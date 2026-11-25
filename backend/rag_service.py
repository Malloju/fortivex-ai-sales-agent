"""
backend/rag_service.py - Retrieval-Augmented Generation for DreamHome knowledge
Handles document indexing, embedding, and semantic retrieval via ChromaDB.
Uses lazy imports so module import is instantaneous and avoids unnecessary TensorFlow load.
"""
import os
import csv
import hashlib
import importlib.util
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import config

logger = logging.getLogger(__name__)

# Check availability without triggering heavy Torch/TF/Chroma imports at import time
CHROMA_AVAILABLE: bool = importlib.util.find_spec("chromadb") is not None
ST_AVAILABLE: bool = importlib.util.find_spec("sentence_transformers") is not None

_embedding_model: Optional[Any] = None
_chroma_client: Optional[Any] = None


def _get_embedding_model():
    """Lazy-load SentenceTransformer embedding model (PyTorch only)."""
    global _embedding_model
    if _embedding_model is None and ST_AVAILABLE:
        os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
        os.environ.setdefault("USE_TF", "0")
        from sentence_transformers import SentenceTransformer

        logger.info("Loading sentence transformer model (all-MiniLM-L6-v2)...")
        try:
            _embedding_model = SentenceTransformer("all-MiniLM-L6-v2", local_files_only=True)
        except Exception:
            _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("Embedding model loaded.")
    return _embedding_model


def _get_chroma_client():
    """Get or create persistent ChromaDB client."""
    global _chroma_client
    if _chroma_client is None and CHROMA_AVAILABLE:
        os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
        import chromadb
        from chromadb.config import Settings

        Path(config.CHROMA_PATH).mkdir(parents=True, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(
            path=config.CHROMA_PATH,
            settings=Settings(anonymized_telemetry=False),
        )
    return _chroma_client


def _embed_texts(texts: List[str]) -> List[List[float]]:
    """Generate embeddings for a list of texts."""
    model = _get_embedding_model()
    if model is None:
        return [[0.0] * 384 for _ in texts]
    embeddings = model.encode(texts, batch_size=32, show_progress_bar=False)
    return embeddings.tolist()


def _chunk_text(text: str, chunk_size: int = None, overlap: int = None) -> List[str]:
    """Split text into overlapping chunks respecting paragraph boundaries."""
    chunk_size = chunk_size or config.RAG_CHUNK_SIZE
    overlap = overlap or config.RAG_CHUNK_OVERLAP

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: List[str] = []
    current_chunk = ""

    for para in paragraphs:
        if len(current_chunk) + len(para) + 2 <= chunk_size:
            current_chunk += ("\n\n" if current_chunk else "") + para
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            if len(para) <= chunk_size:
                current_chunk = para
            else:
                sentences = para.replace(". ", ".|").split("|")
                current_chunk = ""
                for sent in sentences:
                    if len(current_chunk) + len(sent) + 1 <= chunk_size:
                        current_chunk += (" " if current_chunk else "") + sent
                    else:
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                        current_chunk = sent

    if current_chunk:
        chunks.append(current_chunk.strip())

    # Filter out decorative divider-only chunks
    cleaned = [c for c in chunks if len(c.replace("=", "").strip()) > 20]
    return cleaned


def _make_doc_id(source: str, chunk_index: int, content: str) -> str:
    """Generate a stable document ID."""
    content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()[:8]
    return f"{source}_{chunk_index}_{content_hash}"


def index_knowledge_base(force_reindex: bool = False) -> Dict[str, int]:
    """
    Index all knowledge documents and properties into ChromaDB.
    Returns count of documents stored per collection.
    Safe to run multiple times without creating duplicate entries.
    """
    if not CHROMA_AVAILABLE or not ST_AVAILABLE:
        logger.warning("ChromaDB or SentenceTransformers not available. Cannot index.")
        return {"knowledge": 0, "properties": 0}

    client = _get_chroma_client()

    if force_reindex:
        for coll_name in (config.CHROMA_COLLECTION_KNOWLEDGE, config.CHROMA_COLLECTION_PROPERTIES):
            try:
                client.delete_collection(coll_name)
            except Exception:
                pass

    # === Index company knowledge ===
    knowledge_collection = client.get_or_create_collection(
        name=config.CHROMA_COLLECTION_KNOWLEDGE,
        metadata={"hnsw:space": "cosine"},
    )

    if config.KNOWLEDGE_TXT.exists():
        knowledge_text = config.KNOWLEDGE_TXT.read_text(encoding="utf-8")
        chunks = _chunk_text(knowledge_text)
        existing_ids = set(knowledge_collection.get()["ids"])

        new_docs, new_ids, new_metadatas = [], [], []
        for i, chunk in enumerate(chunks):
            doc_id = _make_doc_id("knowledge", i, chunk)
            if doc_id not in existing_ids:
                new_docs.append(chunk)
                new_ids.append(doc_id)
                first_line = chunk.splitlines()[0][:80] if chunk.splitlines() else "company_knowledge"
                new_metadatas.append({
                    "source": "company_knowledge.txt",
                    "section": first_line,
                    "chunk_index": i,
                })

        if new_docs:
            embeddings = _embed_texts(new_docs)
            knowledge_collection.upsert(
                documents=new_docs,
                embeddings=embeddings,
                ids=new_ids,
                metadatas=new_metadatas,
            )
            logger.info(f"Indexed {len(new_docs)} knowledge chunks.")

    # === Index properties ===
    properties_collection = client.get_or_create_collection(
        name=config.CHROMA_COLLECTION_PROPERTIES,
        metadata={"hnsw:space": "cosine"},
    )

    if config.PROPERTIES_CSV.exists():
        existing_ids = set(properties_collection.get()["ids"])
        new_docs, new_ids, new_metadatas = [], [], []

        with open(config.PROPERTIES_CSV, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                prop_id = row.get("property_id", "")
                doc_id = f"prop_{prop_id}"
                price_inr = int(row.get("price_inr", 0))
                price_lakh = price_inr / 100_000
                prop_text = (
                    f"Property ID: {prop_id}\n"
                    f"Property: {row.get('property_name', '')}\n"
                    f"Type: {row.get('property_type', '')}\n"
                    f"Location: {row.get('location', '')}\n"
                    f"Price: Rs. {price_inr:,} ({price_lakh:.1f} Lakh)\n"
                    f"Bedrooms: {row.get('bedrooms', '')} BHK\n"
                    f"Bathrooms: {row.get('bathrooms', '')}\n"
                    f"Area: {row.get('area_sqft', '')} sqft\n"
                    f"Furnishing: {row.get('furnishing', '')}\n"
                    f"Amenities: {row.get('amenities', '')}\n"
                    f"Status: {row.get('possession_status', '')}\n"
                    f"Description: {row.get('description', '')}\n"
                    f"Contact: {row.get('contact_information', '')}\n"
                )
                if doc_id not in existing_ids:
                    new_docs.append(prop_text)
                    new_ids.append(doc_id)
                    new_metadatas.append({
                        "property_id": prop_id,
                        "property_name": row.get("property_name", ""),
                        "location": row.get("location", ""),
                        "property_type": row.get("property_type", ""),
                        "price_inr": price_inr,
                        "bedrooms": int(row.get("bedrooms", 0)),
                        "source": "properties.csv",
                    })

        if new_docs:
            embeddings = _embed_texts(new_docs)
            properties_collection.upsert(
                documents=new_docs,
                embeddings=embeddings,
                ids=new_ids,
                metadatas=new_metadatas,
            )
            logger.info(f"Indexed {len(new_docs)} property documents.")

    stats = get_knowledge_base_stats()
    return {
        "knowledge": stats["knowledge_chunks"],
        "properties": stats["property_documents"],
    }


def is_knowledge_base_indexed() -> bool:
    """Check if both knowledge and property collections have indexed documents."""
    if not CHROMA_AVAILABLE:
        return False
    try:
        client = _get_chroma_client()
        k_count = client.get_collection(config.CHROMA_COLLECTION_KNOWLEDGE).count()
        p_count = client.get_collection(config.CHROMA_COLLECTION_PROPERTIES).count()
        return k_count > 0 and p_count > 0
    except Exception:
        return False


def get_knowledge_base_stats() -> Dict[str, int]:
    """Get document counts from ChromaDB collections."""
    if not CHROMA_AVAILABLE:
        return {"knowledge_chunks": 0, "property_documents": 0}
    try:
        client = _get_chroma_client()
        k_count = 0
        p_count = 0
        try:
            k_count = client.get_collection(config.CHROMA_COLLECTION_KNOWLEDGE).count()
        except Exception:
            pass
        try:
            p_count = client.get_collection(config.CHROMA_COLLECTION_PROPERTIES).count()
        except Exception:
            pass
        return {"knowledge_chunks": k_count, "property_documents": p_count}
    except Exception as e:
        logger.error(f"Error getting KB stats: {e}")
        return {"knowledge_chunks": 0, "property_documents": 0}


def retrieve_relevant_docs(
    query: str,
    top_k: int = None,
    search_properties: bool = True,
    search_knowledge: bool = True,
) -> Tuple[List[str], List[Dict]]:
    """
    Retrieve relevant documents for a query using semantic search.
    Returns (documents, metadatas).
    """
    if not query or not query.strip():
        return [], []

    if not CHROMA_AVAILABLE or not ST_AVAILABLE:
        docs = _fallback_retrieval(query)
        return docs, [{"source": "keyword_fallback"} for _ in docs]

    top_k = top_k or config.RAG_TOP_K
    client = _get_chroma_client()
    query_embedding = _embed_texts([query])[0]

    candidates: List[Tuple[float, str, Dict]] = []

    if search_knowledge:
        try:
            k_coll = client.get_collection(config.CHROMA_COLLECTION_KNOWLEDGE)
            if k_coll.count() > 0:
                results = k_coll.query(
                    query_embeddings=[query_embedding],
                    n_results=min(top_k, k_coll.count()),
                    include=["documents", "metadatas", "distances"],
                )
                for doc, meta, dist in zip(
                    results["documents"][0],
                    results["metadatas"][0],
                    results["distances"][0],
                ):
                    meta_copy = dict(meta or {})
                    meta_copy["distance"] = round(float(dist), 4)
                    candidates.append((float(dist), doc, meta_copy))
        except Exception as e:
            logger.warning(f"Knowledge retrieval error: {e}")

    if search_properties:
        try:
            p_coll = client.get_collection(config.CHROMA_COLLECTION_PROPERTIES)
            if p_coll.count() > 0:
                results = p_coll.query(
                    query_embeddings=[query_embedding],
                    n_results=min(top_k, p_coll.count()),
                    include=["documents", "metadatas", "distances"],
                )
                for doc, meta, dist in zip(
                    results["documents"][0],
                    results["metadatas"][0],
                    results["distances"][0],
                ):
                    meta_copy = dict(meta or {})
                    meta_copy["distance"] = round(float(dist), 4)
                    candidates.append((float(dist), doc, meta_copy))
        except Exception as e:
            logger.warning(f"Property retrieval error: {e}")

    if not candidates:
        docs = _fallback_retrieval(query)
        return docs, [{"source": "keyword_fallback"} for _ in docs]

    # Sort by cosine distance ascending (most relevant first) and keep top_k * 2
    candidates.sort(key=lambda item: item[0])
    selected = candidates[: max(top_k, 5)]
    return [c[1] for c in selected], [c[2] for c in selected]


def _fallback_retrieval(query: str) -> List[str]:
    """Keyword-based fallback when ChromaDB is unavailable."""
    fallback_docs = []
    query_lower = query.lower()

    keywords = {
        "phagwara": ["Sunrise Apartments in Phagwara: 2BHK at Rs.45 lakh, 3BHK at Rs.65 lakh. Ready to move."],
        "jalandhar": ["Shivalik Residency in Jalandhar: 3BHK at Rs.75 lakh with swimming pool."],
        "ludhiana": ["Sarabha Nagar Premium in Ludhiana: 3BHK fully furnished at Rs.98 lakh."],
        "2 bhk": ["We have 2BHK apartments in Phagwara from Rs.35 lakh and in Ludhiana from Rs.43 lakh."],
        "2bhk": ["We have 2BHK apartments in Phagwara from Rs.35 lakh and in Ludhiana from Rs.43 lakh."],
        "3 bhk": ["3BHK options: Green Valley Homes (Rs.52L), Shivalik Residency (Rs.75L), Sarabha Nagar (Rs.98L)."],
        "villa": ["Villas available: Phagwara Meadow Villa (3BHK, Rs.1.12 Cr), BRS Nagar Signature Villa (3BHK, Rs.1.45 Cr), Model Town Luxury Villa (4BHK, Rs.1.80 Cr)."],
        "appointment": ["Site visits available Monday-Saturday, 9AM-6PM IST. Book through our agent."],
        "price": ["Property prices range from Rs.19 lakh (1BHK) to Rs.1.80 crore (luxury villa)."],
        "loan": ["We assist with home loan coordination with SBI, HDFC, ICICI, Axis, and PNB."],
    }

    for keyword, docs in keywords.items():
        if keyword in query_lower:
            fallback_docs.extend(docs)

    if not fallback_docs:
        fallback_docs = [
            "DreamHome Realty lists fictional demonstration properties across Phagwara, Jalandhar, Ludhiana, Nawanshahr, and Adampur.",
            "We offer apartments, independent houses, and villas ranging from Rs.19 lakh to Rs.1.80 crore.",
        ]

    return fallback_docs


def search_properties_by_criteria(
    location: str = None,
    property_type: str = None,
    bedrooms: int = None,
    max_budget: int = None,
    top_k: int = 5,
) -> List[Dict]:
    """Search properties from CSV based on structured criteria."""
    if not config.PROPERTIES_CSV.exists():
        return []

    results = []
    with open(config.PROPERTIES_CSV, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if location and location.lower() not in row.get("location", "").lower():
                continue
            if property_type and property_type.lower() not in ("any", "") and property_type.lower() not in row.get("property_type", "").lower():
                continue
            if bedrooms and int(row.get("bedrooms", 0)) != bedrooms:
                continue
            if max_budget and int(row.get("price_inr", 0)) > max_budget:
                continue
            results.append(dict(row))

    results.sort(key=lambda r: int(r.get("price_inr", 0)))
    return results[:top_k]
