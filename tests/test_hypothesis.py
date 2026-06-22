import pytest
from services.ai_incident_agent.agents import _generate_fallback_hypotheses

def test_hypothesis_generation_fallback(sample_evidence):
    hypotheses = _generate_fallback_hypotheses(sample_evidence)
    
    assert len(hypotheses) > 0
    top_hyp = hypotheses[0]
    
    # Should detect connection pool from the logs
    assert "connection" in top_hyp["hypothesis_text"].lower() or "pool" in top_hyp["hypothesis_text"].lower()
    assert top_hyp["root_cause_category"] == "connection_pool"
    assert top_hyp["confidence_score"] == 65
