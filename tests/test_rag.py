"""
tests/test_rag.py - Tests for RAG service (chunking, ChromaDB indexing, semantic retrieval, CSV filtering)
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_fallback_retrieval():
    """Test keyword-based fallback retrieval."""
    from backend import rag_service
    docs = rag_service._fallback_retrieval("2 BHK apartment in Phagwara")
    assert isinstance(docs, list)
    assert len(docs) > 0
    assert any("phagwara" in d.lower() or "2bhk" in d.lower() or "2 bhk" in d.lower() for d in docs)


def test_fallback_retrieval_loan():
    """Test loan-related fallback."""
    from backend import rag_service
    docs = rag_service._fallback_retrieval("home loan options")
    assert any("loan" in d.lower() or "bank" in d.lower() for d in docs)


def test_chunk_text():
    """Test document chunking."""
    from backend import rag_service

    long_text = "This is a detailed property paragraph with useful details.\n\n" * 30
    chunks = rag_service._chunk_text(long_text, chunk_size=200, overlap=20)

    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 300
        assert len(chunk) > 20


def test_make_doc_id():
    """Test document ID generation."""
    from backend import rag_service

    id1 = rag_service._make_doc_id("source1", 0, "content")
    id2 = rag_service._make_doc_id("source1", 0, "different content")
    id3 = rag_service._make_doc_id("source1", 0, "content")

    assert id1 != id2
    assert id1 == id3


def test_search_properties_by_criteria():
    """Test property filtering from CSV."""
    from backend import rag_service
    import config

    if not config.PROPERTIES_CSV.exists():
        pytest.skip("Properties CSV not found")

    results = rag_service.search_properties_by_criteria(location="Phagwara")
    assert len(results) > 0
    for r in results:
        assert "Phagwara" in r["location"]

    results_2bhk = rag_service.search_properties_by_criteria(bedrooms=2)
    assert len(results_2bhk) > 0
    for r in results_2bhk:
        assert int(r["bedrooms"]) == 2

    results_villas = rag_service.search_properties_by_criteria(property_type="Villa")
    assert len(results_villas) > 0
    for r in results_villas:
        assert r["property_type"] == "Villa"

    results_budget = rag_service.search_properties_by_criteria(max_budget=4_000_000)
    for r in results_budget:
        assert int(r["price_inr"]) <= 4_000_000


def test_chromadb_indexing_and_retrieval(tmp_path, monkeypatch):
    """Test real ChromaDB indexing, idempotency, and semantic retrieval in isolated temp path."""
    import config
    from backend import rag_service

    if not (rag_service.CHROMA_AVAILABLE and rag_service.ST_AVAILABLE):
        pytest.skip("ChromaDB or SentenceTransformers not installed")

    temp_chroma = tmp_path / "chroma_test"
    monkeypatch.setattr(config, "CHROMA_PATH", str(temp_chroma))
    monkeypatch.setattr(rag_service, "_chroma_client", None)

    counts1 = rag_service.index_knowledge_base(force_reindex=False)
    assert counts1["knowledge"] > 0
    assert counts1["properties"] >= 20
    assert rag_service.is_knowledge_base_indexed() is True

    # Running again must not create duplicates
    counts2 = rag_service.index_knowledge_base(force_reindex=False)
    assert counts2 == counts1

    # Retrieval returns relevant docs and source metadata
    docs, metas = rag_service.retrieve_relevant_docs("2 BHK apartment in Phagwara within 50 lakh")
    assert len(docs) > 0
    assert len(metas) == len(docs)
    assert any("phagwara" in d.lower() for d in docs)

    # Reset client before tmp_path cleanup on Windows
    monkeypatch.setattr(rag_service, "_chroma_client", None)
