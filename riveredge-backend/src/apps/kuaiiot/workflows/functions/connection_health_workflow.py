"""快数采连接健康定时任务入口。"""

from __future__ import annotations

from typing import Any, Dict

from apps.kuaiiot.services.connection_health_service import ConnectionHealthService


async def run_kuaiiot_connection_health_check() -> Dict[str, Any]:
    return await ConnectionHealthService.probe_all_enabled()
