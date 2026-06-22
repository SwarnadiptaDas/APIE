import pytest
from services.ai_incident_agent.agents import _generate_fallback_postmortem

def test_report_generation():
    vars = {
        "root_cause": "Database connection pool exhausted",
        "date": "2026-06-20",
        "severity": "CRITICAL",
        "incident_id": "12345",
        "duration_minutes": 15,
        "affected_services": "api-gateway",
        "confidence_score": 85,
        "corrective_actions_formatted": "1. Increased pool size"
    }
    
    report = _generate_fallback_postmortem(vars)
    
    assert "====== INCIDENT POSTMORTEM ======" in report
    assert "CRITICAL" in report
    assert "Database connection pool exhausted" in report
    assert "15 minutes" in report
    assert "1. Increased pool size" in report
    assert "85%" in report
