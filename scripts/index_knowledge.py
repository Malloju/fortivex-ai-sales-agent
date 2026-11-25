"""
scripts/index_knowledge.py - Index documents into ChromaDB for RAG retrieval
Run after modifying data files to update the vector store.
Safe to run multiple times.
"""
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from backend import rag_service

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main(force_reindex: bool = False):
    """Index all knowledge documents."""
    logger.info("=" * 60)
    logger.info("DreamHome Realty - Knowledge Base Indexing")
    logger.info("=" * 60)
    
    if not rag_service.CHROMA_AVAILABLE:
        logger.error("ChromaDB is not installed. Run: pip install chromadb")
        return False
    
    if not rag_service.ST_AVAILABLE:
        logger.error("SentenceTransformers is not installed. Run: pip install sentence-transformers")
        return False
    
    if not config.KNOWLEDGE_TXT.exists():
        logger.error(f"Knowledge file not found: {config.KNOWLEDGE_TXT}")
        logger.error("Run scripts/generate_dataset.py first.")
        return False
    
    if not config.PROPERTIES_CSV.exists():
        logger.error(f"Properties file not found: {config.PROPERTIES_CSV}")
        return False
    
    logger.info(f"ChromaDB path: {config.CHROMA_PATH}")
    logger.info(f"Force reindex: {force_reindex}")
    
    logger.info("\nIndexing documents...")
    try:
        counts = rag_service.index_knowledge_base(force_reindex=force_reindex)
        
        stats = rag_service.get_knowledge_base_stats()
        
        logger.info("\n✅ Indexing complete!")
        logger.info(f"   Knowledge chunks: {stats['knowledge_chunks']}")
        logger.info(f"   Property documents: {stats['property_documents']}")
        
        # Test retrieval
        logger.info("\nTesting retrieval...")
        docs, metas = rag_service.retrieve_relevant_docs("2 BHK apartment in Phagwara")
        logger.info(f"   Test query retrieved {len(docs)} documents")
        if docs:
            logger.info(f"   First result preview: {docs[0][:100]}...")
        
        return True
        
    except Exception as e:
        logger.error(f"Indexing failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    force = "--force" in sys.argv or "-f" in sys.argv
    success = main(force_reindex=force)
    sys.exit(0 if success else 1)
