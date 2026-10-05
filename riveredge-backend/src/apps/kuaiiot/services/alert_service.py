"""快数采告警评估与记录。"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any, Optional

from apps.kuaiiot.constants import EVENT_ALERT_TAG_PREFIX, OFFLINE_ALERT_TAG_KEY
from apps.kuaiiot.models.iot import IotAlert, IotAlertRule, IotDevice
from apps.kuaiiot.services.alert_threshold_resolver import format_actual_value, is_threshold_breached
from core.utils.timezone_utils import resolve_business_datetime
from infra.exceptions.exceptions import NotFoundError, ValidationError


class AlertService:
    @staticmethod
    async def list_alerts(
        tenant_id: int,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
        device_id: Optional[int] = None,
    ) -> tuple[list[IotAlert], int]:
        query = IotAlert.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        if status:
            query = query.filter(status=status)
        if device_id is not None:
            query = query.filter(device_id=device_id)
        total = await query.count()
        items = await query.order_by("-triggered_at").offset((page - 1) * page_size).limit(page_size)
        return items, total

    @staticmethod
    async def get_by_uuid(tenant_id: int, uuid: str) -> IotAlert:
        item = await IotAlert.filter(tenant_id=tenant_id, uuid=uuid, deleted_at__isnull=True).first()
        if not item:
            raise NotFoundError(f"告警记录不存在: {uuid}")
        return item

    @staticmethod
    async def acknowledge(tenant_id: int, uuid: str, user_id: int) -> IotAlert:
        item = await AlertService.get_by_uuid(tenant_id, uuid)
        if item.status == "acknowledged":
            return item
        now = resolve_business_datetime()
        item.status = "acknowledged"
        item.acknowledged_at = now
        item.acknowledged_by = user_id
        await item.save()
        return item

    @staticmethod
    async def evaluate_device_ingest(
        tenant_id: int,
        device: IotDevice,
        tag_values: dict[str, tuple[Optional[str], Optional[Decimal], Optional[bool]]],
    ) -> int:
        if not tag_values:
            return 0
        rules = await IotAlertRule.filter(
            tenant_id=tenant_id,
            is_enabled=True,
            deleted_at__isnull=True,
        )
        matched_rules = []
        for rule in rules:
            if getattr(rule, "rule_type", "threshold") != "threshold":
                continue
            if rule.device_id and rule.device_id != device.id:
                continue
            if rule.equipment_uuid and rule.equipment_uuid != device.equipment_uuid:
                continue
            if not rule.device_id and not rule.equipment_uuid:
                continue
            if rule.tag_key not in tag_values:
                continue
            matched_rules.append(rule)

        triggered = 0
        now = resolve_business_datetime()
        for rule in matched_rules:
            value_text, value_number, value_bool = tag_values[rule.tag_key]
            if not is_threshold_breached(
                rule.operator,
                threshold_number=rule.threshold_number,
                threshold_text=rule.threshold_text,
                value_text=value_text,
                value_number=value_number,
                value_bool=value_bool,
            ):
                continue
            cutoff = now - timedelta(seconds=max(rule.cooldown_seconds, 0))
            recent = await IotAlert.filter(
                tenant_id=tenant_id,
                rule_id=rule.id,
                device_id=device.id,
                status="open",
                triggered_at__gte=cutoff,
                deleted_at__isnull=True,
            ).exists()
            if recent:
                continue
            actual = format_actual_value(value_text, value_number, value_bool)
            threshold_label = (
                str(rule.threshold_number)
                if rule.threshold_number is not None
                else str(rule.threshold_text or "")
            )
            message = f"{rule.name} 触发：{rule.tag_key}={actual}，阈值 {rule.operator} {threshold_label}"
            await IotAlert.create(
                tenant_id=tenant_id,
                rule_id=rule.id,
                device_id=device.id,
                equipment_uuid=device.equipment_uuid,
                tag_key=rule.tag_key,
                severity=rule.severity,
                message=message,
                actual_value=actual,
                status="open",
                triggered_at=now,
            )
            triggered += 1
            if rule.notify_enabled:
                await AlertService._dispatch_notification(
                    tenant_id=tenant_id,
                    rule=rule,
                    device=device,
                    message=message,
                    trigger_action="threshold_breached",
                )
        return triggered

    @staticmethod
    async def record_event_alert(
        tenant_id: int,
        device: IotDevice,
        *,
        event_key: str,
        event_name: str,
        level: str,
        payload: dict[str, Any] | None = None,
    ) -> int:
        if level not in {"warning", "critical"}:
            return 0
        now = resolve_business_datetime()
        tag_key = f"{EVENT_ALERT_TAG_PREFIX}{event_key}"
        cutoff = now - timedelta(seconds=300)
        recent = await IotAlert.filter(
            tenant_id=tenant_id,
            device_id=device.id,
            tag_key=tag_key,
            status="open",
            triggered_at__gte=cutoff,
            deleted_at__isnull=True,
        ).exists()
        if recent:
            return 0
        actual = ""
        if payload:
            actual = str(payload.get("message") or payload.get("detail") or payload)
        message = f"事件告警 {event_name} ({event_key})"
        if actual:
            message = f"{message}: {actual}"
        await IotAlert.create(
            tenant_id=tenant_id,
            rule_id=None,
            device_id=device.id,
            equipment_uuid=device.equipment_uuid,
            tag_key=tag_key,
            severity=level,
            message=message,
            actual_value=actual or event_key,
            status="open",
            triggered_at=now,
        )
        return 1

    @staticmethod
    async def evaluate_device_offline(tenant_id: int, device: IotDevice) -> int:
        rules = await IotAlertRule.filter(
            tenant_id=tenant_id,
            rule_type="offline",
            is_enabled=True,
            deleted_at__isnull=True,
        )
        matched_rules = []
        for rule in rules:
            if rule.device_id and rule.device_id != device.id:
                continue
            if rule.equipment_uuid and rule.equipment_uuid != device.equipment_uuid:
                continue
            if not rule.device_id and not rule.equipment_uuid:
                continue
            matched_rules.append(rule)

        triggered = 0
        now = resolve_business_datetime()
        for rule in matched_rules:
            cutoff = now - timedelta(seconds=max(rule.cooldown_seconds, 0))
            recent = await IotAlert.filter(
                tenant_id=tenant_id,
                rule_id=rule.id,
                device_id=device.id,
                tag_key=OFFLINE_ALERT_TAG_KEY,
                status="open",
                triggered_at__gte=cutoff,
                deleted_at__isnull=True,
            ).exists()
            if recent:
                continue
            message = f"{rule.name} 触发：设备 {device.name} 离线"
            await IotAlert.create(
                tenant_id=tenant_id,
                rule_id=rule.id,
                device_id=device.id,
                equipment_uuid=device.equipment_uuid,
                tag_key=OFFLINE_ALERT_TAG_KEY,
                severity=rule.severity,
                message=message,
                actual_value="offline",
                status="open",
                triggered_at=now,
            )
            triggered += 1
            if rule.notify_enabled:
                await AlertService._dispatch_notification(
                    tenant_id=tenant_id,
                    rule=rule,
                    device=device,
                    message=message,
                    trigger_action="device_offline",
                )
        return triggered

    @staticmethod
    async def _dispatch_notification(
        tenant_id: int,
        rule: IotAlertRule,
        device: IotDevice,
        message: str,
        *,
        trigger_action: str,
    ) -> None:
        try:
            from core.services.business.business_notification_service import BusinessNotificationService

            await BusinessNotificationService.dispatch(
                tenant_id,
                trigger_document="iot_alert",
                trigger_action=trigger_action,
                variables={
                    "rule_name": rule.name,
                    "device_name": device.name,
                    "tag_key": rule.tag_key,
                    "message": message,
                },
            )
        except Exception:
            return
