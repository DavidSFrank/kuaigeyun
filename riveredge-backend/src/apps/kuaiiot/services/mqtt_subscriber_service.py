"""MQTT 连接源订阅入站。"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Optional

from loguru import logger

from apps.kuaiiot.models.iot import IotConnection, IotDevice
from apps.kuaiiot.schemas.iot import IngestPayload
from apps.kuaiiot.services.ingest_service import IngestService
from apps.kuaiiot.services.mqtt_message_buffer import MqttMessageBuffer
from apps.kuaiiot.services.mqtt_paho_bridge import PahoMqttSession, probe_broker_sync
from apps.kuaiiot.services.sanyi_line_adapter import is_sanyi_line_payload, iter_sanyi_device_ingest
from infra.exceptions.exceptions import ValidationError


class MqttSubscriberService:
    _tasks: Dict[int, asyncio.Task] = {}

    @staticmethod
    def _connection_settings(connection: IotConnection) -> dict[str, Any]:
        config = connection.config or {}
        host = str(config.get("broker_host") or config.get("host") or "").strip()
        port = int(config.get("broker_port") or config.get("port") or 1883)
        topic_filter = str(config.get("topic_filter") or "kuaiiot/ingest/+").strip()
        qos = int(config.get("qos") or 1)
        username = config.get("username") or None
        password = config.get("password") or None
        use_tls = bool(config.get("use_tls"))
        payload_format = str(config.get("payload_format") or "auto").strip().lower()
        if payload_format not in {"auto", "kuaiiot", "sanyi_line"}:
            payload_format = "auto"
        client_id = str(config.get("client_id") or config.get("identifier") or "").strip()
        if not client_id:
            client_id = f"kuaiiot-{connection.code}-{connection.id}"
        if not host:
            raise ValueError("MQTT 配置缺少 broker_host")
        return {
            "host": host,
            "port": port,
            "topic_filter": topic_filter,
            "qos": qos,
            "username": username,
            "password": password,
            "use_tls": use_tls,
            "payload_format": payload_format,
            "client_id": client_id,
        }

    @staticmethod
    def _extract_device_token(topic: str) -> Optional[str]:
        parts = [part for part in topic.split("/") if part]
        if not parts:
            return None
        return parts[-1]

    @staticmethod
    def _resolve_format(payload_format: str, payload_data: Any) -> str:
        if payload_format == "sanyi_line":
            return "sanyi_line"
        if payload_format == "kuaiiot":
            return "kuaiiot"
        if is_sanyi_line_payload(payload_data):
            return "sanyi_line"
        return "kuaiiot"

    @classmethod
    async def _find_device_by_external_id(
        cls,
        tenant_id: int,
        connection_id: int,
        external_device_id: str,
    ) -> Optional[IotDevice]:
        device = await IotDevice.filter(
            tenant_id=tenant_id,
            connection_id=connection_id,
            external_device_id=external_device_id,
            deleted_at__isnull=True,
        ).first()
        if device:
            return device
        return await IotDevice.filter(
            tenant_id=tenant_id,
            external_device_id=external_device_id,
            deleted_at__isnull=True,
        ).first()

    @classmethod
    async def _ingest_sanyi_line(
        cls,
        connection: IotConnection,
        payload_data: dict[str, Any],
    ) -> dict[str, Any]:
        ingested = 0
        skipped: list[dict[str, str]] = []
        errors: list[dict[str, str]] = []
        for item in iter_sanyi_device_ingest(payload_data):
            external_id = item["external_device_id"]
            device = await cls._find_device_by_external_id(
                connection.tenant_id,
                connection.id,
                external_id,
            )
            if not device:
                skipped.append(
                    {
                        "external_device_id": external_id,
                        "device_name": item["device_name"],
                        "reason": "未找到匹配设备（请将外部设备 ID 设为 device_id）",
                    }
                )
                continue
            try:
                payload = IngestPayload(tags=item["tags"], timestamp=item.get("timestamp"))
                await IngestService.ingest(device.device_token, payload)
                ingested += 1
            except ValidationError as exc:
                errors.append({"external_device_id": external_id, "reason": str(exc)})
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "kuaiiot mqtt sanyi ingest failed connection_id={} external_id={}: {}",
                    connection.id,
                    external_id,
                    exc,
                )
                errors.append({"external_device_id": external_id, "reason": str(exc)})
        return {
            "ingested_devices": ingested,
            "skipped_devices": len(skipped),
            "error_devices": len(errors),
            "skipped": skipped[:20],
            "errors": errors[:20],
        }

    @classmethod
    async def _ingest_kuaiiot_token(
        cls,
        topic: str,
        payload_data: Any,
    ) -> dict[str, Any]:
        token = cls._extract_device_token(topic)
        if not token:
            raise ValidationError("无法从 Topic 解析 device_token")
        payload = IngestPayload.model_validate(payload_data)
        result = await IngestService.ingest(token, payload)
        return {
            "ingested_devices": 1 if result.accepted or result.events_accepted else 0,
            "accepted_tags": result.accepted,
            "device_token_suffix": token[-6:] if len(token) > 6 else token,
        }

    @classmethod
    async def _record_inbound(
        cls,
        connection: IotConnection,
        *,
        topic: str,
        qos: int,
        retained: bool,
        payload: Any,
        payload_format: str,
        ingest_summary: Optional[dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        await MqttMessageBuffer.persist(
            connection.tenant_id,
            connection.id,
            topic=topic,
            qos=qos,
            retained=retained,
            payload=payload,
            payload_format=payload_format,
            ingest_summary=ingest_summary,
            error=error,
        )
        from apps.kuaiiot.services.connection_service import ConnectionService

        await ConnectionService.apply_health(
            connection,
            healthy=True,
            min_interval_seconds=60,
        )

    @classmethod
    async def _handle_message(
        cls,
        connection: IotConnection,
        settings: dict[str, Any],
        message: Any,
    ) -> None:
        topic = str(message.topic)
        qos = int(getattr(message, "qos", settings["qos"]) or 0)
        retained = bool(getattr(message, "retain", False))
        raw_text: Optional[str] = None
        payload_data: Any = None
        try:
            raw_text = message.payload.decode("utf-8")
            payload_data = json.loads(raw_text)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            await cls._record_inbound(
                connection,
                topic=topic,
                qos=qos,
                retained=retained,
                payload={"raw": raw_text[:2000] if raw_text else None},
                payload_format="invalid_json",
                error=str(exc),
            )
            logger.warning("kuaiiot mqtt invalid payload connection_id={}: {}", connection.id, exc)
            return

        resolved_format = cls._resolve_format(settings["payload_format"], payload_data)
        try:
            if resolved_format == "sanyi_line":
                if not is_sanyi_line_payload(payload_data):
                    raise ValidationError("报文不是三易产线格式（缺少 devices[].variables）")
                summary = await cls._ingest_sanyi_line(connection, payload_data)
            else:
                summary = await cls._ingest_kuaiiot_token(topic, payload_data)
            await cls._record_inbound(
                connection,
                topic=topic,
                qos=qos,
                retained=retained,
                payload=payload_data,
                payload_format=resolved_format,
                ingest_summary=summary,
            )
        except ValidationError as exc:
            await cls._record_inbound(
                connection,
                topic=topic,
                qos=qos,
                retained=retained,
                payload=payload_data,
                payload_format=resolved_format,
                error=str(exc),
            )
            logger.warning(
                "kuaiiot mqtt ingest rejected connection_id={} topic={}: {}",
                connection.id,
                topic,
                exc,
            )
        except Exception as exc:  # noqa: BLE001
            await cls._record_inbound(
                connection,
                topic=topic,
                qos=qos,
                retained=retained,
                payload=payload_data,
                payload_format=resolved_format,
                error=str(exc),
            )
            logger.warning(
                "kuaiiot mqtt ingest error connection_id={} topic={}: {}",
                connection.id,
                topic,
                exc,
            )

    @classmethod
    async def _run_connection(cls, connection: IotConnection) -> None:
        while True:
            session: Optional[PahoMqttSession] = None
            try:
                fresh = await IotConnection.filter(id=connection.id, deleted_at__isnull=True).first()
                if not fresh or not fresh.is_enabled:
                    return
                connection = fresh
                settings = cls._connection_settings(connection)
                queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
                loop = asyncio.get_running_loop()
                session = PahoMqttSession(settings)
                await asyncio.to_thread(session.start, loop, queue)
                logger.info(
                    "kuaiiot mqtt subscribed connection_id={} topic={} payload_format={} client_id={}",
                    connection.id,
                    settings["topic_filter"],
                    settings["payload_format"],
                    settings["client_id"],
                )
                from apps.kuaiiot.services.connection_service import ConnectionService

                await ConnectionService.apply_health(
                    connection,
                    healthy=True,
                    min_interval_seconds=30,
                )
                while True:
                    message = await queue.get()
                    if message is None:
                        raise ConnectionError("MQTT 已断开")
                    await cls._handle_message(connection, settings, message)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "kuaiiot mqtt connection_id={} disconnected, retry in 5s: {}",
                    connection.id,
                    exc,
                )
                await asyncio.sleep(5)
            finally:
                if session is not None:
                    await asyncio.to_thread(session.stop)

    @classmethod
    async def _cancel_task(cls, connection_id: int, *, clear_buffer: bool = False) -> None:
        task = cls._tasks.pop(connection_id, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        if clear_buffer:
            MqttMessageBuffer.clear(connection_id)

    @classmethod
    async def start_all(cls, *, force_restart: bool = False) -> None:
        connections = await IotConnection.filter(
            connection_type="mqtt",
            is_enabled=True,
            deleted_at__isnull=True,
        )
        active_ids = {item.id for item in connections}
        for connection_id in list(cls._tasks.keys()):
            if connection_id not in active_ids or force_restart:
                await cls._cancel_task(connection_id, clear_buffer=connection_id not in active_ids)
        for connection in connections:
            if connection.id in cls._tasks:
                continue
            task = asyncio.create_task(cls._run_connection(connection), name=f"kuaiiot-mqtt-{connection.id}")
            cls._tasks[connection.id] = task

    @classmethod
    async def stop_all(cls) -> None:
        for connection_id in list(cls._tasks.keys()):
            await cls._cancel_task(connection_id, clear_buffer=True)

    @classmethod
    async def reload_connections(cls, *, force_restart: bool = False) -> dict[str, int]:
        await cls.start_all(force_restart=force_restart)
        return {"active_subscriptions": len(cls._tasks)}

    @staticmethod
    async def probe_broker(connection: IotConnection) -> bool:
        settings = MqttSubscriberService._connection_settings(connection)
        try:
            return await asyncio.to_thread(probe_broker_sync, settings)
        except Exception as exc:  # noqa: BLE001
            logger.warning("kuaiiot mqtt probe failed: {}", exc)
            return False
