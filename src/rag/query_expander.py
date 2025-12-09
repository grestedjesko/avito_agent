from typing import List, Optional
from llm.deepseek_client import get_deepseek_client


class QueryExpander:
    def __init__(self):
        self.llm = get_deepseek_client()
        self._cache = {}
    
    def expand(self, query: str) -> str:
        cache_key = query.lower().strip()
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        prompt = f"""Расширь поисковый запрос синонимами и вариантами написания.
Добавь: транслитерацию, бренды, модели. Верни только слова через пробел.

Примеры:
"наушники apple" → наушники apple airpods аирподс earpods
"макбук" → макбук macbook ноутбук apple лэптоп
"айфон" → айфон iphone smartphone телефон

Запрос: "{query}"
Ответ:"""

        try:
            response = self.llm.client.chat.completions.create(
                model=self.llm.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=100
            )
            
            expanded = response.choices[0].message.content.strip()
            expanded = expanded.replace('```', '').replace('"', '').strip()
            
            if query.lower() not in expanded.lower():
                expanded = f"{query} {expanded}"
            
            self._cache[cache_key] = expanded
            return expanded
            
        except Exception as e:
            return query


class LLMReranker:
    def __init__(self):
        self.llm = get_deepseek_client()
    
    def rerank(
        self,
        query: str,
        results: List[dict],
        top_k: Optional[int] = None
    ) -> List[dict]:
        if not results or len(results) <= 2:
            return results[:top_k] if top_k else results
        
        products_text = '\n'.join([
            f"{i+1}. {r['metadata'].get('title', 'Unknown')} ({r['metadata'].get('category', '?')})"
            for i, r in enumerate(results)
        ])
        
        prompt = f"""Оцени релевантность товаров запросу от 0 до 1.
Будь строгим: разные категории = низкая оценка.

Запрос: "{query}"

Товары:
{products_text}

Верни JSON: {{"scores": [0.95, 0.8, ...]}}"""

        try:
            response = self.llm.client.chat.completions.create(
                model=self.llm.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=200
            )
            
            import json, re
            content = response.choices[0].message.content.strip()
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            
            if json_match:
                llm_scores = json.loads(json_match.group()).get('scores', [])
                
                reranked = []
                for i, result in enumerate(results):
                    if i < len(llm_scores):
                        llm_score = float(llm_scores[i])
                        
                        if llm_score < 0.3:
                            continue
                        
                        result_copy = result.copy()
                        result_copy['score'] = llm_score * 0.5 + result['score'] * 0.5
                        result_copy['llm_score'] = llm_score
                        reranked.append(result_copy)
                
                reranked.sort(key=lambda x: x['score'], reverse=True)
                return reranked[:top_k] if top_k else reranked
            
        except Exception as e:
            pass
        
        return results[:top_k] if top_k else results


_query_expander: Optional[QueryExpander] = None
_llm_reranker: Optional[LLMReranker] = None


def get_query_expander() -> QueryExpander:
    global _query_expander
    if _query_expander is None:
        _query_expander = QueryExpander()
    return _query_expander


def get_llm_reranker() -> LLMReranker:
    global _llm_reranker
    if _llm_reranker is None:
        _llm_reranker = LLMReranker()
    return _llm_reranker
