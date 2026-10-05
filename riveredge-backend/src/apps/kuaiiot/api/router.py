"""快数采 API 路由。"""

from fastapi import APIRouter

from .alerts import router as alerts_router
from .analytics import router as analytics_router
from .config import router as config_router
from .connections import router as connections_router
from .connectors import router as connectors_router
from .dashboard import router as dashboard_router
from .device_groups import router as device_groups_router
from .devices import router as devices_router
from .edge_configs import router as edge_configs_router
from .edge_runtime import router as edge_runtime_router
from .fill_context import router as fill_context_router
from .ingest import router as ingest_router
from .ops import router as ops_router
from .products import router as products_router
from .tags import router as tags_router

router = APIRouter(tags=["App - KuaiIoT - Overview"])

router.include_router(connections_router)
router.include_router(config_router)
router.include_router(products_router)
router.include_router(device_groups_router)
router.include_router(devices_router)
router.include_router(tags_router)
router.include_router(dashboard_router)
router.include_router(ingest_router)
router.include_router(connectors_router)
router.include_router(alerts_router)
router.include_router(edge_configs_router)
router.include_router(edge_runtime_router)
router.include_router(analytics_router)
router.include_router(ops_router)
router.include_router(fill_context_router)


@router.get("/health")
async def health_check():
    return {"status": "ok", "app": "kuaiiot"}
