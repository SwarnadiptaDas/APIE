"""
OTLP Receiver — parses OpenTelemetry protocol data.
"""
import logging
import time
from typing import Any

logger = logging.getLogger("otel-receiver")


class OTLPReceiver:
    """
    Lightweight OTLP/HTTP receiver that translates OTel proto JSON
    to our internal telemetry format and routes to storage.
    """

    def __init__(self, storage, memory_queue):
        self.storage = storage
        self.memory_queue = memory_queue

    def parse_resource_spans(self, data: dict) -> list[dict]:
        """Parse OTLP ResourceSpans payload into internal TraceSpan format."""
        spans = []
        for resource_span in data.get("resourceSpans", []):
            service_name = self._extract_service_name(resource_span.get("resource", {}))
            for scope_span in resource_span.get("scopeSpans", []):
                for span in scope_span.get("spans", []):
                    start_ns = int(span.get("startTimeUnixNano", 0))
                    end_ns = int(span.get("endTimeUnixNano", 0))
                    duration_ms = (end_ns - start_ns) / 1_000_000 if end_ns > start_ns else 0
                    status_code = span.get("status", {}).get("code", 0)
                    error_msg = span.get("status", {}).get("message", "")

                    attrs = {
                        a["key"]: self._extract_value(a.get("value", {}))
                        for a in span.get("attributes", [])
                    }
                    spans.append({
                        "trace_id": span.get("traceId", ""),
                        "span_id": span.get("spanId", ""),
                        "parent_span_id": span.get("parentSpanId", ""),
                        "service": service_name,
                        "operation_name": span.get("name", "unknown"),
                        "start_time": start_ns / 1_000_000_000,
                        "duration_ms": duration_ms,
                        "status": "ERROR" if status_code == 2 else "OK",
                        "error_message": error_msg,
                        "attributes": attrs,
                    })
        return spans

    def parse_resource_metrics(self, data: dict) -> list[dict]:
        """Parse OTLP ResourceMetrics payload."""
        points = []
        for resource_metric in data.get("resourceMetrics", []):
            service_name = self._extract_service_name(resource_metric.get("resource", {}))
            for scope_metric in resource_metric.get("scopeMetrics", []):
                for metric in scope_metric.get("metrics", []):
                    metric_name = metric.get("name", "unknown")
                    data_points = (
                        metric.get("gauge", {}).get("dataPoints", [])
                        or metric.get("sum", {}).get("dataPoints", [])
                        or metric.get("histogram", {}).get("dataPoints", [])
                    )
                    for dp in data_points:
                        ts_ns = int(dp.get("timeUnixNano", 0))
                        value = dp.get("asDouble", dp.get("asInt", 0))
                        labels = {
                            a["key"]: self._extract_value(a.get("value", {}))
                            for a in dp.get("attributes", [])
                        }
                        points.append({
                            "timestamp": ts_ns / 1_000_000_000 if ts_ns else time.time(),
                            "service": service_name,
                            "metric_name": metric_name,
                            "value": float(value),
                            "labels": labels,
                        })
        return points

    def parse_resource_logs(self, data: dict) -> list[dict]:
        """Parse OTLP ResourceLogs payload."""
        log_records = []
        for resource_log in data.get("resourceLogs", []):
            service_name = self._extract_service_name(resource_log.get("resource", {}))
            for scope_log in resource_log.get("scopeLogs", []):
                for record in scope_log.get("logRecords", []):
                    ts_ns = int(record.get("timeUnixNano", 0))
                    severity_num = record.get("severityNumber", 9)
                    level = self._severity_to_level(severity_num)
                    body = record.get("body", {})
                    message = body.get("stringValue", str(body))
                    attrs = {
                        a["key"]: self._extract_value(a.get("value", {}))
                        for a in record.get("attributes", [])
                    }
                    log_records.append({
                        "timestamp": ts_ns / 1_000_000_000 if ts_ns else time.time(),
                        "service": service_name,
                        "level": level,
                        "message": message,
                        "trace_id": record.get("traceId", ""),
                        "span_id": record.get("spanId", ""),
                        "attributes": attrs,
                    })
        return log_records

    def _extract_service_name(self, resource: dict) -> str:
        for attr in resource.get("attributes", []):
            if attr.get("key") == "service.name":
                return self._extract_value(attr.get("value", {}))
        return "unknown-service"

    def _extract_value(self, value: dict) -> Any:
        if "stringValue" in value:
            return value["stringValue"]
        if "intValue" in value:
            return int(value["intValue"])
        if "doubleValue" in value:
            return float(value["doubleValue"])
        if "boolValue" in value:
            return value["boolValue"]
        return str(value)

    def _severity_to_level(self, severity_num: int) -> str:
        if severity_num >= 17:
            return "FATAL"
        if severity_num >= 13:
            return "ERROR"
        if severity_num >= 9:
            return "WARN"
        return "INFO"
