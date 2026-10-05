"""
backend/rag/build_index.py

스토리 문서(backend/story/*.md)를 청크로 쪼개서 ChromaDB(story_db)에 넣는 스크립트.
- NPC별로 "## 헤더" 단위로 청크를 나눔 (ella.md 확인해보니 이미 ## 섹션으로 잘 나뉘어 있어서 그대로 활용)
- 재실행해도 안전함: 매번 해당 NPC의 기존 청크를 전부 지우고 새로 넣으므로 중복/스테일 데이터 없음
- story/*.md 파일을 수정(마리아 추가 등)한 뒤에는 이 스크립트를 반드시 다시 돌려야 ChromaDB에 반영됨

사용법 (backend 폴더 안에서):
    python -m rag.build_index          # 전체 재구축 + 결과 요약 출력
    python -m rag.build_index --check  # 재구축 없이 지금 DB 상태만 확인 (빠름, 안전)

먼저 --check 로 지금 상태부터 확인해보세요.
마리아가 0개로 나오거나 미리보기가 옛날 내용이면 재구축이 필요한 겁니다.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backend/ 를 import 경로에 추가

import chromadb
from rag.embedder import get_embedding
from npc.npc_list import VALID_NPCS

STORY_DIR = os.path.join(os.path.dirname(__file__), "..", "story")
DB_DIR = os.path.join(os.path.dirname(__file__), "..", "db", "story_db")


def chunk_story(text: str):
    """'## 헤더' 단위로 쪼갠다. 헤더가 없으면 전체를 한 덩어리로 취급."""
    parts = re.split(r"(?=^##\s)", text, flags=re.MULTILINE)
    chunks = [p.strip() for p in parts if p.strip()]
    if chunks:
        return chunks
    return [text.strip()] if text.strip() else []


def build():
    client = chromadb.PersistentClient(path=DB_DIR)
    collection = client.get_or_create_collection("story")

    print(f"기존 전체 청크 수: {collection.count()}")

    for npc_id in VALID_NPCS:
        path = os.path.join(STORY_DIR, f"{npc_id}.md")
        if not os.path.exists(path):
            print(f"[경고] {npc_id}.md 없음 — 건너뜀")
            continue

        with open(path, "r", encoding="utf-8") as f:
            text = f.read()

        chunks = chunk_story(text)
        if not chunks:
            print(f"[경고] {npc_id}.md 내용이 비어있음 — 건너뜀")
            continue

        # 이 NPC의 기존 청크 전부 삭제 후 재삽입 (중복/스테일 데이터 방지)
        existing = collection.get(where={"npc": npc_id})
        if existing["ids"]:
            collection.delete(ids=existing["ids"])

        ids = [f"{npc_id}_{i}" for i in range(len(chunks))]
        embeddings = [get_embedding(c) for c in chunks]
        metadatas = [{"npc": npc_id} for _ in chunks]

        collection.add(ids=ids, embeddings=embeddings, documents=chunks, metadatas=metadatas)
        print(f"[{npc_id}] {len(chunks)}개 청크 저장 완료")

    print(f"\n완료. 전체 청크 수: {collection.count()}")
    print_summary(collection)


def print_summary(collection=None):
    if collection is None:
        client = chromadb.PersistentClient(path=DB_DIR)
        collection = client.get_or_create_collection("story")

    print("\n=== 현재 ChromaDB 상태 ===")
    for npc_id in VALID_NPCS:
        res = collection.get(where={"npc": npc_id})
        n = len(res["ids"])
        preview = (res["documents"][0][:60] + "...") if res["documents"] else "(없음)"
        print(f"- {npc_id}: {n}개 청크 | 미리보기: {preview}")
    print(f"전체: {collection.count()}개\n")


if __name__ == "__main__":
    if "--check" in sys.argv:
        print_summary()
    else:
        build()