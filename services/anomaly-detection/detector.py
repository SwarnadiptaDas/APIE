"""
Anomaly Detector — correlates ML + threshold signals, publishes anomaly events.
"""
import json
import logging
import time
import uuid
from collections import defaultdict
from typing import Any

import numpy as np
import httpx

from models import AnomalyResult, IsolationForestDetector, MetricWindow, ThresholdDetector

logger = logging.getLogger("detector")

# Feature order for the ML model
FEATURE_METRICS = ["cpu_usage", "memory_usage", "latency_p95_ms", "error_rate"]

class AnomalyDetector:
    """
    Orchestrates ML-based and threshold-based anomaly detection.
    Maintains per-service metric windows for baseline computation.
    """

    def __init__(self, agent_url: str = "http://localhost:8000"):
        self.agent_url = agent_url
        self.if_detector = IsolationForestDetector()
        self.threshold_detector = ThresholdDetector()
        # Per-service, per-metric sliding windows
        self.windows: dict[str, dict[str, MetricWindow]] = defaultdict(
            lambda: defaultdict(MetricWindow)
        )
        self._cooldown: dict[str, float] = {}  # Prevent alert storms
        self.COOLDOWN_SECONDS = 120  # 2-minute cooldown per service

    async def process_metrics(self, metrics: list[dict]) -> list[AnomalyResult]:
        """
        Process a batch of metrics, update windows, and detect anomalies.
        Returns list of detected anomaly results.
        """
        anomalies = []

        # Update windows
        for m in metrics:
            service = m["service"]
            name = m["metric_name"]
            value = float(m["value"])
            ts = float(m.get("timestamp", time.time()))
            self.windows[service][name].add(value, ts)

        # Run detection per service
        services_seen = {m["service"] for m in metrics}
        for service in services_seen:
            service_anomalies = await self._detect_for_service(service, metrics)
            anomalies.extend(service_anomalies)

        return anomalies

    async def _detect_for_service(self, service: str, metrics: list[dict]) -> list[AnomalyResult]:
        anomalies = []
        service_metrics = [m for m in metrics if m["service"] == service]

        # ── Threshold-based detection ────────────────────────────────────────
        for m in service_metrics:
            name = m["metric_name"]
            value = float(m["value"])
            ts = float(m.get("timestamp", time.time()))
            window = self.windows[service][name]
            p95 = window.p95

            severity = self.threshold_detector.check(name, value, p95)
            if severity in ("critical", "warning"):
                baseline = window.mean
                std = window.std
                deviation_sigma = abs(value - baseline) / std if std > 0 else 0.0
                anomalies.append(
                    AnomalyResult(
                        is_anomaly=True,
                        severity=severity,
                        metric_name=name,
                        service=service,
                        value=value,
                        baseline_value=baseline,
                        deviation_sigma=deviation_sigma,
                        timestamp=ts,
                        anomaly_score=-0.8 if severity == "critical" else -0.5,
                    )
                )

        # ── ML-based detection ────────────────────────────────────────────────
        feature_vector = self._build_feature_vector(service)
        if feature_vector is not None:
            X = np.array([feature_vector])
            try:
                labels, scores = self.if_detector.predict(X)
                if labels[0] == -1:  # Anomaly flagged by ML
                    score = float(scores[0])
                    severity = "critical" if score < -0.5 else "warning"
                    # Only report if not already caught by threshold
                    already_flagged = any(a.service == service for a in anomalies)
                    if not already_flagged:
                        anomalies.append(
                            AnomalyResult(
                                is_anomaly=True,
                                severity=severity,
                                metric_name="multivariate",
                                service=service,
                                value=0.0,
                                baseline_value=0.0,
                                deviation_sigma=abs(score) * 3,
                                timestamp=time.time(),
                                anomaly_score=score,
                            )
                        )
            except Exception as e:
                logger.warning(f"ML detection failed for {service}: {e}")

        return anomalies

    def _build_feature_vector(self, service: str) -> list[float] | None:
        """Build [cpu, memory, latency, error_rate] feature vector for ML."""
        windows = self.windows[service]
        features = []
        for metric in FEATURE_METRICS:
            # Try fuzzy match
            matched = next(
                (w.mean for k, w in windows.items() if metric in k.lower() and w.values),
                None,
            )
            if matched is None:
                return None  # Missing metric — skip ML
            features.append(matched)
        return features

    async def publish_anomaly(self, anomaly: AnomalyResult, incident_id: str | None = None):
        """Publish anomaly event to Redis for AI Incident Agent to consume."""
        # Cooldown check
        cooldown_key = f"{anomaly.service}:{anomaly.metric_name}"
        last_alert = self._cooldown.get(cooldown_key, 0)
        if time.time() - last_alert < self.COOLDOWN_SECONDS:
            return
        self._cooldown[cooldown_key] = time.time()

        event = {
            "event_type": "anomaly_detected",
            "incident_id": incident_id or str(uuid.uuid4()),
            "service": anomaly.service,
            "metric_name": anomaly.metric_name,
            "severity": anomaly.severity,
            "value": anomaly.value,
            "baseline": anomaly.baseline_value,
            "deviation_sigma": anomaly.deviation_sigma,
            "anomaly_score": anomaly.anomaly_score,
            "timestamp": anomaly.timestamp,
            "detected_at": time.time(),
        }

        try:
            async with httpx.AsyncClient() as client:
                await client.post(f"{self.agent_url}/incidents/internal_trigger", json=event)
        except Exception as e:
            logger.error(f"Failed to publish anomaly via HTTP: {e}")
            
        logger.info(
            f"🚨 Anomaly published: service={anomaly.service} "
            f"metric={anomaly.metric_name} severity={anomaly.severity} "
            f"value={anomaly.value:.2f}"
        )
        return event


def detect_anomalies(metrics_data: list[dict], detector: "AnomalyDetector | None" = None) -> list[dict]:
    """
    Functional interface for Feature 1.
    Input: list of metric dicts (timestamp, service, metric_name, value)
    Output: list of anomaly flag dicts
    """
    import asyncio

    async def _run():
        d = detector or AnomalyDetector()
        results = await d.process_metrics(metrics_data)
        return results

    anomalies = asyncio.run(_run())
    return [
        {
            "timestamp": a.timestamp,
            "service": a.service,
            "metric_name": a.metric_name,
            "severity": a.severity,
            "value": a.value,
            "baseline": a.baseline_value,
            "deviation_sigma": a.deviation_sigma,
            "anomaly_score": a.anomaly_score,
        }
        for a in anomalies
    ]
