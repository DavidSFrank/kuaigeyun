"""快数采数据留存清理定时任务入口。"""

from __future__ import annotations

from typing import Any, Dict

from apps.kuaiiot.services.retention_service import RetentionService


async def run_kuaiiot_retention_cleanup() -> Dict[str, Any]:
    return await RetentionService.purge_expired_records()
