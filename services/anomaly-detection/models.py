"""
Anomaly Detection Models — Isolation Forest + baseline computation.
"""
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger("anomaly-models")

MODEL_PATH = os.getenv("MODEL_PATH", "/tmp/isolation_forest.joblib")
SCALER_PATH = os.getenv("SCALER_PATH", "/tmp/scaler.joblib")


@dataclass
class AnomalyResult:
    is_anomaly: bool
    severity: str  # "critical" | "warning" | "normal"
    metric_name: str
    service: str
    value: float
    baseline_value: float
    deviation_sigma: float
    timestamp: float
    anomaly_score: float  # -1 to 1, lower = more anomalous


@dataclass
class MetricWindow:
    """Sliding window of metric values for baseline computation."""
    values: list[float] = field(default_factory=list)
    timestamps: list[float] = field(default_factory=list)
    window_seconds: int = 604800  # 7 days

    def add(self, value: float, timestamp: float):
        self.values.append(value)
        self.timestamps.append(timestamp)
        self._prune()

    def _prune(self):
        cutoff = time.time() - self.window_seconds
        while self.timestamps and self.timestamps[0] < cutoff:
            self.timestamps.pop(0)
            self.values.pop(0)

    @property
    def mean(self) -> float:
        return float(np.mean(self.values)) if self.values else 0.0

    @property
    def std(self) -> float:
        return float(np.std(self.values)) if len(self.values) > 1 else 0.0

    @property
    def p95(self) -> float:
        return float(np.percentile(self.values, 95)) if self.values else 0.0

    def has_enough_data(self, min_points: int = 30) -> bool:
        return len(self.values) >= min_points


class IsolationForestDetector:
    """
    Isolation Forest based anomaly detector.
    Detects multivariate anomalies in CPU, memory, latency, error_rate metrics.
    """

    def __init__(
        self,
        contamination: float = 0.05,
        n_estimators: int = 100,
        random_state: int = 42,
    ):
        self.contamination = contamination
        self.n_estimators = n_estimators
        self.random_state = random_state
        self.model: Optional[IsolationForest] = None
        self.scaler: Optional[StandardScaler] = None
        self.is_trained = False
        self._load_or_init()

    def _load_or_init(self):
        try:
            self.model = joblib.load(MODEL_PATH)
            self.scaler = joblib.load(SCALER_PATH)
            self.is_trained = True
            logger.info("Loaded pre-trained Isolation Forest model ✓")
        except Exception:
            logger.info("No pre-trained model found, will train from data")
            self.model = IsolationForest(
                contamination=self.contamination,
                n_estimators=self.n_estimators,
                random_state=self.random_state,
                warm_start=True,
            )
            self.scaler = StandardScaler()

    def train(self, X: np.ndarray):
        """Train on historical metric data. X shape: [n_samples, n_features]."""
        if len(X) < 10:
            logger.warning("Insufficient data for training (< 10 samples)")
            return
        X_scaled = self.scaler.fit_transform(X)
        self.model.fit(X_scaled)
        self.is_trained = True
        self._save()
        logger.info(f"Model trained on {len(X)} samples ✓")

    def predict(self, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """
        Returns:
            labels: 1 = normal, -1 = anomaly
            scores: anomaly scores (lower = more anomalous)
        """
        if not self.is_trained:
            # Fallback: train on the provided data itself
            self.train(X)
        X_scaled = self.scaler.transform(X)
        labels = self.model.predict(X_scaled)
        scores = self.model.score_samples(X_scaled)
        return labels, scores

    def _save(self):
        try:
            joblib.dump(self.model, MODEL_PATH)
            joblib.dump(self.scaler, SCALER_PATH)
            logger.info("Model saved ✓")
        except Exception as e:
            logger.warning(f"Model save failed: {e}")


class ThresholdDetector:
    """
    Rule-based detector for explicit SLO violations.
    Complements the ML model with deterministic checks.
    """

    # Thresholds (configurable via env)
    LATENCY_P95_CRITICAL_MS = float(os.getenv("LATENCY_P95_THRESHOLD_MS", "5000"))
    LATENCY_P95_WARNING_MS = float(os.getenv("LATENCY_P95_WARNING_MS", "2000"))
    ERROR_RATE_CRITICAL = float(os.getenv("ERROR_RATE_CRITICAL_THRESHOLD", "0.10"))
    ERROR_RATE_WARNING = float(os.getenv("ERROR_RATE_WARNING_THRESHOLD", "0.05"))
    CPU_WARNING = float(os.getenv("CPU_WARNING_THRESHOLD", "0.80"))
    CPU_CRITICAL = float(os.getenv("CPU_CRITICAL_THRESHOLD", "0.95"))
    MEMORY_WARNING = float(os.getenv("MEMORY_WARNING_THRESHOLD", "0.85"))
    MEMORY_CRITICAL = float(os.getenv("MEMORY_CRITICAL_THRESHOLD", "0.95"))

    def check(self, metric_name: str, value: float, p95: float = 0.0) -> str:
        """Returns 'critical', 'warning', or 'normal'."""
        name = metric_name.lower()

        if "latency" in name or "duration" in name or "response_time" in name:
            check_val = p95 if p95 > 0 else value
            if check_val > self.LATENCY_P95_CRITICAL_MS:
                return "critical"
            if check_val > self.LATENCY_P95_WARNING_MS:
                return "warning"

        elif "error_rate" in name or "error_ratio" in name:
            if value > self.ERROR_RATE_CRITICAL:
                return "critical"
            if value > self.ERROR_RATE_WARNING:
                return "warning"

        elif "cpu" in name:
            if value > self.CPU_CRITICAL:
                return "critical"
            if value > self.CPU_WARNING:
                return "warning"

        elif "memory" in name or "mem" in name:
            if value > self.MEMORY_CRITICAL:
                return "critical"
            if value > self.MEMORY_WARNING:
                return "warning"

        return "normal"
