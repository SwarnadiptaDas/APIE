"""
LangGraph Multi-Agent System — 4 specialized agents for incident analysis.
Graph: investigator → hypothesis → validator → reporter
"""
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from prompts import (
    HYPOTHESIS_PROMPT,
    INVESTIGATOR_PROMPT,
    REPORTER_PROMPT,
    VALIDATOR_PROMPT,
)
from rag import IncidentRAG
from tools import (
    ALL_TOOLS,
    get_metrics,
    get_service_dependencies,
    get_similar_incidents,
    search_logs,
    fetch_recent_github_commits,
    execute_corrective_action,
)

logger = logging.getLogger("agents")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")


# ─── Agent State ───────────────────────────────────────────────────────────────
class IncidentState(TypedDict):
    incident_id: str
    timestamp: float
    affected_services: list[str]
    severity: str
    anomaly_data: dict[str, Any]
    messages: Annotated[list, add_messages]
    # Intermediate outputs
    correlated_evidence: dict[str, Any]
    similar_incidents: list[dict]
    hypotheses: list[dict]
    validated_hypotheses: list[dict]
    top_hypothesis: dict[str, Any]
    incident_report: dict[str, Any]
    postmortem: str
    # Auto-remediation
    auto_remediation: dict[str, Any]
    # Metadata
    agent_timeline: list[dict]
    status: str
    error: str


def _llm(temperature: float = 0.2) -> ChatGroq:
    return ChatGroq(
        model=GROQ_MODEL,
        temperature=temperature,
        api_key=GROQ_API_KEY,
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _track(state: IncidentState, agent: str, action: str) -> list[dict]:
    timeline = state.get("agent_timeline", [])
    timeline.append({"agent": agent, "action": action, "timestamp": _now_iso()})
    return timeline


# ─── Node 1: Investigator Agent ────────────────────────────────────────────────
async def investigator_node(state: IncidentState) -> dict:
    """
    Correlates evidence across logs, traces, and metrics.
    Calls tools to gather evidence, then LLM synthesizes.
    """
    logger.info(f"[Investigator] Starting for incident {state['incident_id']}")
    start = time.time()

    ts = state["timestamp"]
    services = state["affected_services"]
    window_start = ts - 300  # ±5 minutes
    window_end = ts + 300

    # ── Tool calls: gather raw evidence ──────────────────────────────────────
    evidence_parts = {}

    # 1. Error logs
    try:
        log_result = await search_logs.ainvoke({
            "query": "error exception timeout connection failed",
            "level": "ERROR",
            "start_time": window_start,
            "end_time": window_end,
            "limit": 10,
        })
        evidence_parts["raw_logs"] = json.loads(log_result)
    except Exception as e:
        logger.warning(f"Log search failed: {e}")
        evidence_parts["raw_logs"] = {"logs": []}

    # 2. Error traces
    try:
        trace_result = await get_traces.ainvoke({
            "has_errors": True,
            "start_time": window_start,
            "end_time": window_end,
            "limit": 5,
        })
        evidence_parts["raw_traces"] = json.loads(trace_result)
    except Exception as e:
        evidence_parts["raw_traces"] = {"traces": []}

    # 3. Metrics for incident window
    try:
        metric_result = await get_metrics.ainvoke({
            "start_time": window_start,
            "end_time": window_end,
            "limit": 200,
        })
        evidence_parts["raw_metrics"] = json.loads(metric_result)
    except Exception as e:
        evidence_parts["raw_metrics"] = {"metrics": []}

    # 4. Service dependencies and GitHub Commits
    dep_results = {}
    git_results = {}
    for svc in services[:3]:
        try:
            dep_result = await get_service_dependencies.ainvoke({"service": svc})
            dep_results[svc] = json.loads(dep_result)
        except Exception:
            pass
        
        try:
            git_result = await fetch_recent_github_commits.ainvoke({"service": svc})
            git_results[svc] = json.loads(git_result)
        except Exception:
            pass
            
    evidence_parts["dependencies"] = dep_results
    evidence_parts["github_commits"] = git_results

    # ── LLM synthesis ─────────────────────────────────────────────────────────
    prompt = INVESTIGATOR_PROMPT.format(
        timestamp=datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
        services=", ".join(services) if services else "unknown",
    )

    context = f"""
Raw Evidence Collected:
{json.dumps(evidence_parts, indent=2, default=str)[:8000]}

Anomaly Data:
{json.dumps(state.get('anomaly_data', {}), indent=2)}
"""

    llm = _llm()
    messages = [
        SystemMessage(content=prompt),
        HumanMessage(content=context),
    ]

    try:
        response = await llm.ainvoke(messages)
        content = response.content

        # Parse JSON from response
        correlated_evidence = _extract_json(content) or {
            "summary": content[:500],
            "error_logs": evidence_parts["raw_logs"].get("logs", []),
            "error_traces": evidence_parts["raw_traces"].get("traces", []),
            "metric_anomalies": [],
            "affected_services": services,
            "key_observations": [],
        }
    except Exception as e:
        logger.error(f"Investigator LLM failed: {e}")
        correlated_evidence = {
            "summary": f"Evidence collection complete (LLM synthesis failed: {e})",
            "error_logs": evidence_parts["raw_logs"].get("logs", []),
            "error_traces": evidence_parts["raw_traces"].get("traces", []),
            "metric_anomalies": [],
            "affected_services": services,
            "key_observations": ["LLM synthesis unavailable"],
        }

    logger.info(f"[Investigator] Done in {time.time()-start:.1f}s")
    return {
        "correlated_evidence": correlated_evidence,
        "agent_timeline": _track(state, "investigator", "evidence_correlated"),
        "messages": [AIMessage(content=f"Evidence correlated: {correlated_evidence.get('summary', '')}")],
    }


# ─── Node 2: Hypothesis Agent ──────────────────────────────────────────────────
async def hypothesis_node(state: IncidentState) -> dict:
    """
    Generates top 3 root cause hypotheses based on correlated evidence + RAG.
    """
    logger.info(f"[Hypothesis] Generating hypotheses for incident {state['incident_id']}")
    start = time.time()

    evidence = state["correlated_evidence"]

    # RAG: retrieve similar historical incidents
    rag = IncidentRAG()
    await rag.connect()
    similar_incidents = await rag.retrieve_similar_incidents(evidence, limit=5)

    prompt = HYPOTHESIS_PROMPT.format(
        correlated_evidence_json=json.dumps(evidence, indent=2, default=str)[:4000],
        similar_incidents_json=json.dumps(similar_incidents, indent=2)[:2000],
    )

    llm = _llm(temperature=0.3)
    messages = [
        SystemMessage(content="You are an expert SRE analyzing production incidents."),
        HumanMessage(content=prompt),
    ]

    try:
        response = await llm.ainvoke(messages)
        parsed = _extract_json(response.content)
        hypotheses = parsed.get("hypotheses", []) if parsed else []

        if not hypotheses:
            # Fallback hypotheses
            hypotheses = _generate_fallback_hypotheses(evidence)

    except Exception as e:
        logger.error(f"Hypothesis LLM failed: {e}")
        hypotheses = _generate_fallback_hypotheses(evidence)

    logger.info(f"[Hypothesis] Generated {len(hypotheses)} hypotheses in {time.time()-start:.1f}s")
    return {
        "hypotheses": hypotheses,
        "similar_incidents": similar_incidents,
        "agent_timeline": _track(state, "hypothesis", f"generated_{len(hypotheses)}_hypotheses"),
        "messages": [AIMessage(content=f"Generated {len(hypotheses)} root cause hypotheses")],
    }


def _generate_fallback_hypotheses(evidence: dict) -> list[dict]:
    """Rule-based fallback when LLM is unavailable."""
    logs = evidence.get("error_logs", [])
    metrics = evidence.get("metric_anomalies", [])

    log_text = " ".join(l.get("message", "") for l in logs).lower()

    hypotheses = []
    if "connection" in log_text or "pool" in log_text:
        hypotheses.append({
            "rank": 1,
            "hypothesis_text": "Database connection pool exhausted",
            "root_cause_category": "connection_pool",
            "supporting_evidence": [l.get("message", "") for l in logs[:3]],
            "suggested_fix": "Increase DB connection pool size and add connection timeout handling",
            "confidence_score": 65,
        })
    if "timeout" in log_text or "refused" in log_text:
        hypotheses.append({
            "rank": len(hypotheses) + 1,
            "hypothesis_text": "Network timeout between services",
            "root_cause_category": "network_timeout",
            "supporting_evidence": [l.get("message", "") for l in logs[:3]],
            "suggested_fix": "Increase request timeout, add circuit breaker, check network policies",
            "confidence_score": 55,
        })
    if any(m.get("metric", "").lower() in ("cpu_usage", "memory_usage") for m in metrics):
        hypotheses.append({
            "rank": len(hypotheses) + 1,
            "hypothesis_text": "Resource exhaustion causing service degradation",
            "root_cause_category": "resource",
            "supporting_evidence": [f"{m['metric']} at {m.get('current_value', 0):.2f}" for m in metrics[:3]],
            "suggested_fix": "Scale horizontally, optimize resource-intensive operations",
            "confidence_score": 50,
        })

    if not hypotheses:
        hypotheses = [{
            "rank": 1,
            "hypothesis_text": "Service degradation due to anomalous system state",
            "root_cause_category": "unknown",
            "supporting_evidence": ["Anomaly detected in system metrics"],
            "suggested_fix": "Restart affected services and monitor recovery",
            "confidence_score": 40,
        }]
    return hypotheses[:3]


# ─── Node 3: Validator Agent ───────────────────────────────────────────────────
async def validator_node(state: IncidentState) -> dict:
    """
    Scores each hypothesis with validation checks and adjusts confidence.
    """
    logger.info(f"[Validator] Validating {len(state['hypotheses'])} hypotheses")
    start = time.time()

    hypotheses = state["hypotheses"]
    evidence = state["correlated_evidence"]
    similar = state.get("similar_incidents", [])

    prompt = VALIDATOR_PROMPT.format(
        timestamp=datetime.fromtimestamp(state["timestamp"], tz=timezone.utc).isoformat(),
        hypotheses_json=json.dumps(hypotheses, indent=2),
        evidence_json=json.dumps(evidence, indent=2, default=str)[:4000],
    )

    llm = _llm()
    messages = [
        SystemMessage(content="You are a validation expert for incident root cause analysis."),
        HumanMessage(content=prompt),
    ]

    try:
        response = await llm.ainvoke(messages)
        parsed = _extract_json(response.content)
        validated = parsed.get("validated_hypotheses", []) if parsed else []

        if not validated:
            validated = _rule_based_validation(hypotheses, evidence, similar)

        top_idx = 0
        if parsed:
            top_idx = parsed.get("top_hypothesis_index", 0)

    except Exception as e:
        logger.error(f"Validator LLM failed: {e}")
        validated = _rule_based_validation(hypotheses, evidence, similar)
        top_idx = 0

    top_hypothesis = validated[top_idx] if validated else {}
    logger.info(
        f"[Validator] Top hypothesis: '{top_hypothesis.get('hypothesis_text', '')}' "
        f"confidence={top_hypothesis.get('final_confidence_score', 0)}%"
        f" in {time.time()-start:.1f}s"
    )

    return {
        "validated_hypotheses": validated,
        "top_hypothesis": top_hypothesis,
        "agent_timeline": _track(state, "validator", f"confidence={top_hypothesis.get('final_confidence_score', 0)}%"),
        "messages": [AIMessage(content=f"Validation complete. Top hypothesis confidence: {top_hypothesis.get('final_confidence_score', 0)}%")],
    }


def _rule_based_validation(hypotheses: list[dict], evidence: dict, similar: list[dict]) -> list[dict]:
    """Validate hypotheses using rule-based checks when LLM unavailable."""
    validated = []
    logs = evidence.get("error_logs", [])
    traces = evidence.get("error_traces", [])
    metrics = evidence.get("metric_anomalies", [])
    log_text = " ".join(l.get("message", "") for l in logs).lower()

    for h in hypotheses:
        original_conf = h.get("confidence_score", 50)
        category = h.get("root_cause_category", "unknown")

        # Run validation checks
        keywords_map = {
            "connection_pool": ["connection", "pool", "exhausted", "max connections"],
            "memory_leak": ["memory", "heap", "gc", "oom"],
            "network_timeout": ["timeout", "connection refused", "econnreset"],
            "cache": ["cache", "redis", "memcached", "miss"],
            "thread_pool": ["thread", "executor", "queue full"],
            "cpu": ["cpu", "throttle", "load"],
        }

        keywords = keywords_map.get(category, [])
        log_match = any(kw in log_text for kw in keywords) if keywords else bool(logs)
        trace_align = bool(traces)
        metric_support = bool(metrics)

        checks_passed = sum([log_match, trace_align, metric_support])
        if checks_passed == 3:
            adj = +20
        elif checks_passed == 2:
            adj = +10
        elif checks_passed == 1:
            adj = 0
        elif checks_passed == 0:
            adj = -30
        else:
            adj = -15

        # Historical match bonus
        for sim in similar:
            if category in sim.get("root_cause", "").lower():
                adj += 15
                break

        final_conf = max(5, min(99, original_conf + adj))

        validated.append({
            **h,
            "original_confidence": original_conf,
            "validation_checks": {
                "log_pattern_match": log_match,
                "trace_timing_align": trace_align,
                "metric_anomaly_support": metric_support,
            },
            "confidence_adjustment": adj,
            "final_confidence_score": final_conf,
            "validation_reasoning": f"{checks_passed}/3 validation checks passed",
        })

    # Sort by final confidence
    validated.sort(key=lambda x: x.get("final_confidence_score", 0), reverse=True)
    for i, v in enumerate(validated):
        v["rank"] = i + 1

    return validated


# ─── Node 4: Reporter Agent ────────────────────────────────────────────────────
async def reporter_node(state: IncidentState) -> dict:
    """
    Generates professional incident report and postmortem document.
    """
    logger.info(f"[Reporter] Generating incident report for {state['incident_id']}")
    start = time.time()

    top = state.get("top_hypothesis", {})
    evidence = state.get("correlated_evidence", {})
    anomaly = state.get("anomaly_data", {})

    detected_at = datetime.fromtimestamp(state["timestamp"], tz=timezone.utc).isoformat()
    now = _now_iso()
    duration = int((time.time() - state["timestamp"]) / 60) + 3  # estimate

    # Compile timeline
    timeline = state.get("agent_timeline", [])
    t_detection = detected_at
    t_investigation = timeline[0]["timestamp"] if timeline else now
    t_root_cause = timeline[2]["timestamp"] if len(timeline) > 2 else now
    t_resolution = now

    # Format corrective actions
    suggested_fix = top.get("suggested_fix", "No action recommended")

    log_citations = [
        f"Log: {l.get('service', 'unknown')} @ {l.get('timestamp', '')}"
        for l in evidence.get("error_logs", [])[:3]
    ]
    trace_citations = [
        f"Trace: {t.get('trace_id', 'unknown')[:16]}..."
        for t in evidence.get("error_traces", [])[:3]
    ]

    prompt_vars = {
        "incident_id": state["incident_id"],
        "timestamp": detected_at,
        "root_cause": top.get("hypothesis_text", "Under investigation"),
        "confidence_score": top.get("final_confidence_score", 0),
        "affected_services": ", ".join(state.get("affected_services", ["unknown"])),
        "affected_users": anomaly.get("affected_users", "Unknown"),
        "duration_minutes": duration,
        "error_rate": anomaly.get("error_rate", 0),
        "severity": state.get("severity", "warning").upper(),
        "corrective_actions": suggested_fix,
        "corrective_actions_formatted": f"1. {suggested_fix}",
        "evidence_summary": evidence.get("summary", ""),
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "detection_timestamp": t_detection,
        "investigation_start": t_investigation,
        "root_cause_identified": t_root_cause,
        "action_applied": t_root_cause,
        "resolution_timestamp": t_resolution,
        "log_citations": "; ".join(log_citations) or "None",
        "trace_citations": "; ".join(trace_citations) or "None",
    }

    report_prompt = REPORTER_PROMPT.format(**prompt_vars)

    llm = _llm(temperature=0.4)
    messages = [
        SystemMessage(content="You are a senior SRE writing a professional incident postmortem."),
        HumanMessage(content=report_prompt),
    ]

    try:
        response = await llm.ainvoke(messages)
        postmortem_text = response.content
    except Exception as e:
        logger.error(f"Reporter LLM failed: {e}")
        postmortem_text = _generate_fallback_postmortem(prompt_vars)

    # Build structured incident report
    incident_report = {
        "incident_id": state["incident_id"],
        "title": f"Production Incident: {top.get('hypothesis_text', 'Anomaly Detected')}",
        "severity": state.get("severity", "warning"),
        "status": "analyzed",
        "detected_at": detected_at,
        "analyzed_at": now,
        "timeline": {
            "detected": t_detection,
            "investigation_started": t_investigation,
            "root_cause_identified": t_root_cause,
            "resolved": t_resolution,
        },
        "root_cause_summary": top.get("hypothesis_text", "Under investigation"),
        "root_cause_category": top.get("root_cause_category", "unknown"),
        "confidence_score": top.get("final_confidence_score", 0),
        "impact": {
            "affected_users": anomaly.get("affected_users", "Unknown"),
            "duration_minutes": duration,
            "error_rate": anomaly.get("error_rate", 0),
            "affected_services": state.get("affected_services", []),
        },
        "hypotheses": state.get("validated_hypotheses", []),
        "corrective_actions": [suggested_fix],
        "preventions": [
            f"Add SLO alerting for {top.get('root_cause_category', 'this pattern')}",
            "Implement circuit breakers on critical service paths",
            "Add automated runbooks for common failure patterns",
        ],
        "supporting_evidence": {
            "logs": evidence.get("error_logs", [])[:5],
            "traces": evidence.get("error_traces", [])[:3],
            "metrics": evidence.get("metric_anomalies", [])[:5],
        },
        "similar_incidents": state.get("similar_incidents", []),
        "postmortem": postmortem_text,
        "agent_timeline": state.get("agent_timeline", []),
        "auto_remediation": state.get("auto_remediation", {}),
    }

    logger.info(f"[Reporter] Report generated in {time.time()-start:.1f}s")
    return {
        "incident_report": incident_report,
        "postmortem": postmortem_text,
        "agent_timeline": _track(state, "reporter", "postmortem_generated"),
        "messages": [AIMessage(content="Incident report and postmortem generated successfully.")],
    }


def _generate_fallback_postmortem(vars: dict) -> str:
    return f"""====== INCIDENT POSTMORTEM ======
Title: Production Incident: {vars.get('root_cause', 'System Anomaly')}
Date: {vars.get('date', 'Unknown')}
Status: Analyzed
Severity: {vars.get('severity', 'WARNING')}
Incident ID: {vars.get('incident_id', 'N/A')}

## Executive Summary
An automated anomaly was detected in the production environment affecting {vars.get('affected_services', 'multiple services')}.
The AI incident analysis system identified the likely root cause and recommended corrective actions.

## Timeline
- {vars.get('detection_timestamp', 'N/A')}: Anomaly detected by automated monitoring
- {vars.get('investigation_start', 'N/A')}: AI investigation initiated
- {vars.get('root_cause_identified', 'N/A')}: Root cause identified
- {vars.get('resolution_timestamp', 'N/A')}: Analysis completed

## Impact Assessment
- **Duration**: {vars.get('duration_minutes', 0)} minutes
- **Affected Services**: {vars.get('affected_services', 'Unknown')}

## Root Cause Analysis
**Primary Root Cause**: {vars.get('root_cause', 'Under investigation')}
**Confidence Score**: {vars.get('confidence_score', 0)}%

## Corrective Actions
{vars.get('corrective_actions_formatted', '1. Investigate and remediate')}

## Prevention Recommendations
1. Implement automated runbooks for common failure patterns
2. Add SLO-based alerting for early detection
3. Review capacity planning for affected services

**AI Analysis Confidence**: {vars.get('confidence_score', 0)}%
====== END POSTMORTEM ======"""


# ─── Node 5: Remediator Agent ──────────────────────────────────────────────────
async def remediator_node(state: IncidentState) -> dict:
    """
    Autonomously executes the suggested corrective action if confidence > 85%.
    """
    logger.info(f"[Remediator] Evaluating auto-remediation for {state['incident_id']}")
    start = time.time()
    
    top = state.get("top_hypothesis", {})
    confidence = top.get("final_confidence_score", 0)
    suggested_fix = top.get("suggested_fix", "")
    
    auto_remediation = {"attempted": False, "success": False, "output": "Confidence < 85%, requires manual execution."}
    action_log = "auto_remediation_skipped"
    
    if confidence >= 85 and suggested_fix:
        # Determine the best action based on suggested fix text (simplified logic)
        action_id = None
        params = {"service": state["affected_services"][0] if state.get("affected_services") else "api-gateway"}
        
        fix_lower = suggested_fix.lower()
        if "restart" in fix_lower:
            action_id = "restart_service"
        elif "scale" in fix_lower:
            action_id = "scale_up"
        elif "pool" in fix_lower or "connection" in fix_lower:
            action_id = "increase_pool_size"
        elif "rollback" in fix_lower or "revert" in fix_lower:
            action_id = "rollback_deployment"
        elif "cache" in fix_lower or "flush" in fix_lower:
            action_id = "flush_cache"
            
        if action_id:
            logger.info(f"[Remediator] High confidence ({confidence}%). Executing {action_id}")
            try:
                result_str = await execute_corrective_action.ainvoke({
                    "action_id": action_id, 
                    "incident_id": state["incident_id"],
                    "params": json.dumps(params)
                })
                result = json.loads(result_str)
                auto_remediation = {
                    "attempted": True,
                    "success": result.get("success", False),
                    "action_id": action_id,
                    "output": result.get("output", result.get("error", "Unknown result"))
                }
                action_log = f"auto_remediated_{action_id}"
            except Exception as e:
                logger.error(f"[Remediator] Execution failed: {e}")
                auto_remediation = {"attempted": True, "success": False, "output": str(e), "action_id": action_id}
                action_log = "auto_remediation_failed"
        else:
            auto_remediation = {"attempted": False, "success": False, "output": "No mapped action found for suggested fix"}
    
    # Update the report
    report = state.get("incident_report", {})
    if report:
        report["auto_remediation"] = auto_remediation
        if auto_remediation["attempted"] and auto_remediation["success"]:
            report["status"] = "auto_remediated"
            
    logger.info(f"[Remediator] Finished in {time.time()-start:.1f}s")
    return {
        "auto_remediation": auto_remediation,
        "incident_report": report,
        "status": "completed",
        "agent_timeline": _track(state, "remediator", action_log),
        "messages": [AIMessage(content=f"Auto-remediation completed: {auto_remediation['output']}")]
    }


# ─── Build LangGraph ───────────────────────────────────────────────────────────
def build_incident_graph() -> StateGraph:
    graph = StateGraph(IncidentState)

    graph.add_node("investigator", investigator_node)
    graph.add_node("hypothesis", hypothesis_node)
    graph.add_node("validator", validator_node)
    graph.add_node("reporter", reporter_node)
    graph.add_node("remediator", remediator_node)

    graph.add_edge(START, "investigator")
    graph.add_edge("investigator", "hypothesis")
    graph.add_edge("hypothesis", "validator")
    graph.add_edge("validator", "reporter")
    graph.add_edge("reporter", "remediator")
    graph.add_edge("remediator", END)

    return graph.compile()


# Singleton compiled graph
incident_graph = build_incident_graph()


async def run_incident_analysis(
    incident_id: str,
    timestamp: float,
    affected_services: list[str],
    severity: str,
    anomaly_data: dict,
) -> dict:
    """
    Entry point: run the full 4-agent incident analysis workflow.
    Returns the complete incident report.
    """
    initial_state = IncidentState(
        incident_id=incident_id,
        timestamp=timestamp,
        affected_services=affected_services,
        severity=severity,
        anomaly_data=anomaly_data,
        messages=[],
        correlated_evidence={},
        similar_incidents=[],
        hypotheses=[],
        validated_hypotheses=[],
        top_hypothesis={},
        incident_report={},
        postmortem="",
        auto_remediation={},
        agent_timeline=[],
        status="running",
        error="",
    )

    try:
        final_state = await incident_graph.ainvoke(initial_state)
        return final_state.get("incident_report", {})
    except Exception as e:
        logger.error(f"Incident graph failed: {e}", exc_info=True)
        return {
            "incident_id": incident_id,
            "status": "failed",
            "error": str(e),
            "title": "Incident Analysis Failed",
            "confidence_score": 0,
        }


# ─── Utility ────────────────────────────────────────────────────────────────────
def _extract_json(text: str) -> dict | None:
    """Extract first JSON object from LLM response."""
    import re
    # Try to find JSON block
    patterns = [
        r"```json\s*([\s\S]+?)\s*```",
        r"```\s*([\s\S]+?)\s*```",
        r"(\{[\s\S]+\})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                continue
    # Try parsing entire text
    try:
        return json.loads(text)
    except Exception:
        return None
