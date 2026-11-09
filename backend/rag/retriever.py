import os
import chromadb
from rag.embedder import get_embedding
from config import TOP_K_CHUNKS, FULL_STORY_MAX_CHARS

STORY_DIR = os.path.join(os.path.dirname(__file__), "../story")
DB_DIR = os.path.join(os.path.dirname(__file__), "../db/story_db")

client = chromadb.PersistentClient(path=DB_DIR)
collection = client.get_or_create_collection("story", metadata={"hnsw:space": "cosine"})

# 스토리 문서 전체를 메모리에 올려 둔다 (짧은 문서는 검색 없이 통째로 쓰기 위함)
_story_cache = {}


def _load_story(npc_id: str) -> str:
    if npc_id not in _story_cache:
        path = os.path.join(STORY_DIR, f"{npc_id}.md")
        try:
            with open(path, "r", encoding="utf-8") as f:
                _story_cache[npc_id] = f.read().strip()
        except FileNotFoundError:
            _story_cache[npc_id] = ""
    return _story_cache[npc_id]


def retrieve_context(query: str, npc_id: str) -> str:
    """
    이 NPC의 배경 정보 중 지금 대화에 필요한 부분을 돌려준다.

    - 스토리 문서가 FULL_STORY_MAX_CHARS 이하로 짧으면 검색 없이 전체를 돌려준다.
    - 길면 query(최근 대화)로 가장 관련 있는 청크 TOP_K_CHUNKS개를 찾는다.
    """
    story = _load_story(npc_id)
    if story and len(story) <= FULL_STORY_MAX_CHARS:
        return story

    if not query.strip():
        return ""

    results = collection.query(
        query_embeddings=[get_embedding(query)],
        n_results=TOP_K_CHUNKS,
        where={"npc": npc_id},  # only retrieve chunks tagged to this NPC
    )
    chunks = results["documents"][0] if results.get("documents") else []

    print(f"\n=== RAG 검색 결과 ({npc_id}) ===")
    print(f"검색어: {query[:120]}")
    for i, chunk in enumerate(chunks):
        print(f"[청크 {i+1}] {chunk[:80]}...")
    print("====================\n")

    return "\n\n---\n\n".join(chunks)
