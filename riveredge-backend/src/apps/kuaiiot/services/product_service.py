"""快数采产品物模型服务。"""

from __future__ import annotations

from typing import Any, Optional

from apps.kuaiiot.constants import EVENT_LEVELS, TAG_VALUE_TYPES
from apps.kuaiiot.models.iot import IotDevice, IotProduct
from apps.kuaiiot.schemas.iot import LoadBuiltinProductPresetsResponse, ProductCreate, ProductUpdate
from apps.kuaiiot.services.tag_apply_helper import apply_tag_definitions_to_device
from apps.kuaiiot.services.tag_service import TagService
from apps.kuaiiot.tag_templates import TAG_TEMPLATES
from core.utils.timezone_utils import resolve_business_datetime
from infra.exceptions.exceptions import NotFoundError, ValidationError


class ProductService:
    @staticmethod
    def _validate_tags(tags: Any) -> list[dict[str, Any]]:
        if not isinstance(tags, list) or not tags:
            raise ValidationError("tags 不能为空")
        normalized: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in tags:
            if not isinstance(item, dict):
                raise ValidationError("tags 项必须为对象")
            tag_key = str(item.get("tag_key") or "").strip()
            if not tag_key:
                raise ValidationError("tag_key 不能为空")
            if tag_key in seen:
                raise ValidationError(f"tag_key 重复: {tag_key}")
            seen.add(tag_key)
            map_target = str(item.get("map_target") or "").strip()
            TagService._validate_map_target(map_target)
            value_type = str(item.get("value_type") or "number").strip()
            if value_type not in {"string", "number", "boolean"}:
                raise ValidationError(f"无效 value_type: {value_type}")
            normalized.append(
                {
                    "tag_key": tag_key,
                    "name": str(item.get("name") or tag_key),
                    "value_type": value_type,
                    "unit": item.get("unit"),
                    "map_target": map_target,
                    "fill_target": item.get("fill_target"),
                }
            )
        return normalized

    @staticmethod
    def _validate_events(events: Any) -> list[dict[str, Any]]:
        if events is None:
            return []
        if not isinstance(events, list):
            raise ValidationError("events 必须为数组")
        normalized: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in events:
            if not isinstance(item, dict):
                raise ValidationError("events 项必须为对象")
            event_key = str(item.get("event_key") or "").strip()
            if not event_key:
                raise ValidationError("event_key 不能为空")
            if event_key in seen:
                raise ValidationError(f"event_key 重复: {event_key}")
            seen.add(event_key)
            level = str(item.get("level") or "info").strip()
            if level not in EVENT_LEVELS:
                raise ValidationError(f"无效 level: {level}")
            normalized.append(
                {
                    "event_key": event_key,
                    "name": str(item.get("name") or event_key),
                    "level": level,
                }
            )
        return normalized

    @staticmethod
    def _validate_functions(functions: Any) -> list[dict[str, Any]]:
        if functions is None:
            return []
        if not isinstance(functions, list):
            raise ValidationError("functions 必须为数组")
        normalized: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in functions:
            if not isinstance(item, dict):
                raise ValidationError("functions 项必须为对象")
            function_key = str(item.get("function_key") or "").strip()
            if not function_key:
                raise ValidationError("function_key 不能为空")
            if function_key in seen:
                raise ValidationError(f"function_key 重复: {function_key}")
            seen.add(function_key)
            timeout_seconds = int(item.get("timeout_seconds") or 30)
            if timeout_seconds < 1 or timeout_seconds > 3600:
                raise ValidationError("timeout_seconds 必须在 1-3600 之间")
            params_raw = item.get("params") or []
            if not isinstance(params_raw, list):
                raise ValidationError("params 必须为数组")
            params: list[dict[str, Any]] = []
            param_seen: set[str] = set()
            for param in params_raw:
                if not isinstance(param, dict):
                    raise ValidationError("params 项必须为对象")
                key = str(param.get("key") or "").strip()
                if not key:
                    raise ValidationError("param key 不能为空")
                if key in param_seen:
                    raise ValidationError(f"param key 重复: {key}")
                param_seen.add(key)
                value_type = str(param.get("value_type") or "number").strip()
                if value_type not in TAG_VALUE_TYPES:
                    raise ValidationError(f"无效 value_type: {value_type}")
                params.append(
                    {
                        "key": key,
                        "name": str(param.get("name") or key),
                        "value_type": value_type,
                        "required": bool(param.get("required", True)),
                    }
                )
            edge_action = item.get("edge_action")
            if edge_action is not None and not isinstance(edge_action, dict):
                raise ValidationError("edge_action 必须为对象")
            normalized.append(
                {
                    "function_key": function_key,
                    "name": str(item.get("name") or function_key),
                    "params": params,
                    "timeout_seconds": timeout_seconds,
                    "edge_action": edge_action,
                }
            )
        return normalized

    @staticmethod
    def get_event_definition(product: IotProduct, event_key: str) -> dict[str, Any] | None:
        events = product.events if isinstance(product.events, list) else []
        for item in events:
            if isinstance(item, dict) and str(item.get("event_key") or "") == event_key:
                return item
        return None

    @staticmethod
    async def list_products(
        tenant_id: int,
        page: int = 1,
        page_size: int = 20,
        q: Optional[str] = None,
    ) -> tuple[list[IotProduct], int]:
        query = IotProduct.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        if q:
            query = query.filter(name__icontains=q)
        total = await query.count()
        items = await query.order_by("-created_at", "-id").offset((page - 1) * page_size).limit(page_size)
        return items, total

    @staticmethod
    async def get_by_uuid(tenant_id: int, uuid: str) -> IotProduct:
        item = await IotProduct.filter(tenant_id=tenant_id, uuid=uuid, deleted_at__isnull=True).first()
        if not item:
            raise NotFoundError(f"产品物模型不存在: {uuid}")
        return item

    @staticmethod
    async def get_by_id(tenant_id: int, product_id: int) -> IotProduct:
        item = await IotProduct.filter(tenant_id=tenant_id, id=product_id, deleted_at__isnull=True).first()
        if not item:
            raise NotFoundError(f"产品物模型不存在: {product_id}")
        return item

    @staticmethod
    async def create(tenant_id: int, data: ProductCreate) -> IotProduct:
        exists = await IotProduct.filter(tenant_id=tenant_id, code=data.code, deleted_at__isnull=True).exists()
        if exists:
            raise ValidationError(f"产品编码已存在: {data.code}")
        tags = ProductService._validate_tags(data.model_dump()["tags"])
        events = ProductService._validate_events(data.model_dump().get("events") or [])
        functions = ProductService._validate_functions(data.model_dump().get("functions") or [])
        return await IotProduct.create(
            tenant_id=tenant_id,
            code=data.code,
            name=data.name,
            description=data.description,
            tags=tags,
            events=events,
            functions=functions,
            remark=data.remark,
        )

    @staticmethod
    async def update(tenant_id: int, uuid: str, data: ProductUpdate) -> IotProduct:
        item = await ProductService.get_by_uuid(tenant_id, uuid)
        payload = data.model_dump(exclude_unset=True)
        if "tags" in payload:
            payload["tags"] = ProductService._validate_tags(payload["tags"])
        if "events" in payload:
            payload["events"] = ProductService._validate_events(payload["events"])
        if "functions" in payload:
            payload["functions"] = ProductService._validate_functions(payload["functions"])
        for key, value in payload.items():
            setattr(item, key, value)
        await item.save()
        return item

    @staticmethod
    async def delete(tenant_id: int, uuid: str) -> None:
        item = await ProductService.get_by_uuid(tenant_id, uuid)
        item.deleted_at = resolve_business_datetime()
        await item.save()

    @staticmethod
    async def load_builtin_presets(tenant_id: int) -> LoadBuiltinProductPresetsResponse:
        created = 0
        skipped = 0
        for code, template in TAG_TEMPLATES.items():
            exists = await IotProduct.filter(tenant_id=tenant_id, code=code, deleted_at__isnull=True).exists()
            if exists:
                skipped += 1
                continue
            tags = ProductService._validate_tags(template.get("tags") or [])
            events = ProductService._validate_events(template.get("events") or [])
            functions = ProductService._validate_functions(template.get("functions") or [])
            await IotProduct.create(
                tenant_id=tenant_id,
                code=code,
                name=str(template.get("name") or code),
                description=template.get("description"),
                tags=tags,
                events=events,
                functions=functions,
            )
            created += 1
        total = await IotProduct.filter(tenant_id=tenant_id, deleted_at__isnull=True).count()
        return LoadBuiltinProductPresetsResponse(created=created, skipped=skipped, total=total)

    @staticmethod
    async def apply_product_for_device(tenant_id: int, device: IotDevice, product_id: int) -> tuple[int, int]:
        product = await ProductService.get_by_id(tenant_id, product_id)
        tags = product.tags if isinstance(product.tags, list) else []
        return await apply_tag_definitions_to_device(tenant_id, device, tags)

    @staticmethod
    async def apply_product_for_device_id(tenant_id: int, device: IotDevice, product_id: Optional[int]) -> None:
        if not product_id:
            return
        await ProductService.apply_product_for_device(tenant_id, device, product_id)
