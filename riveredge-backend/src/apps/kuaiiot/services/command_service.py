"""快数采设备指令下发服务。"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Optional

from apps.kuaiiot.constants import (
    COMMAND_DEFAULT_TIMEOUT_SECONDS,
    COMMAND_STATUSES,
    DISPATCH_CHANNELS,
    TAG_VALUE_TYPES,
)
from apps.kuaiiot.models.iot import IotConnection, IotDevice, IotDeviceCommand, IotEdgeConfig, IotProduct
from apps.kuaiiot.schemas.iot import DeviceCommandCreate
from apps.kuaiiot.services.connector_service import ConnectorService
from apps.kuaiiot.services.message_log_service import MessageLogService
from apps.kuaiiot.services.product_service import ProductService
from core.utils.timezone_utils import resolve_business_datetime
from infra.exceptions.exceptions import NotFoundError, ValidationError


class CommandService:
    @staticmethod
    def _find_function(product: IotProduct, function_key: str) -> dict[str, Any]:
        functions = product.functions if isinstance(product.functions, list) else []
        for item in functions:
            if isinstance(item, dict) and str(item.get("function_key") or "") == function_key:
                return item
        raise ValidationError(f"产品未定义功能: {function_key}")

    @staticmethod
    def _validate_params(function_def: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        param_defs = function_def.get("params") or []
        if not isinstance(param_defs, list):
            raise ValidationError("功能 params 定义无效")
        seen: set[str] = set()
        for item in param_defs:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "").strip()
            if not key or key in seen:
                continue
            seen.add(key)
            required = bool(item.get("required", True))
            value_type = str(item.get("value_type") or "number").strip()
            if value_type not in TAG_VALUE_TYPES:
                raise ValidationError(f"无效 value_type: {value_type}")
            if key not in params:
                if required:
                    raise ValidationError(f"缺少必填参数: {key}")
                continue
            raw = params[key]
            if value_type == "boolean" and not isinstance(raw, bool):
                normalized[key] = str(raw).strip().lower() in {"1", "true", "yes", "on"}
            elif value_type == "number":
                normalized[key] = float(raw)
            else:
                normalized[key] = str(raw)
        extra = set(params.keys()) - seen
        if extra:
            raise ValidationError(f"未知参数: {', '.join(sorted(extra))}")
        return normalized

    @staticmethod
    async def _resolve_dispatch_channel(
        tenant_id: int,
        device: IotDevice,
        requested: Optional[str],
    ) -> str:
        if requested:
            if requested not in DISPATCH_CHANNELS:
                raise ValidationError(f"无效 dispatch_channel: {requested}")
            return requested
        edge_exists = await IotEdgeConfig.filter(
            tenant_id=tenant_id,
            device_id=device.id,
            is_enabled=True,
            deleted_at__isnull=True,
        ).exists()
        if edge_exists:
            return "edge"
        if device.connection_id:
            connection = await IotConnection.filter(
                tenant_id=tenant_id,
                id=device.connection_id,
                deleted_at__isnull=True,
            ).first()
            if connection and connection.connection_type in {"thingsboard", "jetlinks"}:
                return connection.connection_type
        raise ValidationError("无法确定指令下发通道，请指定 dispatch_channel 或配置边缘 Agent / 连接源")

    @staticmethod
    async def create_command(
        tenant_id: int,
        device: IotDevice,
        data: DeviceCommandCreate,
        *,
        requested_by: Optional[int] = None,
    ) -> IotDeviceCommand:
        if not device.product_id:
            raise ValidationError("设备未绑定产品模型，无法下发指令")
        product = await ProductService.get_by_id(tenant_id, device.product_id)
        function_def = CommandService._find_function(product, data.function_key)
        params = CommandService._validate_params(function_def, dict(data.params or {}))
        channel = await CommandService._resolve_dispatch_channel(tenant_id, device, data.dispatch_channel)
        timeout_seconds = int(function_def.get("timeout_seconds") or COMMAND_DEFAULT_TIMEOUT_SECONDS)
        now = resolve_business_datetime()
        command = await IotDeviceCommand.create(
            tenant_id=tenant_id,
            device_id=device.id,
            function_key=data.function_key,
            params=params,
            dispatch_channel=channel,
            status="pending",
            requested_by=requested_by,
            expires_at=now + timedelta(seconds=max(timeout_seconds, 1)),
        )
        await MessageLogService.append(
            tenant_id=tenant_id,
            device_id=device.id,
            direction="down",
            msg_type="command",
            result="accepted",
            payload={
                "command_uuid": command.uuid,
                "function_key": command.function_key,
                "params": params,
                "dispatch_channel": channel,
            },
        )
        if channel in {"thingsboard", "jetlinks"}:
            await CommandService._dispatch_upstream(tenant_id, device, command, function_def)
        return command

    @staticmethod
    async def _dispatch_upstream(
        tenant_id: int,
        device: IotDevice,
        command: IotDeviceCommand,
        function_def: dict[str, Any],
    ) -> None:
        now = resolve_business_datetime()
        try:
            result = await ConnectorService.invoke_device_function(
                tenant_id=tenant_id,
                device=device,
                function_key=command.function_key,
                params=command.params,
                function_def=function_def,
            )
            command.status = "success"
            command.result = result
            command.sent_at = now
            command.completed_at = now
            await command.save()
            await MessageLogService.append(
                tenant_id=tenant_id,
                device_id=device.id,
                direction="up",
                msg_type="command_result",
                result="synced",
                payload={"command_uuid": command.uuid, "result": result},
            )
        except Exception as exc:
            command.status = "failed"
            command.error_message = str(exc)
            command.sent_at = now
            command.completed_at = now
            await command.save()
            await MessageLogService.append(
                tenant_id=tenant_id,
                device_id=device.id,
                direction="up",
                msg_type="command_result",
                result="error",
                payload={"command_uuid": command.uuid},
                error_message=str(exc),
            )

    @staticmethod
    async def list_commands(
        tenant_id: int,
        device_id: int,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[IotDeviceCommand], int]:
        query = IotDeviceCommand.filter(
            tenant_id=tenant_id,
            device_id=device_id,
            deleted_at__isnull=True,
        )
        total = await query.count()
        items = await query.order_by("-created_at").offset((page - 1) * page_size).limit(page_size)
        return items, total

    @staticmethod
    async def get_by_uuid(tenant_id: int, uuid: str) -> IotDeviceCommand:
        item = await IotDeviceCommand.filter(tenant_id=tenant_id, uuid=uuid, deleted_at__isnull=True).first()
        if not item:
            raise NotFoundError(f"指令不存在: {uuid}")
        return item

    @staticmethod
    async def claim_pending_for_edge(
        tenant_id: int,
        device_id: int,
        *,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        now = resolve_business_datetime()
        pending = await IotDeviceCommand.filter(
            tenant_id=tenant_id,
            device_id=device_id,
            dispatch_channel="edge",
            status="pending",
            deleted_at__isnull=True,
        ).order_by("created_at").limit(limit)
        payloads: list[dict[str, Any]] = []
        device = await IotDevice.filter(tenant_id=tenant_id, id=device_id, deleted_at__isnull=True).first()
        edge_action: dict[str, Any] | None = None
        if device and device.product_id:
            product = await IotProduct.filter(tenant_id=tenant_id, id=device.product_id, deleted_at__isnull=True).first()
            if product:
                functions = product.functions if isinstance(product.functions, list) else []
                function_map = {
                    str(item.get("function_key")): item
                    for item in functions
                    if isinstance(item, dict) and item.get("function_key")
                }
        else:
            function_map = {}

        for command in pending:
            function_def = function_map.get(command.function_key, {})
            edge_action = function_def.get("edge_action") if isinstance(function_def, dict) else None
            command.status = "sent"
            command.sent_at = now
            await command.save()
            payloads.append(
                {
                    "command_uuid": command.uuid,
                    "function_key": command.function_key,
                    "params": command.params,
                    "edge_action": edge_action,
                    "expires_at": command.expires_at.isoformat() if command.expires_at else None,
                }
            )
        return payloads

    @staticmethod
    async def complete_edge_command(
        tenant_id: int,
        device_id: int,
        *,
        command_uuid: str,
        success: bool,
        result: Any = None,
        error_message: Optional[str] = None,
    ) -> IotDeviceCommand:
        command = await IotDeviceCommand.filter(
            tenant_id=tenant_id,
            device_id=device_id,
            uuid=command_uuid,
            deleted_at__isnull=True,
        ).first()
        if not command:
            raise NotFoundError(f"指令不存在: {command_uuid}")
        if command.status in {"success", "failed", "timeout"}:
            return command
        now = resolve_business_datetime()
        command.status = "success" if success else "failed"
        command.result = result if isinstance(result, dict) else {"value": result}
        command.error_message = error_message
        command.completed_at = now
        await command.save()
        await MessageLogService.append(
            tenant_id=tenant_id,
            device_id=device_id,
            direction="up",
            msg_type="command_result",
            result="synced" if success else "error",
            payload={"command_uuid": command.uuid, "result": command.result},
            error_message=error_message,
        )
        return command

    @staticmethod
    async def timeout_expired_commands() -> int:
        now = resolve_business_datetime()
        expired = await IotDeviceCommand.filter(
            status__in=["pending", "sent"],
            expires_at__lt=now,
            deleted_at__isnull=True,
        ).all()
        count = 0
        for command in expired:
            command.status = "timeout"
            command.completed_at = now
            command.error_message = "指令执行超时"
            await command.save()
            await MessageLogService.append(
                tenant_id=command.tenant_id,
                device_id=command.device_id,
                direction="up",
                msg_type="command_result",
                result="error",
                payload={"command_uuid": command.uuid},
                error_message=command.error_message,
            )
            count += 1
        return count
