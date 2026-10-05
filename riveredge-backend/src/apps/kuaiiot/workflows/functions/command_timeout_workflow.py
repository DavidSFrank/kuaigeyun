"""快数采指令超时检测定时任务入口。"""

from __future__ import annotations

from typing import Any, Dict

from apps.kuaiiot.services.command_service import CommandService


async def run_kuaiiot_command_timeout_check() -> Dict[str, Any]:
    timed_out = await CommandService.timeout_expired_commands()
    return {"timed_out": timed_out}
