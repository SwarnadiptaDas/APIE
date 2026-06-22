import pytest
from services.anomaly_detection.models import ThresholdDetector, MetricWindow

def test_threshold_detector_latency():
    detector = ThresholdDetector()
    
    # Normal
    assert detector.check("latency_p95_ms", 150, 150) == "normal"
    # Warning
    assert detector.check("latency_p95_ms", 2500, 2500) == "warning"
    # Critical
    assert detector.check("latency_p95_ms", 5500, 5500) == "critical"

def test_threshold_detector_error_rate():
    detector = ThresholdDetector()
    assert detector.check("error_rate", 0.01) == "normal"
    assert detector.check("error_rate", 0.06) == "warning"
    assert detector.check("error_rate", 0.15) == "critical"

def test_metric_window():
    window = MetricWindow()
    window.add(100, 1000)
    window.add(200, 1060)
    
    assert window.mean == 150.0
    assert window.p95 > 100
