"""Script to initialize vector store with product data."""
import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from rag.vectorstore import get_vector_store
from product.repository import get_product_repository


def setup_vectorstore():
    """Initialize vector store with product data."""
    print("=" * 60)
    print("Setting up vector store with product data")
    print("=" * 60)
    
    vector_store = get_vector_store()
    product_repo = get_product_repository()
    
    print("\nClearing existing vector store data...")
    vector_store.delete_all()
    
    products = product_repo.list_products()
    print(f"\nFound {len(products)} products")
    
    if not products:
        print("No products found! Check data/products.json")
        return
    
    texts = []
    metadatas = []
    ids = []
    
    for product in products:
        text = f"""
{product.title}

Категория: {product.category}

Описание: {product.description}

Характеристики:
{chr(10).join(f"{k}: {v}" for k, v in product.characteristics.items())}

Гарантия: {product.warranty}

Состояние: {product.quality_notes}

Цена: {product.price} руб.
"""
        
        metadata = {
            "product_id": product.id,
            "title": product.title,
            "category": product.category,
            "price": product.price
        }
        
        texts.append(text.strip())
        metadatas.append(metadata)
        ids.append(f"product_{product.id}")
    
    print(f"\nAdding {len(texts)} documents to vector store...")
    vector_store.add_documents(texts, metadatas, ids)
    
    count = vector_store.count()
    print(f"\n✓ Vector store setup complete!")
    print(f"✓ Total documents: {count}")
    
    print("\n" + "=" * 60)
    print("Testing search functionality")
    print("=" * 60)
    
    test_queries = [
        "iPhone",
        "ноутбук для работы",
        "игровой компьютер",
        "наушники"
    ]
    
    for query in test_queries:
        print(f"\nQuery: '{query}'")
        results = vector_store.search(query, top_k=2)
        if results:
            for i, result in enumerate(results, 1):
                print(f"  {i}. {result['metadata'].get('title', 'N/A')} "
                      f"(score: {result['score']:.3f})")
        else:
            print("  No results found")
    
    print("\n" + "=" * 60)
    print("Setup complete!")
    print("=" * 60)


if __name__ == "__main__":
    setup_vectorstore()
