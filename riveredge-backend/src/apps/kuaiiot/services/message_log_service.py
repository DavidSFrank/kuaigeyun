"""快数采设备消息追踪日志。"""

from __future__ import annotations

import json
from typing import Any, Optional

from apps.kuaiiot.constants import (
    MESSAGE_DIRECTIONS,
    MESSAGE_LOG_PAYLOAD_MAX,
    MESSAGE_RESULTS,
    MESSAGE_TYPES,
)
from apps.kuaiiot.models.iot import IotMessageLog
from infra.exceptions.exceptions import ValidationError


class MessageLogService:
    @staticmethod
    def _truncate_payload(payload: Any) -> Any:
        if payload is None:
            return None
        try:
            text = json.dumps(payload, ensure_ascii=False, default=str)
        except TypeError:
            text = str(payload)
        if len(text) <= MESSAGE_LOG_PAYLOAD_MAX:
            return payload if isinstance(payload, (dict, list)) else {"value": text}
        return {"truncated": True, "preview": text[:MESSAGE_LOG_PAYLOAD_MAX]}

    @staticmethod
    async def append(
        tenant_id: int,
        device_id: int,
        *,
        direction: str,
        msg_type: str,
        result: str,
        payload: Any = None,
        error_message: Optional[str] = None,
    ) -> IotMessageLog:
        if direction not in MESSAGE_DIRECTIONS:
            raise ValidationError(f"无效 direction: {direction}")
        if msg_type not in MESSAGE_TYPES:
            raise ValidationError(f"无效 msg_type: {msg_type}")
        if result not in MESSAGE_RESULTS:
            raise ValidationError(f"无效 result: {result}")
        return await IotMessageLog.create(
            tenant_id=tenant_id,
            device_id=device_id,
            direction=direction,
            msg_type=msg_type,
            payload=MessageLogService._truncate_payload(payload),
            result=result,
            error_message=error_message,
        )

    @staticmethod
    async def list_logs(
        tenant_id: int,
        device_id: int,
        *,
        page: int = 1,
        page_size: int = 20,
        direction: Optional[str] = None,
        msg_type: Optional[str] = None,
    ) -> tuple[list[IotMessageLog], int]:
        query = IotMessageLog.filter(
            tenant_id=tenant_id,
            device_id=device_id,
            deleted_at__isnull=True,
        )
        if direction:
            query = query.filter(direction=direction)
        if msg_type:
            query = query.filter(msg_type=msg_type)
        total = await query.count()
        items = await query.order_by("-created_at").offset((page - 1) * page_size).limit(page_size)
        return items, total
