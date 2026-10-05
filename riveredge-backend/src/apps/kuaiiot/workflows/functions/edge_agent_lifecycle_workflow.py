"""快数采边缘 Agent 离线检测任务入口。"""

from __future__ import annotations

from typing import Any, Dict

from apps.kuaiiot.services.edge_agent_lifecycle_service import EdgeAgentLifecycleService


async def run_kuaiiot_edge_agent_offline_check() -> Dict[str, Any]:
    return await EdgeAgentLifecycleService.mark_stale_agents_offline()
