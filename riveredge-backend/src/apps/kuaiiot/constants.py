"""快数采常量与枚举。"""

from __future__ import annotations

CONNECTION_TYPES = frozenset({"mqtt", "thingsboard", "jetlinks", "http_webhook"})

TAG_VALUE_TYPES = frozenset({"string", "number", "boolean"})

MAP_TARGETS = frozenset(
    {
        "status",
        "temperature",
        "pressure",
        "vibration",
        "is_online",
    }
)

FILL_TARGET_PREFIXES = (
    "sop_parameters.",
    "other_parameters.",
    "process_params.",
)

EVENT_LEVELS = frozenset({"info", "warning", "critical"})

ALERT_RULE_TYPES = frozenset({"threshold", "offline"})
ALERT_OPERATORS = frozenset({"gt", "lt", "gte", "lte", "eq", "ne"})
ALERT_SEVERITIES = frozenset({"info", "warning", "critical"})
OFFLINE_ALERT_TAG_KEY = "__offline__"
EVENT_ALERT_TAG_PREFIX = "event:"

EDGE_PROTOCOLS = frozenset({"modbus_tcp", "modbus_rtu", "opc_ua", "s7"})
MODBUS_DATA_TYPES = frozenset({"int16", "uint16", "int32", "uint32", "float32", "bool"})

INGEST_THROTTLE_SECONDS = 5
INGEST_MAX_TAGS_PER_PAYLOAD = 200
INGEST_BATCH_MAX_ITEMS = 100
INGEST_DEDUP_RETENTION_DAYS = 7

OFFLINE_THRESHOLD_SECONDS = 300
EDGE_AGENT_OFFLINE_SECONDS = 120

DEVICE_BATCH_MAX = 100

ALERT_RETENTION_DAYS = 90
MESSAGE_LOG_RETENTION_DAYS = 30
MESSAGE_LOG_PAYLOAD_MAX = 4000
MESSAGE_DIRECTIONS = frozenset({"inbound", "outbound"})
MESSAGE_TYPES = frozenset({"ingest", "command", "heartbeat", "sync", "other"})
MESSAGE_RESULTS = frozenset({"success", "failed", "timeout", "skipped"})

COMMAND_DEFAULT_TIMEOUT_SECONDS = 30
COMMAND_STATUSES = frozenset({"pending", "sent", "success", "failed", "timeout"})
DISPATCH_CHANNELS = frozenset({"http", "mqtt", "edge"})

TSDB_INTEGRATION_CODE = "kuaiiot_tsdb"

MES_DATA_SOURCE = "sensor"
