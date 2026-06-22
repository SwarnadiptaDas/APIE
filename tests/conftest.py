import pytest

@pytest.fixture
def sample_metrics():
    return [
        {"timestamp": 1000, "service": "api-gateway", "metric_name": "latency_p95_ms", "value": 150},
        {"timestamp": 1060, "service": "api-gateway", "metric_name": "latency_p95_ms", "value": 160},
        # Anomaly
        {"timestamp": 1120, "service": "api-gateway", "metric_name": "latency_p95_ms", "value": 5200},
    ]

@pytest.fixture
def sample_evidence():
    return {
        "summary": "DB connection pool exhausted",
        "error_logs": [
            {"service": "api-gateway", "level": "ERROR", "message": "connection pool exhausted"}
        ],
        "metric_anomalies": [
            {"metric": "latency_p95_ms", "current_value": 8500}
        ]
    }
