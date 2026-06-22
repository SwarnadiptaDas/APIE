"""
AI Incident Agent Service — FastAPI + WebSocket + HTTP event receiver.
"""
import asyncio
import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

import aiosqlite
import uvicorn
from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agents import run_incident_analysis
from rag import IncidentRAG

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("ai-incident-agent")

DB_PATH = "../local_data.db"

# ─── Global State ─────────────────────────────────────────────────────────────
rag: IncidentRAG | None = None
active_incidents: dict[str, dict] = {}  # in-memory cache
ws_connections: list[WebSocket] = []  # active WebSocket clients


@asynccontextmanager
async def lifespan(app: FastAPI):
    global rag
    logger.info("Starting AI Incident Agent Service...")

    try:
        await _ensure_schema()
    except Exception as e:
        logger.warning(f"SQLite init failed: {e}")

    rag = IncidentRAG()
    await rag.connect()

    logger.info("AI Incident Agent ready ✓")
    yield


app = FastAPI(
    title="AI Incident Agent",
    description="Multi-agent AI system for autonomous production incident analysis.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Models ────────────────────────────────────────────────────────────────────
class TriggerIncidentRequest(BaseModel):
    service: str = "api-gateway"
    metric_name: str = "latency_p95_ms"
    severity: str = "critical"
    value: float = 8500.0
    affected_services: list[str] = ["api-gateway", "payment-service"]
    anomaly_data: dict[str, Any] = {}


class ActionRequest(BaseModel):
    params: dict[str, Any] = {}


# ─── Routes ────────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "healthy", "service": "ai-incident-agent", "timestamp": time.time()}


@app.post("/incidents/trigger", status_code=202)
async def trigger_incident(req: TriggerIncidentRequest, background_tasks: BackgroundTasks):
    """Manually trigger an incident investigation workflow."""
    incident_id = str(uuid.uuid4())
    incident = {
        "id": incident_id,
        "title": f"Manual Trigger: {req.metric_name} anomaly in {req.service}",
        "status": "investigating",
        "severity": req.severity,
        "detected_at": time.time(),
        "affected_services": req.affected_services,
        "anomaly_data": {
            **req.anomaly_data,
            "service": req.service,
            "metric_name": req.metric_name,
            "value": req.value,
        },
        "analysis_result": {},
        "postmortem": "",
    }
    active_incidents[incident_id] = incident
    await _save_incident(incident)

    # Notify WebSocket clients
    await _broadcast_ws({"event": "incident_created", "incident": incident})

    # Run analysis in background
    background_tasks.add_task(_analyze_incident, incident_id, incident)
    return {"incident_id": incident_id, "status": "investigation_started"}


@app.get("/incidents/")
async def list_incidents(limit: int = 50):
    """List all incidents from DB."""
    incidents = await _load_incidents(limit)
    return {"incidents": incidents, "total": len(incidents)}


@app.get("/incidents/{incident_id}")
async def get_incident(incident_id: str):
    """Get full incident details including analysis result."""
    # Check in-memory cache first
    if incident_id in active_incidents:
        return active_incidents[incident_id]
    incidents = await _load_incidents_by_id(incident_id)
    if not incidents:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incidents[0]


@app.post("/incidents/{incident_id}/actions/{action_id}")
async def execute_action(incident_id: str, action_id: str, req: ActionRequest, background_tasks: BackgroundTasks):
    """Execute a corrective action for an incident."""
    from tools import execute_corrective_action

    result = await execute_corrective_action.ainvoke({
        "action_id": action_id,
        "incident_id": incident_id,
        "params": json.dumps(req.params),
    })
    result_data = json.loads(result)

    # Update incident with action taken
    if incident_id in active_incidents:
        actions = active_incidents[incident_id].get("corrective_actions_taken", [])
        actions.append({
            "action_id": action_id,
            "result": result_data,
            "executed_at": time.time(),
        })
        active_incidents[incident_id]["corrective_actions_taken"] = actions

    await _broadcast_ws({"event": "action_executed", "incident_id": incident_id, "result": result_data})
    return result_data


@app.post("/incidents/{incident_id}/resolve")
async def resolve_incident(incident_id: str):
    """Mark incident as resolved and store to RAG knowledge base."""
    if incident_id not in active_incidents:
        raise HTTPException(status_code=404, detail="Incident not found")

    incident = active_incidents[incident_id]
    incident["status"] = "resolved"
    incident["resolved_at"] = time.time()
    incident["resolution_minutes"] = int((time.time() - incident["detected_at"]) / 60)

    await _save_incident(incident)

    # Store to RAG knowledge base for future retrieval
    if rag:
        await rag.embed_and_store_incident(incident)

    await _broadcast_ws({"event": "incident_resolved", "incident_id": incident_id})
    return {"status": "resolved", "resolution_minutes": incident["resolution_minutes"]}


@app.get("/incidents/{incident_id}/postmortem")
async def get_postmortem(incident_id: str):
    """Get the auto-generated postmortem for an incident."""
    if incident_id in active_incidents:
        postmortem = active_incidents[incident_id].get("postmortem", "")
        if postmortem:
            return {"incident_id": incident_id, "postmortem": postmortem}
    incidents = await _load_incidents_by_id(incident_id)
    if not incidents:
        raise HTTPException(status_code=404, detail="Incident not found")
    return {"incident_id": incident_id, "postmortem": incidents[0].get("postmortem", "Not yet generated")}


@app.get("/stats")
async def get_stats():
    return {
        "active_incidents": len([i for i in active_incidents.values() if i.get("status") == "investigating"]),
        "total_incidents_cached": len(active_incidents),
        "ws_connections": len(ws_connections),
    }


# ─── WebSocket ─────────────────────────────────────────────────────────────────
@app.websocket("/ws/incidents")
async def ws_incidents(websocket: WebSocket):
    """Real-time incident event stream for the dashboard."""
    await websocket.accept()
    ws_connections.append(websocket)
    logger.info(f"WebSocket client connected ({len(ws_connections)} total)")

    # Send current incidents on connect
    incidents = list(active_incidents.values())[-20:]
    await websocket.send_json({"event": "initial_state", "incidents": incidents})

    try:
        while True:
            # Keep connection alive with ping
            await asyncio.sleep(30)
            await websocket.send_json({"event": "ping", "timestamp": time.time()})
    except WebSocketDisconnect:
        ws_connections.remove(websocket)
        logger.info(f"WebSocket client disconnected ({len(ws_connections)} remaining)")


# ─── HTTP Anomaly Event Receiver ───────────────────────────────────────────────
@app.post("/incidents/internal_trigger")
async def internal_trigger(event: dict = Body(...)):
    """Receive anomaly events via HTTP POST from Anomaly Detection Service."""
    try:
        await _handle_anomaly_event(event)
        return {"status": "event_received"}
    except Exception as e:
        logger.error(f"Failed to process internal trigger: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _handle_anomaly_event(event: dict):
    """Convert anomaly event to incident and trigger analysis."""
    incident_id = event.get("incident_id", str(uuid.uuid4()))

    # Deduplicate
    if incident_id in active_incidents:
        return

    incident = {
        "id": incident_id,
        "title": f"Anomaly: {event.get('metric_name', 'unknown')} in {event.get('service', 'unknown')}",
        "status": "investigating",
        "severity": event.get("severity", "warning"),
        "detected_at": event.get("detected_at", time.time()),
        "affected_services": [event.get("service", "unknown")],
        "anomaly_data": event,
        "analysis_result": {},
        "postmortem": "",
    }
    active_incidents[incident_id] = incident
    await _save_incident(incident)
    await _broadcast_ws({"event": "incident_created", "incident": incident})

    # Trigger analysis
    asyncio.create_task(_analyze_incident(incident_id, incident))


async def _analyze_incident(incident_id: str, incident: dict):
    """Run the full 4-agent analysis pipeline."""
    logger.info(f"Starting analysis for incident {incident_id}")
    try:
        result = await run_incident_analysis(
            incident_id=incident_id,
            timestamp=incident["detected_at"],
            affected_services=incident.get("affected_services", []),
            severity=incident.get("severity", "warning"),
            anomaly_data=incident.get("anomaly_data", {}),
        )

        if incident_id in active_incidents:
            active_incidents[incident_id].update({
                "status": "analyzed",
                "analysis_result": result,
                "postmortem": result.get("postmortem", ""),
                "title": result.get("title", incident["title"]),
            })

        await _save_incident(active_incidents.get(incident_id, incident))
        await _broadcast_ws({"event": "analysis_complete", "incident_id": incident_id, "result": result})
        logger.info(f"Analysis complete for incident {incident_id}")

    except Exception as e:
        logger.error(f"Analysis failed for {incident_id}: {e}", exc_info=True)
        if incident_id in active_incidents:
            active_incidents[incident_id]["status"] = "failed"
            active_incidents[incident_id]["error"] = str(e)
        await _broadcast_ws({"event": "analysis_failed", "incident_id": incident_id, "error": str(e)})


async def _broadcast_ws(message: dict):
    """Send a message to all connected WebSocket clients."""
    dead = []
    for ws in ws_connections:
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(ws)
    for d in dead:
        if d in ws_connections:
            ws_connections.remove(d)


# ─── DB Helpers ────────────────────────────────────────────────────────────────
async def _ensure_schema():
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS incidents (
                id              TEXT PRIMARY KEY,
                title           TEXT NOT NULL,
                status          TEXT NOT NULL DEFAULT 'open',
                severity        TEXT NOT NULL DEFAULT 'warning',
                detected_at     REAL NOT NULL,
                resolved_at     REAL,
                affected_services TEXT DEFAULT '[]',
                anomaly_data    TEXT DEFAULT '{}',
                analysis_result TEXT DEFAULT '{}',
                postmortem      TEXT DEFAULT '',
                created_at      REAL,
                updated_at      REAL
            );
        """)
        await conn.commit()


async def _save_incident(incident: dict):
    try:
        now = time.time()
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute(
                """
                INSERT INTO incidents
                  (id, title, status, severity, detected_at, resolved_at, affected_services,
                   anomaly_data, analysis_result, postmortem, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (id) DO UPDATE SET
                  status = excluded.status,
                  resolved_at = excluded.resolved_at,
                  analysis_result = excluded.analysis_result,
                  postmortem = excluded.postmortem,
                  updated_at = excluded.updated_at
                """,
                (
                    incident["id"],
                    incident.get("title", "Untitled"),
                    incident.get("status", "open"),
                    incident.get("severity", "warning"),
                    incident.get("detected_at", now),
                    incident.get("resolved_at"),
                    json.dumps(incident.get("affected_services", [])),
                    json.dumps(incident.get("anomaly_data", {})),
                    json.dumps(incident.get("analysis_result", {})),
                    incident.get("postmortem", ""),
                    incident.get("created_at", now),
                    now
                )
            )
            await conn.commit()
    except Exception as e:
        logger.error(f"Failed to save incident {incident.get('id')}: {e}")


async def _load_incidents(limit: int) -> list[dict]:
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT * FROM incidents ORDER BY detected_at DESC LIMIT ?", (limit,)
            ) as cursor:
                rows = await cursor.fetchall()
        
        results = []
        for r in rows:
            d = dict(r)
            for key in ["affected_services", "anomaly_data", "analysis_result"]:
                if d.get(key):
                    try:
                        d[key] = json.loads(d[key])
                    except Exception:
                        pass
            results.append(d)
        return results
    except Exception as e:
        logger.error(f"Failed to load incidents: {e}")
        return list(active_incidents.values())[-limit:]


async def _load_incidents_by_id(incident_id: str) -> list[dict]:
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT * FROM incidents WHERE id = ?", (incident_id,)
            ) as cursor:
                rows = await cursor.fetchall()
        
        results = []
        for r in rows:
            d = dict(r)
            for key in ["affected_services", "anomaly_data", "analysis_result"]:
                if d.get(key):
                    try:
                        d[key] = json.loads(d[key])
                    except Exception:
                        pass
            results.append(d)
        return results
    except Exception as e:
        logger.error(f"Failed to load incident by id: {e}")
        return []


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
