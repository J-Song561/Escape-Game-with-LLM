"""
rag/indexer.py
──────────────
story/*.md 를 청크로 잘라 ChromaDB에 저장한다.
스토리 문서를 고쳤거나 이 파일을 고친 뒤에는 반드시 다시 실행해야 한다.

    python -m rag.indexer          # 인덱스 재구축
    python -m rag.indexer --check  # 현재 상태만 확인
"""

import os
import re
import sys
import chromadb
from rag.embedder import get_embedding

STORY_DIR = os.path.join(os.path.dirname(__file__), "../story")
DB_DIR = os.path.join(os.path.dirname(__file__), "../db/story_db")
COLLECTION_NAME = "story"
COLLECTION_META = {"hnsw:space": "cosine"}

client = chromadb.PersistentClient(path=DB_DIR)

# 한 청크의 최대 글자 수. 한국어는 띄어쓰기 단어 수보다 글자 수가 길이를 더 잘 나타낸다.
CHUNK_MAX_CHARS = 600


def _split_sentences(text: str) -> list:
    """문장 단위로 나눈다 (. ! ? 뒤 공백, 줄바꿈)."""
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p.strip() for p in parts if p.strip()]


def chunk_text(text: str, max_chars: int = CHUNK_MAX_CHARS) -> list:
    """
    1) '## 제목' 단위로 섹션을 나누고
    2) 섹션이 길면 문장 경계에서 max_chars 이하로 자르되, 앞 청크의 마지막 문장을 한 개 겹친다.
    3) 모든 청크 앞에 섹션 제목을 붙여서, 잘린 조각만 봐도 무슨 내용인지 알 수 있게 한다.
    """
    sections = re.split(r"\n(?=## )", "\n" + text)
    chunks = []

    for section in sections:
        section = section.strip()
        if not section:
            continue

        lines = section.splitlines()
        if lines[0].startswith("## "):
            header = lines[0].strip()
            body = "\n".join(lines[1:]).strip()
        else:
            header = ""
            body = section

        if not body:
            continue

        if len(body) <= max_chars:
            chunks.append(f"{header}\n{body}".strip())
            continue

        sentences = _split_sentences(body)
        current = []
        current_len = 0
        for sent in sentences:
            if current and current_len + len(sent) > max_chars:
                chunks.append(f"{header}\n{' '.join(current)}".strip())
                # 문맥 유지를 위해 마지막 문장 하나를 다음 청크에 겹친다
                current = [current[-1]]
                current_len = len(current[0])
            current.append(sent)
            current_len += len(sent) + 1
        if current:
            chunks.append(f"{header}\n{' '.join(current)}".strip())

    return chunks


def _story_npc_ids() -> list:
    return sorted(f[:-3] for f in os.listdir(STORY_DIR) if f.endswith(".md"))


def index_story_files():
    # 거리 계산 방식(cosine)을 확실히 적용하기 위해 컬렉션을 통째로 새로 만든다
    try:
        client.delete_collection(COLLECTION_NAME)
        print("Cleared existing index.")
    except Exception:
        pass
    collection = client.get_or_create_collection(COLLECTION_NAME, metadata=COLLECTION_META)

    total_chunks = 0
    for npc_id in _story_npc_ids():
        filepath = os.path.join(STORY_DIR, f"{npc_id}.md")
        with open(filepath, "r", encoding="utf-8") as f:
            text = f.read()

        chunks = chunk_text(text)
        if chunks:
            collection.add(
                ids=[f"{npc_id}_{i}" for i in range(len(chunks))],
                embeddings=[get_embedding(c) for c in chunks],
                documents=chunks,
                metadatas=[{"npc": npc_id} for _ in chunks],
            )

        print(f"Indexed {len(chunks)} chunks from {npc_id}.md")
        total_chunks += len(chunks)

    print(f"Done. Total chunks indexed: {total_chunks}")


def check_index():
    """재구축 없이 지금 ChromaDB 상태만 확인한다 (story/*.md 기준 NPC 목록 사용)."""
    collection = client.get_or_create_collection(COLLECTION_NAME, metadata=COLLECTION_META)
    print("=== 현재 ChromaDB 상태 ===")
    for npc_id in _story_npc_ids():
        res = collection.get(where={"npc": npc_id})
        n = len(res["ids"])
        preview = (res["documents"][0][:60] + "...") if res["documents"] else "(없음)"
        print(f"- {npc_id}: {n}개 청크 | 미리보기: {preview}")
    print(f"전체: {collection.count()}개")


if __name__ == "__main__":
    if "--check" in sys.argv:
        check_index()
    else:
        index_story_files()
