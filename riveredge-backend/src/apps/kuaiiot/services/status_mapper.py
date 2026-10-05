"""中国设备态语义归一化。"""

from __future__ import annotations

from apps.kuaizhizao.schemas.equipment import EQUIPMENT_ALLOWED_STATUSES

_STATUS_ALIASES: dict[str, str] = {
    "normal": "正常",
    "ok": "正常",
    "idle": "待机",
    "standby": "待机",
    "stop": "待机",
    "stopped": "待机",
    "停机": "待机",
    "running": "运行中",
    "run": "运行中",
    "working": "运行中",
    "加工": "运行中",
    "fault": "故障",
    "error": "故障",
    "alarm": "故障",
    "repair": "维修中",
    "maintenance": "维修中",
    "maintaining": "维修中",
    "disabled": "停用",
    "offline": "停用",
    "calibration": "校验中",
    "calibrating": "校验中",
    "scrapped": "报废",
    "scrap": "报废",
}


def normalize_equipment_status(raw: str | None) -> str:
    """将入站状态归一化为快制造允许枚举；未知值映射为待机。"""
    if raw is None:
        return "待机"
    text = str(raw).strip()
    if not text:
        return "待机"
    if text in EQUIPMENT_ALLOWED_STATUSES:
        return text
    alias = _STATUS_ALIASES.get(text.lower())
    if alias:
        return alias
    for allowed in EQUIPMENT_ALLOWED_STATUSES:
        if allowed in text:
            return allowed
    return "待机"
