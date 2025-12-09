from typing import List, Dict, Optional
from rag.vectorstore import get_vector_store
from product.repository import get_product_repository
from rag.query_expander import get_query_expander, get_llm_reranker
from config import get_settings


class HybridRetriever:
    def __init__(
        self, 
        semantic_weight: float = 0.6, 
        keyword_weight: float = 0.4,
        use_query_expansion: bool = True,
        use_llm_reranking: bool = True
    ):
        self.vector_store = get_vector_store()
        self.product_repo = get_product_repository()
        
        total = semantic_weight + keyword_weight
        self.semantic_weight = semantic_weight / total
        self.keyword_weight = keyword_weight / total
        
        self.use_query_expansion = use_query_expansion
        self.use_llm_reranking = use_llm_reranking
        
        if use_query_expansion:
            self.query_expander = get_query_expander()
        if use_llm_reranking:
            self.llm_reranker = get_llm_reranker()
        
        settings = get_settings()
        self.top_k = settings.rag_top_k
        self.min_score = settings.rag_min_score
    
    def _keyword_search(self, query: str, top_k: int = 10) -> List[Dict]:
        query_lower = query.lower()
        all_products = self.product_repo.list_products()
        results = []
        
        for product in all_products:
            title_lower = product.title.lower()
            category_lower = product.category.lower()
            
            score = 0.0
            
            if query_lower in title_lower:
                score = 1.0
            else:
                query_words = query_lower.split()
                title_words = title_lower.split()
                matches = sum(1 for qw in query_words if qw in title_lower)
                if matches > 0:
                    score = matches / len(query_words) * 0.8
            
            if query_lower in category_lower:
                score = max(score, 0.5)
            
            if score > 0.3:
                results.append({
                    'product_id': product.id,
                    'score': score,
                    'title': product.title,
                    'metadata': {
                        'category': product.category,
                        'price': product.price,
                        'product_id': product.id,
                        'title': product.title
                    }
                })
        
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:top_k]
    
    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        min_score: Optional[float] = None
    ) -> List[Dict]:
        k = top_k or self.top_k
        score_threshold = min_score or self.min_score
        
        search_query = query
        if self.use_query_expansion:
            search_query = self.query_expander.expand(query)
        
        semantic_results = self.vector_store.search(
            query=search_query,
            top_k=k * 2,
            min_score=0.0
        )
        
        keyword_results = self._keyword_search(search_query, top_k=k * 2)
        combined_results = self._combine_results(semantic_results, keyword_results)
        
        if self.use_llm_reranking and len(combined_results) > 2:
            combined_results = self.llm_reranker.rerank(query, combined_results)
        
        filtered_results = [r for r in combined_results if r['score'] >= score_threshold]
        
        if filtered_results:
            top_score = filtered_results[0]['score']
            adaptive_threshold = max(score_threshold, top_score - 0.3)
            filtered_results = [r for r in filtered_results if r['score'] >= adaptive_threshold]
        
        print(f"Найдено результатов: {len(filtered_results[:k])}")
        return filtered_results[:k]
    
    def _combine_results(
        self,
        semantic_results: List[Dict],
        keyword_results: List[Dict]
    ) -> List[Dict]:
        combined = {}
        
        for result in semantic_results:
            product_id = result['metadata'].get('product_id')
            if product_id:
                combined[product_id] = {
                    'text': result['text'],
                    'metadata': result['metadata'],
                    'semantic_score': result['score'],
                    'keyword_score': 0.0
                }
        
        # Merge keyword results
        for result in keyword_results:
            product_id = result['product_id']
            if product_id in combined:
                combined[product_id]['keyword_score'] = result['score']
            else:
                product = self.product_repo.get_product(product_id)
                if product:
                    text = self._format_product(product)
                    combined[product_id] = {
                        'text': text,
                        'metadata': result['metadata'],
                        'semantic_score': 0.0,
                        'keyword_score': result['score']
                    }
        
        final_results = []
        for product_id, data in combined.items():
            combined_score = (
                data['semantic_score'] * self.semantic_weight +
                data['keyword_score'] * self.keyword_weight
            )
            
            final_results.append({
                'text': data['text'],
                'metadata': data['metadata'],
                'score': combined_score,
                'semantic_score': data['semantic_score'],
                'keyword_score': data['keyword_score'],
                'id': f"product_{product_id}"
            })
        
        final_results.sort(key=lambda x: x['score'], reverse=True)
        return final_results
    
    def _format_product(self, product) -> str:
        chars = '\n'.join(f"{k}: {v}" for k, v in product.characteristics.items())
        return f"""{product.title}

Категория: {product.category}
Описание: {product.description}

Характеристики:
{chars}

Цена: {product.price} руб.
Наличие: {product.stock} шт."""
    
    def retrieve_formatted(self, query: str) -> str:
        results = self.retrieve(query)
        
        if not results:
            return "Не найдено релевантной информации о товарах."
        
        formatted_parts = []
        for i, result in enumerate(results, 1):
            formatted_parts.append(
                f"Результат {i} (релевантность: {result['score']:.2f}):\n{result['text']}"
            )
        
        return "\n\n---\n\n".join(formatted_parts)
    
    def get_product_context(self, product_id: str) -> Optional[str]:
        product = self.product_repo.get_product(product_id)
        if not product:
            return None
        
        return f"""Товар: {product.title}
ID: {product.id}
Категория: {product.category}
Цена: {product.price} руб.
Наличие: {"В наличии" if product.is_available() else "Нет в наличии"} ({product.stock} шт.)

Описание:
{product.description}

Характеристики:
{chr(10).join(f"- {k}: {v}" for k, v in product.characteristics.items())}

Гарантия: {product.warranty}
Состояние: {product.quality_notes}
Вес: {product.weight} кг
Размеры: {product.dimensions.length}x{product.dimensions.width}x{product.dimensions.height} см
Места встречи: {", ".join(product.meeting_locations)}

[ВНУТРЕННЯЯ ИНФОРМАЦИЯ]
- Торг: {"возможен" if product.bargaining_allowed else "невозможен"}
- Минимальная цена: {product.min_price} руб.
{f"- Максимальная скидка: {product.max_discount_percent}%" if product.max_discount_percent > 0 else ""}"""


_hybrid_retriever: Optional[HybridRetriever] = None


def get_hybrid_retriever(
    semantic_weight: float = 0.6, 
    keyword_weight: float = 0.4,
    use_query_expansion: bool = True,
    use_llm_reranking: bool = True
) -> HybridRetriever:
    global _hybrid_retriever
    if _hybrid_retriever is None:
        _hybrid_retriever = HybridRetriever(
            semantic_weight, 
            keyword_weight,
            use_query_expansion,
            use_llm_reranking
        )
    return _hybrid_retriever
