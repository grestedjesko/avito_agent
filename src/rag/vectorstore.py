from typing import List, Dict, Optional
from pathlib import Path
from langchain_chroma import Chroma
from langchain_core.documents import Document

from rag.embeddings import get_embedding_model
from config import get_settings


class VectorStore:
    def __init__(self, persist_directory: Optional[str] = None):
        settings_config = get_settings()
        persist_dir = persist_directory or settings_config.chroma_persist_directory
        
        Path(persist_dir).mkdir(parents=True, exist_ok=True)
        
        embedding_model = get_embedding_model()
        
        self.chroma = Chroma(
            collection_name="products",
            embedding_function=embedding_model,
            persist_directory=persist_dir
        )
    
    def add_documents(
        self,
        texts: List[str],
        metadatas: List[Dict],
        ids: List[str]
    ) -> None:
        documents = [
            Document(page_content=text, metadata=metadata)
            for text, metadata in zip(texts, metadatas)
        ]
        
        self.chroma.add_documents(documents=documents, ids=ids)
    
    def search(
        self,
        query: str,
        top_k: int = 3,
        min_score: float = 0.0
    ) -> List[Dict]:
        results = self.chroma.similarity_search_with_score(
            query=query,
            k=top_k
        )
        
        formatted_results = []
        for i, (doc, score) in enumerate(results):
            similarity_score = max(0.0, min(1.0, 1.0 - (score / 2.0)))
            
            if similarity_score >= min_score:
                product_id = doc.metadata.get('product_id', 'unknown')
                
                formatted_results.append({
                    'text': doc.page_content,
                    'metadata': doc.metadata,
                    'score': similarity_score,
                    'id': f"product_{product_id}"
                })
        
        if formatted_results:
            print(f"Векторный поиск: найдено {len(formatted_results)} результатов")
        return formatted_results
    
    def delete_all(self) -> None:
        self.chroma.delete_collection()
    
    def count(self) -> int:
        return self.chroma._collection.count()


_vector_store: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store
