"""快数采 MQTT 订阅任务入口。"""

from __future__ import annotations

from typing import Any, Dict

from apps.kuaiiot.services.mqtt_subscriber_service import MqttSubscriberService


async def run_kuaiiot_mqtt_reload(force_restart: bool = False) -> Dict[str, Any]:
    return await MqttSubscriberService.reload_connections(force_restart=force_restart)
