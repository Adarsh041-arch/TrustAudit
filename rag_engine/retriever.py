import os
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Import chromadb and langchain embedding libraries if available
try:
    import chromadb
    from langchain_google_genai import GoogleGenerativeAIEmbeddings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    logger.warning("chromadb or langchain_google_genai embeddings not available. Falling back to internal semantic/keyword retriever.")

from policy_store.manager import parse_policy_markdown, PolicyRule

class PolicyRetriever:
    def __init__(self, db_path: str = "./chroma_db"):
        self.db_path = os.path.abspath(db_path)
        self.client = None
        self.collection = None
        self.fallback_rules: List[PolicyRule] = []
        
        if CHROMA_AVAILABLE:
            try:
                # Ensure the chroma directory exists
                os.makedirs(self.db_path, exist_ok=True)
                self.client = chromadb.PersistentClient(path=self.db_path)
                # Create or get collection
                self.collection = self.client.get_or_create_collection(
                    name="compliance_policies",
                    metadata={"hnsw:space": "cosine"}
                )
                self.embeddings = GoogleGenerativeAIEmbeddings(
                    model="models/text-embedding-004",
                    google_api_key=os.getenv("GOOGLE_API_KEY")
                )

            except Exception as e:
                logger.error(f"Failed to initialize ChromaDB: {e}. Falling back to memory-based retriever.")
                self.client = None
                self.collection = None

    def index_policies(self, checklist_path: str):
        """Loads and indexes rules from the checklist markdown into ChromaDB."""
        try:
            checklist = parse_policy_markdown(checklist_path)
            self.fallback_rules = checklist.rules
            
            if self.collection is not None and len(checklist.rules) > 0:
                ids = []
                documents = []
                metadatas = []
                
                for rule in checklist.rules:
                    ids.append(rule.rule_id)
                    # Prepare rich textual description for embedding search
                    doc_content = f"Rule ID: {rule.rule_id}\nTitle: {rule.title}\nSeverity: {rule.severity}\nDescription: {rule.description}\nImpact: {rule.impact}\nRecommendation: {rule.recommendation}"
                    documents.append(doc_content)
                    metadatas.append({
                        "rule_id": rule.rule_id,
                        "title": rule.title,
                        "severity": rule.severity,
                        "mandatory": str(rule.mandatory)
                    })
                
                # To feed embeddings, we use standard chromadb client add or upsert
                # Since Chroma's native API expects embeddings if not using their default EF, 
                # we generate embeddings via GoogleGenerativeAIEmbeddings.
                try:
                    embeddings_list = self.embeddings.embed_documents(documents)
                    self.collection.upsert(
                        ids=ids,
                        embeddings=embeddings_list,
                        documents=documents,
                        metadatas=metadatas
                    )
                    logger.info(f"Successfully indexed {len(checklist.rules)} policies in ChromaDB vector store.")
                except Exception as emb_err:
                    logger.warning(f"Error generating Gemini embeddings: {emb_err}. Using text-only search indexing.")
                    # Chroma default embedding fallback
                    self.collection.upsert(
                        ids=ids,
                        documents=documents,
                        metadatas=metadatas
                    )
        except Exception as e:
            logger.error(f"Error indexing policies: {e}")

    def retrieve_relevant_policies(self, query: str, top_k: int = 2) -> List[Dict[str, Any]]:
        """
        Retrieves top_k most relevant policies for the query.
        Falls back to keyword matching if ChromaDB is unavailable.
        """
        if self.collection is not None:
            try:
                # Retrieve using embeddings or text
                try:
                    query_embedding = self.embeddings.embed_query(query)
                    results = self.collection.query(
                        query_embeddings=[query_embedding],
                        n_results=min(top_k, self.collection.count())
                    )
                except Exception:
                    results = self.collection.query(
                        query_texts=[query],
                        n_results=min(top_k, self.collection.count())
                    )
                
                retrieved = []
                if results and "documents" in results and results["documents"]:
                    docs = results["documents"][0]
                    metas = results["metadatas"][0]
                    ids = results["ids"][0]
                    
                    for i in range(len(docs)):
                        # Look up full rule detail from fallbacks to fetch impact/recs
                        rule_id = ids[i]
                        rule_ref = self._find_rule_in_fallback(rule_id)
                        retrieved.append({
                            "rule_id": rule_id,
                            "title": metas[i].get("title", ""),
                            "severity": metas[i].get("severity", "medium"),
                            "description": docs[i],
                            "impact": rule_ref.impact if rule_ref else "",
                            "recommendation": rule_ref.recommendation if rule_ref else ""
                        })
                return retrieved
            except Exception as e:
                logger.error(f"ChromaDB retrieval error: {e}. Falling back to keyword match.")
        
        # Fallback keyword match
        return self._keyword_match(query, top_k)

    def _find_rule_in_fallback(self, rule_id: str) -> Optional[PolicyRule]:
        for r in self.fallback_rules:
            if r.rule_id == rule_id:
                return r
        return None

    def _keyword_match(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        query_words = set(query.lower().split())
        scored_rules = []
        for r in self.fallback_rules:
            # Score based on overlap in title or description
            text = f"{r.rule_id} {r.title} {r.description} {r.severity}".lower()
            score = sum(1 for w in query_words if w in text)
            # Extra weight if rule ID is explicitly mentioned
            if r.rule_id.lower() in query.lower():
                score += 5
            scored_rules.append((score, r))
        
        # Sort and return top_k
        scored_rules.sort(key=lambda x: x[0], reverse=True)
        retrieved = []
        for score, r in scored_rules[:top_k]:
            retrieved.append({
                "rule_id": r.rule_id,
                "title": r.title,
                "severity": r.severity,
                "description": r.description,
                "impact": r.impact,
                "recommendation": r.recommendation
            })
        return retrieved
