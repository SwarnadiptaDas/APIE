"""
Demo Data Seeder
Populates the system with initial metrics, logs, traces, and historical incidents
so the dashboard has rich data to display immediately without waiting for real OTel data.
"""
import asyncio
import json
import logging
import os
import random
import time
import uuid

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed")

TELEMETRY_URL = os.getenv("TELEMETRY_URL", "http://localhost:8001")
AI_AGENT_URL = os.getenv("AI_AGENT_URL", "http://localhost:8000")

SERVICES = ["api-gateway", "payment-service", "order-service", "auth-service"]


async def seed_telemetry():
    """Seed baseline metrics for the last 1 hour."""
    logger.info("Seeding telemetry data...")
    now = time.time()
    metrics = []

    for i in range(60):  # 60 minutes
        ts = now - (60 - i) * 60
        for svc in SERVICES:
            # Baseline normal metrics
            metrics.extend([
                {"timestamp": ts, "service": svc, "metric_name": "latency_p95_ms", "value": random.uniform(80, 250)},
                {"timestamp": ts, "service": svc, "metric_name": "cpu_usage", "value": random.uniform(0.2, 0.45)},
                {"timestamp": ts, "service": svc, "metric_name": "memory_usage", "value": random.uniform(0.4, 0.65)},
                {"timestamp": ts, "service": svc, "metric_name": "error_rate", "value": random.uniform(0.001, 0.005)},
            ])

    async with httpx.AsyncClient() as client:
        # We send in chunks
        chunk_size = 100
        for i in range(0, len(metrics), chunk_size):
            chunk = metrics[i : i + chunk_size]
            try:
                await client.post(f"{TELEMETRY_URL}/v1/metrics", json=chunk)
            except Exception as e:
                logger.warning(f"Failed to push metrics: {e}")
                
        # Push some error logs to guarantee high confidence for auto-remediation
        logs = [
            {"timestamp": now - 120, "service": "api-gateway", "level": "ERROR", "message": "connection pool exhausted (50/50 connections used)"},
            {"timestamp": now - 110, "service": "api-gateway", "level": "ERROR", "message": "timeout waiting for database connection"},
            {"timestamp": now - 100, "service": "api-gateway", "level": "ERROR", "message": "connection refused by upstream payment-db"}
        ]
        try:
            await client.post(f"{TELEMETRY_URL}/v1/logs", json=logs)
            logger.info("Seeded error logs for correlation.")
        except Exception as e:
            logger.warning(f"Failed to push logs: {e}")
            
    logger.info(f"Seeded {len(metrics)} baseline metrics.")


async def seed_historical_incidents():
    """Seed resolved incidents to Weaviate (via Agent API) to enable RAG."""
    logger.info("Seeding historical incidents for RAG...")
    hist_incidents = [
        {
            "service": "payment-service",
            "metric_name": "latency_p95_ms",
            "severity": "critical",
            "value": 12500,
            "affected_services": ["payment-service", "api-gateway"],
            "anomaly_data": {"affected_users": 5400, "error_rate": 0.08},
        },
        {
            "service": "order-service",
            "metric_name": "error_rate",
            "severity": "warning",
            "value": 0.15,
            "affected_services": ["order-service", "inventory-service"],
            "anomaly_data": {"affected_users": 1200, "error_rate": 0.15},
        }
    ]

    async with httpx.AsyncClient() as client:
        for inc in hist_incidents:
            try:
                # Trigger
                res = await client.post(f"{AI_AGENT_URL}/incidents/trigger", json=inc)
                if res.status_code == 202:
                    inc_id = res.json()["incident_id"]
                    logger.info(f"Triggered historical incident {inc_id}, waiting for analysis...")
                    
                    # Wait for analysis
                    for _ in range(15):
                        await asyncio.sleep(2)
                        chk = await client.get(f"{AI_AGENT_URL}/incidents/{inc_id}")
                        if chk.json().get("status") == "analyzed":
                            break
                            
                    # Resolve
                    await client.post(f"{AI_AGENT_URL}/incidents/{inc_id}/resolve")
                    logger.info(f"Resolved historical incident {inc_id} (stored in RAG)")
            except Exception as e:
                logger.warning(f"Failed to seed historical incident: {e}")


async def seed_live_incident():
    """Trigger a live critical incident that will trigger auto-remediation."""
    logger.info("Triggering live critical incident for auto-remediation demo...")
    live_inc = {
        "service": "api-gateway",
        "metric_name": "latency_p95_ms",
        "severity": "critical",
        "value": 8500,
        "affected_services": ["api-gateway", "payment-service"],
        "anomaly_data": {"affected_users": 12500, "error_rate": 0.14},
    }
    async with httpx.AsyncClient() as client:
        try:
            res = await client.post(f"{AI_AGENT_URL}/incidents/trigger", json=live_inc)
            if res.status_code == 202:
                inc_id = res.json()["incident_id"]
                logger.info(f"Live incident {inc_id} triggered! Check the dashboard.")
        except Exception as e:
            logger.warning(f"Failed to trigger live incident: {e}")

async def main():
    await seed_telemetry()
    await seed_historical_incidents()
    await seed_live_incident()
    logger.info("✅ Demo seeding complete.")


if __name__ == "__main__":
    asyncio.run(main())
