"""Health check routes for the V2 AI Engine."""

from fastapi import APIRouter

from champiq_v2.config import get_settings

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("")
async def health():
    """Basic health check."""
    cfg = get_settings()
    return {
        "status": "healthy",
        "service": cfg.app_name,
        "version": cfg.app_version,
    }


@router.get("/ready")
async def ready():
    """Readiness check including dependency connectivity."""
    checks: dict[str, bool] = {"neo4j": False, "llm": False, "graphiti": False}
    details: dict[str, str] = {}

    # Check Neo4j
    try:
        from champiq_v2.graph.service import get_graph_service
        graph = await get_graph_service()
        await graph.query("RETURN 1")
        checks["neo4j"] = True
    except Exception as e:
        details["neo4j"] = str(e)

    # Check LLM client
    try:
        from champiq_v2.llm.service import get_llm_service
        llm = get_llm_service()
        checks["llm"] = llm._client is not None
        if not checks["llm"]:
            details["llm"] = "LLM client not initialized"
    except Exception as e:
        details["llm"] = str(e)

    # Check Graphiti
    try:
        from champiq_v2.graph.graphiti_service import get_graphiti_service
        graphiti = await get_graphiti_service()
        checks["graphiti"] = graphiti._initialized
        if not checks["graphiti"]:
            details["graphiti"] = "Graphiti not initialized"
    except Exception as e:
        details["graphiti"] = str(e)

    # Check SMTP
    cfg = get_settings()
    checks["smtp"] = bool(cfg.smtp_host and cfg.smtp_host != "localhost" and cfg.smtp_user)
    if not checks["smtp"]:
        details["smtp"] = "SMTP not configured — emails will be simulated"

    return {
        "ready": checks["neo4j"] and checks["llm"],
        "checks": checks,
        "details": details or None,
    }
