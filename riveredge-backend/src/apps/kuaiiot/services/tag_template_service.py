"""快数采点位模板服务。"""

from __future__ import annotations

from apps.kuaiiot.models.iot import IotDevice
from apps.kuaiiot.schemas.iot import ApplyTagTemplateResponse, TagTemplateResponse
from apps.kuaiiot.services.device_service import DeviceService
from apps.kuaiiot.services.tag_service import TagService
from apps.kuaiiot.tag_templates import TAG_TEMPLATES
from infra.exceptions.exceptions import NotFoundError


class TagTemplateService:
    @staticmethod
    def list_templates() -> list[TagTemplateResponse]:
        return [
            TagTemplateResponse(
                code=code,
                name=item["name"],
                description=item.get("description"),
                tag_count=len(item.get("tags") or []),
            )
            for code, item in TAG_TEMPLATES.items()
        ]

    @staticmethod
    async def apply_template(tenant_id: int, device_uuid: str, template_code: str) -> ApplyTagTemplateResponse:
        template = TAG_TEMPLATES.get(template_code)
        if not template:
            raise NotFoundError(f"点位模板不存在: {template_code}")

        device = await DeviceService.get_by_uuid(tenant_id, device_uuid)
        created = 0
        skipped = 0
        for tag in template.get("tags") or []:
            map_target = tag["map_target"]
            TagService._validate_map_target(map_target)
            exists = await IotTagDefinition.filter(
                tenant_id=tenant_id,
                device_id=device.id,
                tag_key=tag["tag_key"],
                deleted_at__isnull=True,
            ).exists()
            if exists:
                skipped += 1
                continue
            await IotTagDefinition.create(
                tenant_id=tenant_id,
                device_id=device.id,
                tag_key=tag["tag_key"],
                name=tag["name"],
                value_type=tag["value_type"],
                unit=tag.get("unit"),
                map_target=map_target,
            )
            created += 1
        return ApplyTagTemplateResponse(created=created, skipped=skipped, template_code=template_code)

    @staticmethod
    async def apply_template_for_device_id(tenant_id: int, device: IotDevice, template_code: str) -> None:
        if not template_code:
            return
        await TagTemplateService.apply_template(tenant_id, device.uuid, template_code)
