"""快数采数据入站与 MES 写回服务。"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional

from apps.kuaizhizao.schemas.equipment_status_monitor import EquipmentStatusMonitorCreate
from apps.kuaizhizao.services.equipment_status_monitor_service import EquipmentStatusMonitorService
from apps.kuaiiot.constants import INGEST_BATCH_MAX_ITEMS, INGEST_MAX_TAGS_PER_PAYLOAD, INGEST_THROTTLE_SECONDS, MES_DATA_SOURCE
from apps.kuaiiot.models.iot import IotDevice, IotIngestDedup, IotTagDefinition, IotTagSnapshot
from apps.kuaiiot.schemas.iot import IngestBatchPayload, IngestBatchResponse, IngestPayload, IngestResponse
from apps.kuaiiot.services.alert_service import AlertService
from apps.kuaiiot.services.tag_history_store import TagHistoryPoint, TagHistoryStore
from core.utils.timezone_utils import resolve_business_datetime
from infra.exceptions.exceptions import ValidationError


class IngestService:
    @staticmethod
    def _coerce_value(raw: Any, value_type: str) -> tuple[Optional[str], Optional[Decimal], Optional[bool]]:
        if raw is None:
            return None, None, None
        if value_type == "boolean":
            if isinstance(raw, bool):
                return None, None, raw
            text = str(raw).strip().lower()
            return None, None, text in {"1", "true", "yes", "on", "online"}
        if value_type == "number":
            try:
                return None, Decimal(str(raw)), None
            except (InvalidOperation, ValueError) as exc:
                raise ValidationError(f"无法解析数值: {raw}") from exc
        return str(raw), None, None

    @staticmethod
    async def _upsert_snapshot(
        tenant_id: int,
        device_id: int,
        tag_key: str,
        value_text: Optional[str],
        value_number: Optional[Decimal],
        value_bool: Optional[bool],
        sampled_at: datetime,
    ) -> None:
        snapshot = await IotTagSnapshot.filter(
            tenant_id=tenant_id,
            device_id=device_id,
            tag_key=tag_key,
            deleted_at__isnull=True,
        ).first()
        if snapshot:
            snapshot.value_text = value_text
            snapshot.value_number = value_number
            snapshot.value_bool = value_bool
            snapshot.sampled_at = sampled_at
            await snapshot.save()
        else:
            await IotTagSnapshot.create(
                tenant_id=tenant_id,
                device_id=device_id,
                tag_key=tag_key,
                value_text=value_text,
                value_number=value_number,
                value_bool=value_bool,
                sampled_at=sampled_at,
            )

    @staticmethod
    def _apply_map_target(
        map_target: str,
        value_text: Optional[str],
        value_number: Optional[Decimal],
        value_bool: Optional[bool],
        mes_payload: Dict[str, Any],
    ) -> None:
        if map_target == "status":
            mes_payload["status"] = value_text if value_text is not None else str(value_number or value_bool)
        elif map_target == "temperature":
            mes_payload["temperature"] = value_number if value_number is not None else Decimal(str(value_text or 0))
        elif map_target == "pressure":
            mes_payload["pressure"] = value_number if value_number is not None else Decimal(str(value_text or 0))
        elif map_target == "vibration":
            mes_payload["vibration"] = value_number if value_number is not None else Decimal(str(value_text or 0))
        elif map_target == "is_online":
            mes_payload["is_online"] = bool(value_bool) if value_bool is not None else str(value_text).lower() in {
                "1",
                "true",
                "yes",
                "on",
                "online",
            }
        elif map_target.startswith("other_parameters."):
            key = map_target.split(".", 1)[1]
            other = mes_payload.setdefault("other_parameters", {})
            if value_text is not None:
                other[key] = value_text
            elif value_number is not None:
                other[key] = float(value_number)
            elif value_bool is not None:
                other[key] = value_bool

    @staticmethod
    async def _load_dedup_response(
        tenant_id: int,
        device_id: int,
        idempotency_key: str,
    ) -> Optional[IngestResponse]:
        item = await IotIngestDedup.filter(
            tenant_id=tenant_id,
            device_id=device_id,
            idempotency_key=idempotency_key,
            deleted_at__isnull=True,
        ).first()
        if not item:
            return None
        return IngestResponse.model_validate_json(item.response_json)

    @staticmethod
    async def _store_dedup_response(
        tenant_id: int,
        device_id: int,
        idempotency_key: str,
        response: IngestResponse,
    ) -> None:
        await IotIngestDedup.create(
            tenant_id=tenant_id,
            device_id=device_id,
            idempotency_key=idempotency_key,
            response_json=response.model_dump_json(),
        )

    @staticmethod
    async def _process_events(
        tenant_id: int,
        device: IotDevice,
        events: list[Any],
        sampled_at: datetime,
    ) -> int:
        if not events:
            return 0
        from apps.kuaiiot.services.message_log_service import MessageLogService
        from apps.kuaiiot.services.product_service import ProductService

        if not device.product_id:
            raise ValidationError("设备未绑定产品模型，无法上报事件")
        product = await ProductService.get_by_id(tenant_id, device.product_id)
        accepted = 0
        for raw in events:
            if not isinstance(raw, dict):
                raise ValidationError("events 项必须为对象")
            event_key = str(raw.get("event_key") or "").strip()
            if not event_key:
                raise ValidationError("event_key 不能为空")
            event_def = ProductService.get_event_definition(product, event_key)
            if not event_def:
                raise ValidationError(f"未定义的事件: {event_key}")
            level = str(event_def.get("level") or "info")
            event_name = str(event_def.get("name") or event_key)
            payload = raw.get("data") if isinstance(raw.get("data"), dict) else raw
            await MessageLogService.append(
                tenant_id=tenant_id,
                device_id=device.id,
                direction="inbound",
                msg_type="other",
                result="success",
                payload={"event_key": event_key, "data": payload},
            )
            if level in {"warning", "critical"}:
                await AlertService.record_event_alert(
                    tenant_id=tenant_id,
                    device=device,
                    event_key=event_key,
                    event_name=event_name,
                    level=level,
                    payload=payload if isinstance(payload, dict) else {"detail": payload},
                )
            accepted += 1
        return accepted

    @staticmethod
    async def ingest(device_token: str, payload: IngestPayload) -> IngestResponse:
        device = await IotDevice.filter(device_token=device_token, deleted_at__isnull=True).first()
        if not device:
            raise ValidationError("无效的设备 token")

        if not payload.tags and not payload.events:
            raise ValidationError("tags 与 events 不能同时为空")

        if len(payload.tags) > INGEST_MAX_TAGS_PER_PAYLOAD:
            raise ValidationError(f"单次入站 tags 最多 {INGEST_MAX_TAGS_PER_PAYLOAD} 个")

        if payload.idempotency_key:
            cached = await IngestService._load_dedup_response(
                tenant_id=device.tenant_id,
                device_id=device.id,
                idempotency_key=payload.idempotency_key,
            )
            if cached:
                return cached

        sampled_at = payload.timestamp or resolve_business_datetime()
        tag_defs = await IotTagDefinition.filter(
            tenant_id=device.tenant_id,
            device_id=device.id,
            is_enabled=True,
            deleted_at__isnull=True,
        )
        tag_map = {item.tag_key: item for item in tag_defs}

        accepted = 0
        mes_payload: Dict[str, Any] = {}
        history_points: list[TagHistoryPoint] = []
        tag_values: Dict[str, tuple[Optional[str], Optional[Decimal], Optional[bool]]] = {}

        for tag_key, raw_value in payload.tags.items():
            tag_def = tag_map.get(tag_key)
            if not tag_def:
                continue
            value_text, value_number, value_bool = IngestService._coerce_value(raw_value, tag_def.value_type)
            tag_values[tag_key] = (value_text, value_number, value_bool)
            await IngestService._upsert_snapshot(
                tenant_id=device.tenant_id,
                device_id=device.id,
                tag_key=tag_key,
                value_text=value_text,
                value_number=value_number,
                value_bool=value_bool,
                sampled_at=sampled_at,
            )
            history_points.append(
                TagHistoryPoint(
                    tag_key=tag_key,
                    value_text=value_text,
                    value_number=value_number,
                    value_bool=value_bool,
                    sampled_at=sampled_at,
                )
            )
            IngestService._apply_map_target(
                tag_def.map_target,
                value_text,
                value_number,
                value_bool,
                mes_payload,
            )
            accepted += 1

        await TagHistoryStore.write_points(
            tenant_id=device.tenant_id,
            device_id=device.id,
            points=history_points,
        )

        if tag_values:
            await AlertService.evaluate_device_ingest(device.tenant_id, device, tag_values)

        events_accepted = 0
        if payload.events:
            events_accepted = await IngestService._process_events(
                device.tenant_id, device, payload.events, sampled_at
            )

        device.is_online = True
        device.last_seen_at = sampled_at
        await device.save()

        synced = await IngestService._maybe_sync_mes(device, mes_payload, sampled_at)
        response = IngestResponse(
            accepted=accepted,
            events_accepted=events_accepted,
            synced_to_mes=synced,
        )
        if payload.idempotency_key:
            await IngestService._store_dedup_response(
                tenant_id=device.tenant_id,
                device_id=device.id,
                idempotency_key=payload.idempotency_key,
                response=response,
            )
        return response

    @staticmethod
    async def ingest_batch(device_token: str, payload: IngestBatchPayload) -> IngestBatchResponse:
        if len(payload.items) > INGEST_BATCH_MAX_ITEMS:
            raise ValidationError(f"单次批量入站最多 {INGEST_BATCH_MAX_ITEMS} 条")

        total = len(payload.items)
        accepted = 0
        duplicates = 0
        failed = 0
        synced_to_mes = False

        for item in payload.items:
            if not item.tags:
                failed += 1
                continue
            ingest_payload = IngestPayload(
                tags=item.tags,
                timestamp=item.timestamp,
                idempotency_key=item.idempotency_key,
            )
            try:
                before = await IngestService._load_dedup_response_by_token(device_token, ingest_payload.idempotency_key)
                result = await IngestService.ingest(device_token, ingest_payload)
                if before is not None:
                    duplicates += 1
                accepted += result.accepted
                synced_to_mes = synced_to_mes or result.synced_to_mes
            except ValidationError:
                failed += 1

        return IngestBatchResponse(
            total=total,
            accepted=accepted,
            duplicates=duplicates,
            failed=failed,
            synced_to_mes=synced_to_mes,
        )

    @staticmethod
    async def _load_dedup_response_by_token(
        device_token: str,
        idempotency_key: Optional[str],
    ) -> Optional[IngestResponse]:
        if not idempotency_key:
            return None
        device = await IotDevice.filter(device_token=device_token, deleted_at__isnull=True).first()
        if not device:
            return None
        return await IngestService._load_dedup_response(
            tenant_id=device.tenant_id,
            device_id=device.id,
            idempotency_key=idempotency_key,
        )

    @staticmethod
    async def sync_offline_to_mes(device: IotDevice) -> bool:
        if not device.equipment_uuid:
            return False
        return await IngestService._maybe_sync_mes(
            device,
            {"is_online": False, "status": "待机"},
            resolve_business_datetime(),
        )

    @staticmethod
    async def _maybe_sync_mes(
        device: IotDevice,
        mes_payload: Dict[str, Any],
        sampled_at: datetime,
    ) -> bool:
        if not device.equipment_uuid or not mes_payload:
            return False

        now = resolve_business_datetime()
        if device.last_mes_sync_at and (now - device.last_mes_sync_at).total_seconds() < INGEST_THROTTLE_SECONDS:
            return False

        status = mes_payload.get("status", "运行中")
        is_online = mes_payload.get("is_online", True)
        monitor_data = EquipmentStatusMonitorCreate(
            equipment_uuid=device.equipment_uuid,
            status=str(status),
            is_online=bool(is_online),
            temperature=mes_payload.get("temperature"),
            pressure=mes_payload.get("pressure"),
            vibration=mes_payload.get("vibration"),
            other_parameters=mes_payload.get("other_parameters"),
            data_source=MES_DATA_SOURCE,
            monitored_at=sampled_at,
        )
        service = EquipmentStatusMonitorService()
        await service.create_status_monitor(tenant_id=device.tenant_id, data=monitor_data)
        device.last_mes_sync_at = now
        await device.save()
        return True
