import chromadb
import os
from rag.embedder import get_embedding
from config import TOP_K_CHUNKS

DB_DIR = os.path.join(os.path.dirname(__file__), "../db/story_db")

client = chromadb.PersistentClient(path=DB_DIR)
collection = client.get_or_create_collection("story")

def retrieve_context(user_message: str, npc_id: str) -> str:
    """
    Given a user message and NPC id,
    return the most relevant story chunks as a single string.
    """
    query_embedding = get_embedding(user_message)

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=TOP_K_CHUNKS,
        where={"npc": npc_id}  # only retrieve chunks tagged to this NPC
    )

    # results["documents"] returns a list of lists, grab the inner list
    chunks = results["documents"][0]
    
    print("\n=== RAG 검색 결과 ===")
    print(f"질문: {user_message}")
    for i, chunk in enumerate(chunks):
        print(f"\n[청크 {i+1}]\n{chunk[:100]}...")  # 앞 100자만
    print("====================\n")

    if not chunks:
        return ""

    return "\n\n---\n\n".join(chunks)

    if not chunks:
        return ""

    return "\n\n".join(chunks)