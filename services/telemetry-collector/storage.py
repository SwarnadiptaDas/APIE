"""
Storage Manager — SQLite + ChromaDB writes/reads.
"""
import asyncio
import json
import logging
import time
import os
from typing import Any

import aiosqlite
import chromadb
from chromadb.config import Settings

logger = logging.getLogger("storage")


class StorageManager:
    def __init__(self, database_url: str, weaviate_url: str, groq_api_key: str):
        # We will ignore the database_url and weaviate_url and use local files
        self.db_path = "../local_data.db"
        self.chroma_path = "../local_chroma_db"
        self.groq_api_key = groq_api_key
        
        self.chroma_client = chromadb.PersistentClient(path=self.chroma_path)
        self.log_collection = self.chroma_client.get_or_create_collection(name="LogEntry")
        self.kb_collection = self.chroma_client.get_or_create_collection(name="IncidentKB")

    async def initialize(self):
        """Create SQLite schema."""
        await self._init_sqlite()
        logger.info("Storage initialized ✓")

    async def _init_sqlite(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS metrics (
                    time        REAL NOT NULL,
                    service     TEXT NOT NULL,
                    metric_name TEXT NOT NULL,
                    value       REAL NOT NULL,
                    labels      TEXT DEFAULT '{}'
                );
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS traces (
                    time            REAL NOT NULL,
                    trace_id        TEXT NOT NULL,
                    span_id         TEXT NOT NULL,
                    parent_span_id  TEXT DEFAULT '',
                    service         TEXT NOT NULL,
                    operation_name  TEXT NOT NULL,
                    duration_ms     REAL NOT NULL,
                    status          TEXT NOT NULL,
                    error_message   TEXT DEFAULT '',
                    attributes      TEXT DEFAULT '{}'
                );
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS incidents (
                    id              TEXT PRIMARY KEY,
                    title           TEXT NOT NULL,
                    status          TEXT NOT NULL DEFAULT 'open',
                    severity        TEXT NOT NULL DEFAULT 'warning',
                    detected_at     REAL NOT NULL,
                    resolved_at     REAL,
                    affected_services TEXT DEFAULT '[]',
                    anomaly_data    TEXT DEFAULT '{}',
                    analysis_result TEXT DEFAULT '{}',
                    postmortem      TEXT DEFAULT '',
                    created_at      REAL,
                    updated_at      REAL
                );
            """)
            await db.commit()
        logger.info("SQLite initialized ✓")

    async def get_db(self):
        return await aiosqlite.connect(self.db_path)

    # ─── Write Operations ──────────────────────────────────────────────────────
    async def write_metrics(self, metrics: list[dict]):
        if not metrics: return
        async with await self.get_db() as db:
            await db.executemany(
                """
                INSERT INTO metrics (time, service, metric_name, value, labels)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        m["timestamp"],
                        m["service"],
                        m["metric_name"],
                        float(m["value"]),
                        json.dumps(m.get("labels", {})),
                    )
                    for m in metrics
                ]
            )
            await db.commit()

    async def write_logs(self, logs: list[dict]):
        if not logs: return
        
        docs = []
        metadatas = []
        ids = []
        for i, log in enumerate(logs):
            docs.append(log["message"])
            metadatas.append({
                "service": log["service"],
                "level": log["level"],
                "traceId": log.get("trace_id", ""),
                "timestamp": log["timestamp"]
            })
            ids.append(f"{log['timestamp']}-{i}")
            
        try:
            self.log_collection.add(
                documents=docs,
                metadatas=metadatas,
                ids=ids
            )
        except Exception as e:
            logger.warning(f"ChromaDB log write failed: {e}")

    async def write_traces(self, spans: list[dict]):
        if not spans: return
        async with await self.get_db() as db:
            await db.executemany(
                """
                INSERT INTO traces
                  (time, trace_id, span_id, parent_span_id, service, operation_name,
                   duration_ms, status, error_message, attributes)
                VALUES
                  (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        s["start_time"],
                        s["trace_id"],
                        s["span_id"],
                        s.get("parent_span_id", ""),
                        s["service"],
                        s["operation_name"],
                        float(s["duration_ms"]),
                        s["status"],
                        s.get("error_message", ""),
                        json.dumps(s.get("attributes", {})),
                    )
                    for s in spans
                ]
            )
            await db.commit()

    # ─── Query Operations ──────────────────────────────────────────────────────
    async def query_metrics(
        self,
        service: str | None,
        metric_name: str | None,
        start_time: float | None,
        end_time: float | None,
        limit: int = 100,
    ) -> list[dict]:
        where_clauses = []
        params: list[Any] = []
        
        if service:
            where_clauses.append("service = ?")
            params.append(service)
        if metric_name:
            where_clauses.append("metric_name = ?")
            params.append(metric_name)
        if start_time:
            where_clauses.append("time >= ?")
            params.append(start_time)
        if end_time:
            where_clauses.append("time <= ?")
            params.append(end_time)
            
        where = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
        params.append(limit)
        
        async with await self.get_db() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"SELECT time as ts, service, metric_name, value, labels FROM metrics {where} ORDER BY time DESC LIMIT ?",
                params,
            )
            rows = await cursor.fetchall()
            
        return [dict(r) for r in rows]

    async def search_logs(
        self,
        service: str | None,
        level: str | None,
        query: str | None,
        start_time: float | None,
        end_time: float | None,
        limit: int = 50,
    ) -> list[dict]:
        """Semantic log search via ChromaDB."""
        try:
            where = {}
            if service:
                where["service"] = service
            if level:
                where["level"] = level
                
            if query:
                results = self.log_collection.query(
                    query_texts=[query],
                    n_results=limit,
                    where=where if where else None
                )
                
                if not results["documents"] or not results["documents"][0]:
                    return []
                    
                parsed_results = []
                for i in range(len(results["documents"][0])):
                    meta = results["metadatas"][0][i] if results["metadatas"] else {}
                    parsed_results.append({
                        "message": results["documents"][0][i],
                        **meta
                    })
                return parsed_results
            else:
                # ChromaDB doesn't have a simple fetch_all without query, but we can do a dummy query
                return []
        except Exception as e:
            logger.warning(f"ChromaDB search failed: {e}")
            return []

    async def query_traces(
        self,
        service: str | None,
        has_errors: bool,
        start_time: float | None,
        end_time: float | None,
        limit: int = 20,
    ) -> list[dict]:
        where_clauses = []
        params: list[Any] = []
        
        if service:
            where_clauses.append("service = ?")
            params.append(service)
        if has_errors:
            where_clauses.append("status = 'ERROR'")
        if start_time:
            where_clauses.append("time >= ?")
            params.append(start_time)
        if end_time:
            where_clauses.append("time <= ?")
            params.append(end_time)
            
        where = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
        params.append(limit)
        
        async with await self.get_db() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"SELECT *, time as ts FROM traces {where} ORDER BY time DESC LIMIT ?",
                params,
            )
            rows = await cursor.fetchall()
            
        return [dict(r) for r in rows]

    async def save_incident(self, incident: dict):
        """Persist incident metadata to SQLite."""
        async with await self.get_db() as db:
            await db.execute(
                """
                INSERT INTO incidents
                  (id, title, status, severity, detected_at, affected_services,
                   anomaly_data, analysis_result, postmortem, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (id) DO UPDATE SET
                  status = excluded.status,
                  analysis_result = excluded.analysis_result,
                  postmortem = excluded.postmortem,
                  updated_at = excluded.updated_at
                """,
                (
                    incident["id"],
                    incident.get("title", "Untitled Incident"),
                    incident.get("status", "open"),
                    incident.get("severity", "warning"),
                    incident.get("detected_at", time.time()),
                    json.dumps(incident.get("affected_services", [])),
                    json.dumps(incident.get("anomaly_data", {})),
                    json.dumps(incident.get("analysis_result", {})),
                    incident.get("postmortem", ""),
                    time.time(),
                    time.time()
                )
            )
            await db.commit()

    async def list_incidents(self, limit: int = 50) -> list[dict]:
        async with await self.get_db() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT id, title, status, severity,
                       detected_at,
                       resolved_at,
                       affected_services, analysis_result, postmortem
                FROM incidents ORDER BY detected_at DESC LIMIT ?
                """,
                (limit,)
            )
            rows = await cursor.fetchall()
        
        # Parse JSON fields
        results = []
        for r in rows:
            d = dict(r)
            for json_field in ['affected_services', 'analysis_result']:
                try:
                    d[json_field] = json.loads(d[json_field]) if d[json_field] else {}
                except:
                    pass
            results.append(d)
            
        return results
