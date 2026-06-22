"""
Telemetry Collector Service — main.py
Receives OTLP logs/traces/metrics and routes to SQLite + ChromaDB.
"""
import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from otel_receiver import OTLPReceiver
from storage import StorageManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("telemetry-collector")

# ─── Config ───────────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///local_data.db")
WEAVIATE_URL = os.getenv("WEAVIATE_URL", "http://localhost:8080")  # ignored; kept for compat
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# ─── Global state ─────────────────────────────────────────────────────────────
storage: StorageManager | None = None
memory_queue: asyncio.Queue = asyncio.Queue()
receiver: OTLPReceiver | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global storage, receiver
    logger.info("Starting Telemetry Collector Service...")

    storage = StorageManager(DATABASE_URL, WEAVIATE_URL, GROQ_API_KEY)
    await storage.initialize()

    receiver = OTLPReceiver(storage, memory_queue)

    # Background task: drain memory queue → storage
    asyncio.create_task(drain_queue_worker())

    logger.info("Telemetry Collector ready ✓")
    yield

    logger.info("Telemetry Collector shut down.")


app = FastAPI(
    title="Telemetry Collector Service",
    description="Receives OpenTelemetry logs/traces/metrics and stores them for incident analysis.",
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
class MetricDataPoint(BaseModel):
    timestamp: float = Field(..., description="Unix timestamp in seconds")
    service: str
    metric_name: str
    value: float
    labels: dict[str, str] = {}


class LogEntry(BaseModel):
    timestamp: float
    service: str
    level: str  # INFO, WARN, ERROR, FATAL
    message: str
    trace_id: str = ""
    span_id: str = ""
    attributes: dict[str, Any] = {}


class TraceSpan(BaseModel):
    trace_id: str
    span_id: str
    parent_span_id: str = ""
    service: str
    operation_name: str
    start_time: float
    duration_ms: float
    status: str  # OK, ERROR
    error_message: str = ""
    attributes: dict[str, Any] = {}


class TelemetryBatch(BaseModel):
    metrics: list[MetricDataPoint] = []
    logs: list[LogEntry] = []
    traces: list[TraceSpan] = []


# ─── Routes ────────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "healthy", "service": "telemetry-collector", "timestamp": time.time()}


@app.post("/v1/telemetry", status_code=202)
async def ingest_telemetry(batch: TelemetryBatch, background_tasks: BackgroundTasks):
    """Primary HTTP endpoint for batched telemetry (logs + traces + metrics)."""
    payload = batch.model_dump()
    await memory_queue.put(payload)
    background_tasks.add_task(_process_immediately, payload)
    return {
        "accepted": True,
        "metrics": len(batch.metrics),
        "logs": len(batch.logs),
        "traces": len(batch.traces),
    }


@app.post("/v1/metrics", status_code=202)
async def ingest_metrics(metrics: list[MetricDataPoint]):
    payload = {"metrics": [m.model_dump() for m in metrics], "logs": [], "traces": []}
    await memory_queue.put(payload)
    return {"accepted": True, "count": len(metrics)}


@app.post("/v1/logs", status_code=202)
async def ingest_logs(logs: list[LogEntry]):
    payload = {"metrics": [], "logs": [l.model_dump() for l in logs], "traces": []}
    await memory_queue.put(payload)
    return {"accepted": True, "count": len(logs)}


@app.post("/v1/traces", status_code=202)
async def ingest_traces(spans: list[TraceSpan]):
    payload = {"metrics": [], "logs": [], "traces": [s.model_dump() for s in spans]}
    await memory_queue.put(payload)
    return {"accepted": True, "count": len(spans)}


@app.get("/v1/metrics/query")
async def query_metrics(
    service: str | None = None,
    metric_name: str | None = None,
    start_time: float | None = None,
    end_time: float | None = None,
    limit: int = 100,
):
    """Query stored metrics from SQLite."""
    results = await storage.query_metrics(service, metric_name, start_time, end_time, limit)
    return {"metrics": results, "count": len(results)}


@app.get("/v1/logs/query")
async def query_logs(
    service: str | None = None,
    level: str | None = None,
    query: str | None = None,
    start_time: float | None = None,
    end_time: float | None = None,
    limit: int = 50,
):
    """Semantic log search via ChromaDB."""
    results = await storage.search_logs(service, level, query, start_time, end_time, limit)
    return {"logs": results, "count": len(results)}


@app.get("/v1/traces/query")
async def query_traces(
    service: str | None = None,
    has_errors: bool = False,
    start_time: float | None = None,
    end_time: float | None = None,
    limit: int = 20,
):
    """Query traces from SQLite."""
    results = await storage.query_traces(service, has_errors, start_time, end_time, limit)
    return {"traces": results, "count": len(results)}


@app.get("/v1/stats")
async def get_stats():
    queue_depth = memory_queue.qsize()
    return {
        "queue_depth": queue_depth,
        "service": "telemetry-collector",
    }


# ─── Background Workers ────────────────────────────────────────────────────────
async def _process_immediately(payload: dict):
    """Process telemetry payload directly to storage (fast path)."""
    try:
        if payload.get("metrics"):
            await storage.write_metrics(payload["metrics"])
        if payload.get("logs"):
            await storage.write_logs(payload["logs"])
        if payload.get("traces"):
            await storage.write_traces(payload["traces"])
    except Exception as e:
        logger.error(f"Error processing telemetry: {e}")


async def drain_queue_worker():
    """Background worker: processes buffered telemetry from memory queue."""
    logger.info("Queue drain worker started")
    while True:
        try:
            payload = await memory_queue.get()
            await _process_immediately(payload)
            memory_queue.task_done()
        except Exception as e:
            logger.error(f"Queue drain error: {e}")
            await asyncio.sleep(1)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=False, workers=1)
