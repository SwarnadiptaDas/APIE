"""
RAG — Historical Incident Knowledge Base using ChromaDB.
"""
import json
import logging
import os

import chromadb

logger = logging.getLogger("rag")

CHROMA_PATH = "../local_chroma_db"
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.5"))  # Lower threshold for local L2/similarity mapping


class IncidentRAG:
    """
    Retrieval-Augmented Generation for historical incident knowledge base.
    Uses ChromaDB vector search.
    """

    def __init__(self):
        self.client: chromadb.PersistentClient | None = None
        self.collection_name = "IncidentKB"
        self.collection = None

    async def connect(self):
        try:
            self.client = chromadb.PersistentClient(path=CHROMA_PATH)
            self.collection = self.client.get_or_create_collection(name=self.collection_name)
            logger.info("RAG connected to ChromaDB ✓")
        except Exception as e:
            logger.warning(f"RAG ChromaDB connection failed: {e}")

    async def retrieve_similar_incidents(
        self,
        current_evidence: dict,
        limit: int = 5,
    ) -> list[dict]:
        """
        Feature 7: Retrieve top-K similar historical incidents using semantic search.

        Input: Current correlated evidence dict
        Output: Top 5 similar incidents with title, root_cause, resolution_time, corrective_actions
        """
        if not self.collection:
            return []

        # Build search query from evidence
        query_text = self._evidence_to_text(current_evidence)

        try:
            results = self.collection.query(
                query_texts=[query_text],
                n_results=limit,
            )

            incidents = []
            if results and results.get("documents") and results["documents"][0]:
                for i in range(len(results["documents"][0])):
                    meta = results["metadatas"][0][i] if results["metadatas"] else {}
                    distance = results["distances"][0][i] if results.get("distances") else 1.0
                    
                    # Convert L2 distance to a similarity score (0 to 1)
                    similarity = 1.0 / (1.0 + distance)
                    
                    if similarity >= SIMILARITY_THRESHOLD:
                        # Parse services/corrective_actions if they are stored as JSON strings
                        services = meta.get("services", "[]")
                        corrective_actions = meta.get("corrective_actions", "[]")
                        
                        incidents.append({
                            "incident_id": meta.get("incident_id", ""),
                            "title": meta.get("title", ""),
                            "root_cause": meta.get("root_cause", ""),
                            "services": services,
                            "corrective_actions": corrective_actions,
                            "resolution_minutes": int(meta.get("resolution_minutes", 0)),
                            "evidence_summary": meta.get("evidence_summary", ""),
                            "similarity_score": round(similarity, 4),
                        })

            logger.info(f"RAG retrieved {len(incidents)} similar incidents")
            return incidents

        except Exception as e:
            logger.warning(f"RAG retrieval failed: {e}")
            return []

    async def embed_and_store_incident(self, incident: dict):
        """
        Store a resolved incident in the knowledge base for future RAG.
        Called after incident is resolved + postmortem generated.
        """
        if not self.collection:
            return

        try:
            evidence = incident.get("analysis_result", {}).get("correlated_evidence", {})
            evidence_summary = self._evidence_to_text(evidence)

            metadata = {
                "incident_id": incident["id"],
                "title": incident.get("title", ""),
                "root_cause": incident.get("analysis_result", {}).get("root_cause", ""),
                "services": json.dumps(incident.get("affected_services", [])),
                "corrective_actions": json.dumps(incident.get("corrective_actions", [])),
                "resolution_minutes": int(incident.get("resolution_minutes", 0)),
                "evidence_summary": evidence_summary,
            }

            self.collection.upsert(
                documents=[evidence_summary],
                metadatas=[metadata],
                ids=[incident["id"]]
            )
            logger.info(f"Incident {incident['id']} stored in RAG knowledge base ✓")

        except Exception as e:
            logger.warning(f"RAG storage failed: {e}")

    def _evidence_to_text(self, evidence: dict) -> str:
        """Convert evidence dict to a searchable text summary for embedding."""
        parts = []

        if summary := evidence.get("summary"):
            parts.append(f"Summary: {summary}")

        if logs := evidence.get("error_logs", []):
            log_msgs = [f"{l.get('service','')}: {l.get('message','')}" for l in logs[:5]]
            parts.append(f"Error logs: {'; '.join(log_msgs)}")

        if traces := evidence.get("error_traces", []):
            trace_msgs = [f"{t.get('operation','')}: {t.get('error','')}" for t in traces[:3]]
            parts.append(f"Error traces: {'; '.join(trace_msgs)}")

        if metrics := evidence.get("metric_anomalies", []):
            metric_msgs = [
                f"{m.get('metric','')} on {m.get('service','')}: {m.get('current_value',0):.2f}"
                for m in metrics[:5]
            ]
            parts.append(f"Metric anomalies: {'; '.join(metric_msgs)}")

        if observations := evidence.get("key_observations", []):
            parts.append(f"Observations: {'; '.join(observations[:3])}")

        return " | ".join(parts) if parts else "Unknown incident"
