"""
Anomaly Detection Service — FastAPI + background scheduler.
"""
import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager

import aiosqlite
import httpx
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from detector import AnomalyDetector

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("anomaly-detection")

DB_PATH = "../local_data.db"
TELEMETRY_URL = os.getenv("TELEMETRY_URL", "http://telemetry-collector:8001")
DETECTION_INTERVAL = int(os.getenv("DETECTION_INTERVAL_SECONDS", "15"))
AGENT_URL = os.getenv("AGENT_URL", "http://localhost:8000")

detector: AnomalyDetector | None = None
stats = {"anomalies_detected": 0, "batches_processed": 0, "last_run_ts": 0.0}

@asynccontextmanager
async def lifespan(app: FastAPI):
    global detector
    logger.info("Starting Anomaly Detection Service...")

    detector = AnomalyDetector(agent_url=AGENT_URL)

    # Seed model with synthetic historical data on first start
    await _seed_model()

    # Start background detection loop
    asyncio.create_task(detection_loop())
    logger.info(f"Anomaly Detection ready ✓ (interval={DETECTION_INTERVAL}s)")
    yield



app = FastAPI(
    title="Anomaly Detection Service",
    description="Real-time anomaly detection using Isolation Forest on time-series metrics.",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "anomaly-detection", "timestamp": time.time()}


@app.get("/stats")
async def get_stats():
    return stats


@app.post("/detect")
async def trigger_detection():
    """Manually trigger a detection run (useful for testing)."""
    metrics = await _fetch_recent_metrics()
    anomalies = await detector.process_metrics(metrics)
    published = []
    for anomaly in anomalies:
        event = await detector.publish_anomaly(anomaly)
        if event:
            published.append(event)
    return {"anomalies_found": len(anomalies), "published": len(published), "metrics_checked": len(metrics)}


@app.get("/model/info")
async def model_info():
    return {
        "is_trained": detector.if_detector.is_trained if detector else False,
        "contamination": detector.if_detector.contamination if detector else None,
        "n_estimators": detector.if_detector.n_estimators if detector else None,
    }


@app.post("/model/retrain")
async def retrain_model():
    """Retrain the Isolation Forest on recent historical data."""
    import numpy as np
    metrics = await _fetch_historical_metrics(days=7)
    if len(metrics) < 50:
        return {"status": "insufficient_data", "count": len(metrics)}

    # Build feature matrix
    service_groups: dict[str, list] = {}
    for m in metrics:
        svc = m["service"]
        service_groups.setdefault(svc, []).append(m)

    X_list = []
    for svc, svc_metrics in service_groups.items():
        feature_vec = _metrics_to_features(svc_metrics)
        if feature_vec:
            X_list.append(feature_vec)

    if not X_list:
        return {"status": "no_feature_vectors"}

    X = np.array(X_list)
    detector.if_detector.train(X)
    return {"status": "retrained", "samples": len(X_list)}


# ─── Background Detection Loop ─────────────────────────────────────────────────
async def detection_loop():
    """Poll TimescaleDB every DETECTION_INTERVAL seconds and run anomaly detection."""
    logger.info("Detection loop started")
    while True:
        try:
            await _run_detection_cycle()
        except Exception as e:
            logger.error(f"Detection cycle error: {e}")
        await asyncio.sleep(DETECTION_INTERVAL)


async def _run_detection_cycle():
    metrics = await _fetch_recent_metrics()
    if not metrics:
        return

    stats["batches_processed"] += 1
    stats["last_run_ts"] = time.time()

    anomalies = await detector.process_metrics(metrics)
    for anomaly in anomalies:
        event = await detector.publish_anomaly(anomaly)
        if event:
            stats["anomalies_detected"] += 1
            logger.info(f"Published anomaly event: {json.dumps(event, indent=2)}")


async def _fetch_recent_metrics(window_seconds: int = 60) -> list[dict]:
    """Fetch metrics from SQLite for the last window_seconds."""
    try:
        start_ts = time.time() - window_seconds
        async with aiosqlite.connect(DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                """
                SELECT time as timestamp, service, metric_name, value, labels
                FROM metrics
                WHERE time >= ?
                ORDER BY time DESC
                LIMIT 1000
                """,
                (start_ts,),
            ) as cursor:
                rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Failed to fetch metrics: {e}")
        return []


async def _fetch_historical_metrics(days: int = 7) -> list[dict]:
    """Fetch historical metrics from SQLite for the last few days."""
    try:
        start_ts = time.time() - (days * 86400)
        async with aiosqlite.connect(DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                """
                SELECT time as timestamp, service, metric_name, value
                FROM metrics
                WHERE time >= ?
                ORDER BY time ASC
                LIMIT 10000
                """,
                (start_ts,),
            ) as cursor:
                rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Failed to fetch historical metrics: {e}")
        return []


def _metrics_to_features(metrics: list[dict]) -> list[float] | None:
    """Convert a group of service metrics to a feature vector [cpu, mem, latency, error_rate]."""
    mapping = {"cpu": [], "memory": [], "latency": [], "error_rate": []}
    for m in metrics:
        name = m["metric_name"].lower()
        val = float(m["value"])
        if "cpu" in name:
            mapping["cpu"].append(val)
        elif "memory" in name or "mem" in name:
            mapping["memory"].append(val)
        elif "latency" in name or "duration" in name:
            mapping["latency"].append(val)
        elif "error_rate" in name or "error_ratio" in name:
            mapping["error_rate"].append(val)

    if not all(mapping.values()):
        return None
    import numpy as np
    return [
        float(np.mean(mapping["cpu"])),
        float(np.mean(mapping["memory"])),
        float(np.mean(mapping["latency"])),
        float(np.mean(mapping["error_rate"])),
    ]


async def _seed_model():
    """Seed the Isolation Forest with synthetic baseline data on first start."""
    import numpy as np
    logger.info("Seeding model with synthetic baseline data...")
    rng = np.random.default_rng(42)
    # Normal operating conditions
    n = 500
    cpu = rng.normal(0.35, 0.10, n).clip(0, 1)
    memory = rng.normal(0.55, 0.12, n).clip(0, 1)
    latency = rng.normal(150, 40, n).clip(10, 5000)
    error_rate = rng.normal(0.01, 0.005, n).clip(0, 1)
    X = np.column_stack([cpu, memory, latency, error_rate])
    detector.if_detector.train(X)
    logger.info("Model seeded ✓")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=False)
