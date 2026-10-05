"""快数采预置点位模板。"""

from __future__ import annotations

from typing import Any

TAG_TEMPLATES: dict[str, dict[str, Any]] = {
    "generic_line": {
        "name": "通用产线",
        "description": "状态 在线 温度 压力 振动",
        "tags": [
            {"tag_key": "status", "name": "设备状态", "value_type": "string", "map_target": "status"},
            {"tag_key": "online", "name": "在线状态", "value_type": "boolean", "map_target": "is_online"},
            {"tag_key": "temp", "name": "温度", "value_type": "number", "map_target": "temperature", "unit": "℃"},
            {"tag_key": "pressure", "name": "压力", "value_type": "number", "map_target": "pressure", "unit": "MPa"},
            {"tag_key": "vibration", "name": "振动", "value_type": "number", "map_target": "vibration", "unit": "mm/s"},
        ],
        "events": [
            {"event_key": "fault", "name": "设备故障", "level": "critical"},
            {"event_key": "mold_change", "name": "换模", "level": "info"},
        ],
    },
    "injection_molding": {
        "name": "注塑机",
        "description": "注塑机常用采集点位",
        "tags": [
            {"tag_key": "status", "name": "运行状态", "value_type": "string", "map_target": "status"},
            {"tag_key": "online", "name": "在线", "value_type": "boolean", "map_target": "is_online"},
            {"tag_key": "barrel_temp", "name": "料筒温度", "value_type": "number", "map_target": "temperature", "unit": "℃"},
            {"tag_key": "mold_pressure", "name": "模腔压力", "value_type": "number", "map_target": "pressure", "unit": "MPa"},
            {"tag_key": "cycle_time", "name": "周期", "value_type": "number", "map_target": "other_parameters.cycle_time", "unit": "s"},
        ],
        "events": [
            {"event_key": "fault", "name": "设备故障", "level": "critical"},
            {"event_key": "mold_change", "name": "换模", "level": "info"},
        ],
    },
    "cnc": {
        "name": "CNC 机床",
        "description": "CNC 常用采集点位",
        "tags": [
            {"tag_key": "status", "name": "运行状态", "value_type": "string", "map_target": "status"},
            {"tag_key": "online", "name": "在线", "value_type": "boolean", "map_target": "is_online"},
            {"tag_key": "spindle_speed", "name": "主轴转速", "value_type": "number", "map_target": "other_parameters.spindle_speed", "unit": "rpm"},
            {"tag_key": "feed_rate", "name": "进给速度", "value_type": "number", "map_target": "other_parameters.feed_rate", "unit": "mm/min"},
            {"tag_key": "load", "name": "负载", "value_type": "number", "map_target": "vibration", "unit": "%"},
        ],
        "events": [
            {"event_key": "fault", "name": "设备故障", "level": "critical"},
            {"event_key": "tool_change", "name": "换刀", "level": "info"},
        ],
    },
    "sanyi_plc_line": {
        "name": "三易产线 PLC",
        "description": "三易 MQTT 产线快照（devices[].variables），含产量/稼动率/时间类点位",
        "tags": [
            {"tag_key": "online", "name": "在线", "value_type": "boolean", "map_target": "is_online"},
            {"tag_key": "status", "name": "采集状态", "value_type": "string", "map_target": "other_parameters.device_status"},
            {"tag_key": "exception", "name": "异常信息", "value_type": "string", "map_target": "other_parameters.exception"},
            {"tag_key": "sczq", "name": "生产周期", "value_type": "number", "map_target": "other_parameters.sczq"},
            {"tag_key": "hgcl", "name": "合格产量", "value_type": "number", "map_target": "other_parameters.hgcl"},
            {"tag_key": "hgl", "name": "合格率", "value_type": "number", "map_target": "other_parameters.hgl", "unit": "%"},
            {"tag_key": "blsl", "name": "不良数量", "value_type": "number", "map_target": "other_parameters.blsl"},
            {"tag_key": "zscl", "name": "总生产量", "value_type": "number", "map_target": "other_parameters.zscl"},
            {"tag_key": "dbcl", "name": "当班产量", "value_type": "number", "map_target": "other_parameters.dbcl"},
            {"tag_key": "xscl", "name": "小时产量", "value_type": "number", "map_target": "other_parameters.xscl"},
            {"tag_key": "bzcn", "name": "标准产能", "value_type": "number", "map_target": "other_parameters.bzcn"},
            {"tag_key": "cnjdl", "name": "产能稼动率", "value_type": "number", "map_target": "other_parameters.cnjdl", "unit": "%"},
            {"tag_key": "jdl", "name": "稼动率", "value_type": "number", "map_target": "other_parameters.jdl", "unit": "%"},
            {"tag_key": "qdsj_zsj_s", "name": "启动总时间_秒", "value_type": "number", "map_target": "other_parameters.qdsj_zsj_s", "unit": "s"},
            {"tag_key": "qdsj_zsj_m", "name": "启动总时间_分", "value_type": "number", "map_target": "other_parameters.qdsj_zsj_m", "unit": "min"},
            {"tag_key": "qdsj_zsj_h", "name": "启动总时间_时", "value_type": "number", "map_target": "other_parameters.qdsj_zsj_h", "unit": "h"},
            {"tag_key": "qdsj_yxsj_s", "name": "运行时间_秒", "value_type": "number", "map_target": "other_parameters.qdsj_yxsj_s", "unit": "s"},
            {"tag_key": "qdsj_yxsj_m", "name": "运行时间_分", "value_type": "number", "map_target": "other_parameters.qdsj_yxsj_m", "unit": "min"},
            {"tag_key": "qdsj_yxsj_h", "name": "运行时间_时", "value_type": "number", "map_target": "other_parameters.qdsj_yxsj_h", "unit": "h"},
            {"tag_key": "ztjsj_s", "name": "总停机时间_秒", "value_type": "number", "map_target": "other_parameters.ztjsj_s", "unit": "s"},
            {"tag_key": "ztjsj_m", "name": "总停机时间_分", "value_type": "number", "map_target": "other_parameters.ztjsj_m", "unit": "min"},
            {"tag_key": "ztjsj_h", "name": "总停机时间_时", "value_type": "number", "map_target": "other_parameters.ztjsj_h", "unit": "h"},
            {"tag_key": "qdsj_qlsj_s", "name": "缺料时间_秒", "value_type": "number", "map_target": "other_parameters.qdsj_qlsj_s", "unit": "s"},
            {"tag_key": "qdsj_qlsj_m", "name": "缺料时间_分", "value_type": "number", "map_target": "other_parameters.qdsj_qlsj_m", "unit": "min"},
            {"tag_key": "qdsj_qlsj_h", "name": "缺料时间_时", "value_type": "number", "map_target": "other_parameters.qdsj_qlsj_h", "unit": "h"},
            {"tag_key": "tjsj_bjsj_s", "name": "报警时间_秒", "value_type": "number", "map_target": "other_parameters.tjsj_bjsj_s", "unit": "s"},
            {"tag_key": "tjsj_bjsj_m", "name": "报警时间_分", "value_type": "number", "map_target": "other_parameters.tjsj_bjsj_m", "unit": "min"},
            {"tag_key": "tjsj_bjsj_h", "name": "报警时间_时", "value_type": "number", "map_target": "other_parameters.tjsj_bjsj_h", "unit": "h"},
            {"tag_key": "tjsj_qtsj_s", "name": "其他停机_秒", "value_type": "number", "map_target": "other_parameters.tjsj_qtsj_s", "unit": "s"},
            {"tag_key": "tjsj_qtsj_m", "name": "其他停机_分", "value_type": "number", "map_target": "other_parameters.tjsj_qtsj_m", "unit": "min"},
            {"tag_key": "tjsj_qtsj_h", "name": "其他停机_时", "value_type": "number", "map_target": "other_parameters.tjsj_qtsj_h", "unit": "h"},
            {"tag_key": "qdsj_mlsj_s", "name": "满料时间_秒", "value_type": "number", "map_target": "other_parameters.qdsj_mlsj_s", "unit": "s"},
            {"tag_key": "qdsj_mlsj_m", "name": "满料时间_分", "value_type": "number", "map_target": "other_parameters.qdsj_mlsj_m", "unit": "min"},
            {"tag_key": "qdsj_mlsj_h", "name": "满料时间_时", "value_type": "number", "map_target": "other_parameters.qdsj_mlsj_h", "unit": "h"},
        ],
        "events": [
            {"event_key": "fault", "name": "设备故障", "level": "critical"},
            {"event_key": "material_shortage", "name": "缺料", "level": "warning"},
        ],
    },
}
