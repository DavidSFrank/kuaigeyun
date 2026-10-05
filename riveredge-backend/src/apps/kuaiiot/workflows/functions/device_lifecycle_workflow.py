"""快数采设备生命周期定时任务入口。"""

from __future__ import annotations

from typing import Any, Dict

from apps.kuaiiot.services.device_lifecycle_service import DeviceLifecycleService


async def run_kuaiiot_offline_check() -> Dict[str, Any]:
    return await DeviceLifecycleService.mark_stale_devices_offline()
