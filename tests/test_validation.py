import pytest
from services.ai_incident_agent.agents import _rule_based_validation

def test_validation_confidence_adjustment():
    hypotheses = [
        {
            "rank": 1,
            "hypothesis_text": "DB connection pool exhausted",
            "root_cause_category": "connection_pool",
            "confidence_score": 60
        }
    ]
    evidence = {
        "error_logs": [{"message": "connection pool exhausted"}],
        "error_traces": [{"trace_id": "123"}],
        "metric_anomalies": [{"metric": "latency"}]
    }
    
    # Should get +20 since all 3 checks (logs, traces, metrics) pass
    validated = _rule_based_validation(hypotheses, evidence, [])
    
    assert len(validated) == 1
    assert validated[0]["confidence_adjustment"] == 20
    assert validated[0]["final_confidence_score"] == 80
    assert validated[0]["validation_checks"]["log_pattern_match"] is True
    assert validated[0]["validation_checks"]["trace_timing_align"] is True
    assert validated[0]["validation_checks"]["metric_anomaly_support"] is True
