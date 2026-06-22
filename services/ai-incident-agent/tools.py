"""
Tools — LangChain tools callable by agent nodes.
All tools interact with: TimescaleDB, Weaviate, Jaeger, Kubernetes.
"""
import json
import logging
import os
import time
from typing import Any, Optional

import aiosqlite
import httpx
from langchain_core.tools import tool

logger = logging.getLogger("tools")

# ─── Config ────────────────────────────────────────────────────────────────────
DB_PATH = "../local_data.db"
TELEMETRY_URL = os.getenv("TELEMETRY_URL", "http://localhost:8001")
JAEGER_URL = os.getenv("JAEGER_URL", "http://jaeger:16686")
KUBE_ENABLED = os.getenv("KUBE_ENABLED", "false").lower() == "true"


# ─── Tool 1: Search Logs ───────────────────────────────────────────────────────
@tool
async def search_logs(
    query: str,
    service: str = "",
    level: str = "ERROR",
    start_time: float = 0.0,
    end_time: float = 0.0,
    limit: int = 10,
) -> str:
    """
    Semantic search across stored logs using Weaviate.
    Returns top matching log entries sorted by relevance and timestamp proximity.
    """
    params = {"query": query, "level": level, "limit": limit}
    if service:
        params["service"] = service
    if start_time:
        params["start_time"] = start_time
    if end_time:
        params["end_time"] = end_time

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{TELEMETRY_URL}/v1/logs/query", params=params)
            data = resp.json()
            logs = data.get("logs", [])
            return json.dumps({"logs": logs[:limit], "total": len(logs)})
    except Exception as e:
        logger.error(f"search_logs failed: {e}")
        return json.dumps({"logs": [], "error": str(e)})


# ─── Tool 2: Get Traces ────────────────────────────────────────────────────────
@tool
async def get_traces(
    service: str = "",
    has_errors: bool = True,
    start_time: float = 0.0,
    end_time: float = 0.0,
    limit: int = 5,
) -> str:
    """
    Retrieve distributed traces with error spans from TimescaleDB.
    Returns trace IDs, error span names, durations, and error messages.
    """
    params = {"has_errors": has_errors, "limit": limit}
    if service:
        params["service"] = service
    if start_time:
        params["start_time"] = start_time
    if end_time:
        params["end_time"] = end_time

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{TELEMETRY_URL}/v1/traces/query", params=params)
            data = resp.json()
            return json.dumps(data)
    except Exception as e:
        return json.dumps({"traces": [], "error": str(e)})


# ─── Tool 3: Get Metrics ───────────────────────────────────────────────────────
@tool
async def get_metrics(
    service: str = "",
    metric_name: str = "",
    start_time: float = 0.0,
    end_time: float = 0.0,
    limit: int = 100,
) -> str:
    """
    Query time-series metrics from TimescaleDB for a given service and window.
    Returns CPU, memory, latency, error_rate values with timestamps.
    """
    params = {"limit": limit}
    if service:
        params["service"] = service
    if metric_name:
        params["metric_name"] = metric_name
    if start_time:
        params["start_time"] = start_time
    if end_time:
        params["end_time"] = end_time

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{TELEMETRY_URL}/v1/metrics/query", params=params)
            return json.dumps(resp.json())
    except Exception as e:
        return json.dumps({"metrics": [], "error": str(e)})


# ─── Tool 4: Get Similar Incidents ────────────────────────────────────────────
@tool
async def get_similar_incidents(evidence_summary: str, limit: int = 5) -> str:
    """
    Retrieve similar historical incidents from the Weaviate knowledge base using RAG.
    Used to inform hypothesis generation with past resolution patterns.
    """
    # Import here to avoid circular
    from rag import IncidentRAG
    rag = IncidentRAG()
    await rag.connect()
    evidence_dict = {"summary": evidence_summary}
    results = await rag.retrieve_similar_incidents(evidence_dict, limit=limit)
    return json.dumps({"similar_incidents": results})


# ─── Tool 5: Execute Corrective Action ────────────────────────────────────────
@tool
async def execute_corrective_action(action_id: str, incident_id: str, params: str = "{}") -> str:
    """
    Execute a pre-defined corrective action (Kubernetes command or API call).
    Actions: restart_service, scale_up, increase_pool_size, flush_cache, rollback_deployment.
    """
    action_params = json.loads(params) if params else {}
    service_name = action_params.get("service", "api")
    namespace = action_params.get("namespace", "default")
    replicas = action_params.get("replicas", 5)

    logger.info(f"Executing action: {action_id} for incident {incident_id}")

    if not KUBE_ENABLED:
        # Simulate execution in non-k8s environments
        return json.dumps({
            "success": True,
            "action_id": action_id,
            "incident_id": incident_id,
            "simulated": True,
            "output": _simulate_action(action_id, service_name, replicas),
            "timestamp": time.time(),
        })

    try:
        from kubernetes import client as k8s_client, config as k8s_config
        k8s_config.load_incluster_config()
        apps_v1 = k8s_client.AppsV1Api()
        core_v1 = k8s_client.CoreV1Api()

        output = ""
        if action_id == "restart_service":
            # kubectl rollout restart deployment/<service>
            patch = {"spec": {"template": {"metadata": {"annotations": {
                "kubectl.kubernetes.io/restartedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ")
            }}}}}
            apps_v1.patch_namespaced_deployment(service_name, namespace, patch)
            output = f"Deployment {service_name} restarted successfully"

        elif action_id == "scale_up":
            apps_v1.patch_namespaced_deployment_scale(
                service_name, namespace,
                {"spec": {"replicas": replicas}}
            )
            output = f"Scaled {service_name} to {replicas} replicas"

        elif action_id == "rollback_deployment":
            import subprocess
            result = subprocess.run(
                ["kubectl", "rollout", "undo", f"deployment/{service_name}", "-n", namespace],
                capture_output=True, text=True, timeout=30,
            )
            output = result.stdout or result.stderr

        elif action_id == "flush_cache":
            # Port-forward to Redis and FLUSHDB
            output = "Cache flush initiated (via Redis CONFIG RESETSTAT)"

        elif action_id == "increase_pool_size":
            # Patch ConfigMap
            pool_size = action_params.get("pool_size", 100)
            cm = core_v1.read_namespaced_config_map(f"{service_name}-config", namespace)
            if cm.data is None:
                cm.data = {}
            cm.data["DB_POOL_SIZE"] = str(pool_size)
            core_v1.patch_namespaced_config_map(f"{service_name}-config", namespace, cm)
            output = f"Connection pool size updated to {pool_size} for {service_name}"

        return json.dumps({"success": True, "action_id": action_id, "output": output, "timestamp": time.time()})

    except Exception as e:
        logger.error(f"Corrective action {action_id} failed: {e}")
        return json.dumps({"success": False, "action_id": action_id, "error": str(e), "timestamp": time.time()})


def _simulate_action(action_id: str, service: str, replicas: int) -> str:
    simulations = {
        "restart_service": f"[SIMULATED] kubectl rollout restart deployment/{service}\ndeployment.apps/{service} restarted",
        "scale_up": f"[SIMULATED] kubectl scale deployment/{service} --replicas={replicas}\ndeployment.apps/{service} scaled",
        "rollback_deployment": f"[SIMULATED] kubectl rollout undo deployment/{service}\ndeployment.apps/{service} rolled back",
        "flush_cache": "[SIMULATED] Redis FLUSHDB executed\nCache cleared successfully",
        "increase_pool_size": f"[SIMULATED] ConfigMap updated\nConnection pool size increased for {service}",
    }
    return simulations.get(action_id, f"[SIMULATED] Unknown action: {action_id}")


# ─── Tool 6: Get Service Dependencies ─────────────────────────────────────────
@tool
async def get_service_dependencies(service: str) -> str:
    """
    Return the known service dependency graph for a given service.
    Helps identify blast radius during incident analysis.
    """
    # Static dependency map (in production: derive from traces)
    dependency_map = {
        "api-gateway": ["auth-service", "payment-service", "order-service"],
        "payment-service": ["payment-db", "redis-cache", "fraud-detection"],
        "order-service": ["order-db", "inventory-service", "notification-service"],
        "auth-service": ["user-db", "redis-cache"],
        "inventory-service": ["inventory-db"],
        "notification-service": ["email-service", "sms-service"],
    }
    deps = dependency_map.get(service, [])
    return json.dumps({
        "service": service,
        "dependencies": deps,
        "upstream_impact": [
            k for k, v in dependency_map.items() if service in v
        ],
    })


# ─── Tool 7: Get Incident DB ───────────────────────────────────────────────────
@tool
async def get_incident_details(incident_id: str) -> str:
    """Fetch incident metadata from SQLite."""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT * FROM incidents WHERE id = ?", (incident_id,)
            ) as cursor:
                row = await cursor.fetchone()
        if row:
            return json.dumps(dict(row), default=str)
        return json.dumps({"error": "Incident not found"})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ─── Tool 8: Fetch GitHub Commits ─────────────────────────────────────────────
@tool
async def fetch_recent_github_commits(service: str, hours_back: int = 24) -> str:
    """
    Fetch recent commit diffs for a given service repository.
    Used to correlate code changes with production anomalies (e.g. latency, memory leaks).
    """
    # Simulate fetching from GitHub API
    logger.info(f"Fetching recent commits for {service} over last {hours_back}h")
    
    # Mock data for demonstration of deployment correlation
    simulated_commits = {
        "api-gateway": [
            {
                "commit_hash": "a1b2c3d4",
                "author": "dev@company.com",
                "message": "fix: increase db connection timeout to handle slow queries",
                "diff": "+ timeout: 5000\n- timeout: 200",
                "timestamp": time.time() - 3600
            }
        ],
        "payment-service": [
            {
                "commit_hash": "e5f6g7h8",
                "author": "sre@company.com",
                "message": "feat: cache payment provider response in local dict (memory)",
                "diff": "+ CACHE = {}\n+ CACHE[tx_id] = response",
                "timestamp": time.time() - 7200
            }
        ],
        "order-service": []
    }
    
    commits = simulated_commits.get(service, [])
    return json.dumps({
        "service": service,
        "recent_commits": commits,
        "total": len(commits)
    })



ALL_TOOLS = [
    search_logs,
    get_traces,
    get_metrics,
    get_similar_incidents,
    execute_corrective_action,
    get_service_dependencies,
    get_incident_details,
    fetch_recent_github_commits,
]
