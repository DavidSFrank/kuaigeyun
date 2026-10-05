"""快数采遥测拉取定时任务入口。"""

from __future__ import annotations

from typing import Any, Dict

from apps.kuaiiot.services.telemetry_sync_service import TelemetrySyncService


async def run_kuaiiot_telemetry_pull() -> Dict[str, Any]:
    return await TelemetrySyncService.pull_all_enabled_connections()
