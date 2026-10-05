"""快数采边缘 Agent 配置服务。"""

from __future__ import annotations

from typing import Any, Optional

from apps.kuaiiot.constants import EDGE_PROTOCOLS, MODBUS_DATA_TYPES
from apps.kuaiiot.models.iot import IotDevice, IotEdgeConfig
from apps.kuaiiot.schemas.iot import EdgeConfigCreate, EdgeConfigUpdate
from infra.exceptions.exceptions import NotFoundError, ValidationError


class EdgeConfigService:
    @staticmethod
    def _validate_registers(
        registers: Any,
        *,
        tag_key_field: str = "tag_key",
        require_modbus_fields: bool = False,
    ) -> None:
        if not isinstance(registers, list) or not registers:
            raise ValidationError("config.registers 或 config.nodes 不能为空")
        for item in registers:
            if not isinstance(item, dict):
                raise ValidationError("映射项必须为对象")
            if not item.get(tag_key_field):
                raise ValidationError(f"{tag_key_field} 不能为空")
            if require_modbus_fields:
                EdgeConfigService._validate_modbus_register(item, tag_key_field=tag_key_field)

    @staticmethod
    def _validate_modbus_register(item: dict[str, Any], *, tag_key_field: str = "tag_key") -> None:
        address = item.get("address")
        if address is None:
            raise ValidationError(f"{item.get(tag_key_field)} 缺少 address")
        try:
            address_int = int(address)
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"{item.get(tag_key_field)} 的 address 必须为整数") from exc
        if address_int < 0:
            raise ValidationError(f"{item.get(tag_key_field)} 的 address 不能为负数")
        data_type = str(item.get("data_type") or "").strip().lower()
        if not data_type:
            raise ValidationError(f"{item.get(tag_key_field)} 缺少 data_type")
        if data_type not in MODBUS_DATA_TYPES:
            raise ValidationError(
                f"{item.get(tag_key_field)} 的 data_type 必须为 {', '.join(sorted(MODBUS_DATA_TYPES))}"
            )

    @staticmethod
    def _validate_publish(config: dict[str, Any]) -> None:
        publish = config.get("publish")
        if not isinstance(publish, dict):
            raise ValidationError("config.publish 不能为空")
        mode = publish.get("mode")
        if mode not in {"http_ingest", "mqtt"}:
            raise ValidationError("config.publish.mode 必须为 http_ingest 或 mqtt")

    @staticmethod
    def _validate_config(protocol: str, config: dict[str, Any]) -> None:
        if protocol not in EDGE_PROTOCOLS:
            raise ValidationError(f"不支持的协议: {protocol}")
        if protocol in {"modbus_tcp", "modbus_rtu"}:
            EdgeConfigService._validate_registers(config.get("registers"), require_modbus_fields=True)
            EdgeConfigService._validate_publish(config)
            return
        if protocol == "opc_ua":
            if not str(config.get("endpoint") or "").strip():
                raise ValidationError("config.endpoint 不能为空")
            EdgeConfigService._validate_registers(config.get("nodes"), tag_key_field="tag_key")
            EdgeConfigService._validate_publish(config)
            return
        if protocol == "s7":
            if not str(config.get("host") or "").strip():
                raise ValidationError("config.host 不能为空")
            if config.get("rack") is None or config.get("slot") is None:
                raise ValidationError("config.rack 与 config.slot 不能为空")
            EdgeConfigService._validate_registers(config.get("db_blocks"), tag_key_field="tag_key")
            EdgeConfigService._validate_publish(config)

    @staticmethod
    def build_agent_spec(device: IotDevice, item: IotEdgeConfig) -> dict[str, Any]:
        return {
            "version": 1,
            "protocol": item.protocol,
            "device_token": device.device_token,
            "config": item.config,
            "config_version": item.config_version,
        }

    @staticmethod
    async def list_configs(
        tenant_id: int,
        page: int = 1,
        page_size: int = 20,
        device_id: Optional[int] = None,
        q: Optional[str] = None,
    ) -> tuple[list[IotEdgeConfig], int]:
        query = IotEdgeConfig.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        if device_id is not None:
            query = query.filter(device_id=device_id)
        if q:
            query = query.filter(name__icontains=q)
        total = await query.count()
        items = await query.order_by("-created_at", "-id").offset((page - 1) * page_size).limit(page_size)
        return items, total

    @staticmethod
    async def get_by_uuid(tenant_id: int, uuid: str) -> IotEdgeConfig:
        item = await IotEdgeConfig.filter(tenant_id=tenant_id, uuid=uuid, deleted_at__isnull=True).first()
        if not item:
            raise NotFoundError(f"边缘配置不存在: {uuid}")
        return item

    @staticmethod
    async def create(tenant_id: int, data: EdgeConfigCreate) -> IotEdgeConfig:
        exists = await IotEdgeConfig.filter(tenant_id=tenant_id, code=data.code, deleted_at__isnull=True).exists()
        if exists:
            raise ValidationError(f"配置编码已存在: {data.code}")
        device = await IotDevice.filter(id=data.device_id, tenant_id=tenant_id, deleted_at__isnull=True).first()
        if not device:
            raise NotFoundError(f"IoT 设备不存在: {data.device_id}")
        EdgeConfigService._validate_config(data.protocol, data.config or {})
        return await IotEdgeConfig.create(tenant_id=tenant_id, **data.model_dump())

    @staticmethod
    async def update(tenant_id: int, uuid: str, data: EdgeConfigUpdate) -> IotEdgeConfig:
        item = await EdgeConfigService.get_by_uuid(tenant_id, uuid)
        payload = data.model_dump(exclude_unset=True)
        if "device_id" in payload:
            device = await IotDevice.filter(
                id=payload["device_id"], tenant_id=tenant_id, deleted_at__isnull=True
            ).first()
            if not device:
                raise NotFoundError(f"IoT 设备不存在: {payload['device_id']}")
        protocol = payload.get("protocol", item.protocol)
        if "config" in payload:
            EdgeConfigService._validate_config(protocol, payload["config"] or {})
        bump_version = any(key in payload for key in ("protocol", "config", "is_enabled", "device_id"))
        for key, value in payload.items():
            setattr(item, key, value)
        if bump_version:
            item.config_version = int(item.config_version or 1) + 1
        await item.save()
        return item

    @staticmethod
    async def delete(tenant_id: int, uuid: str) -> None:
        item = await EdgeConfigService.get_by_uuid(tenant_id, uuid)
        from core.utils.timezone_utils import resolve_business_datetime

        item.deleted_at = resolve_business_datetime()
        await item.save()

    @staticmethod
    async def export_agent_spec(tenant_id: int, uuid: str) -> dict[str, Any]:
        item = await EdgeConfigService.get_by_uuid(tenant_id, uuid)
        device = await IotDevice.filter(id=item.device_id, tenant_id=tenant_id, deleted_at__isnull=True).first()
        if not device:
            raise NotFoundError(f"IoT 设备不存在: {item.device_id}")
        return EdgeConfigService.build_agent_spec(device, item)
