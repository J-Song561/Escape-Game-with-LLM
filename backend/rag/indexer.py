import os
import re
import chromadb
from rag.embedder import get_embedding

STORY_DIR = os.path.join(os.path.dirname(__file__), "../story")
DB_DIR = os.path.join(os.path.dirname(__file__), "../db/story_db")

client = chromadb.PersistentClient(path=DB_DIR)
collection = client.get_or_create_collection("story")

def chunk_text(text: str, chunk_size: int = 150, overlap: int = 30) -> list:
    """Split by ## headers first, then by word count if section is too long."""
    sections = re.split(r'\n(?=## )', text)
    chunks = []

    for section in sections:
        if not section.strip():
            continue
        words = section.split()
        if len(words) <= chunk_size:
            # 섹션이 짧으면 그대로 하나의 청크
            chunks.append(section.strip())
        else:
            # 섹션이 너무 길면 추가 분할
            start = 0
            while start < len(words):
                end = start + chunk_size
                chunks.append(" ".join(words[start:end]))
                start += chunk_size - overlap

    return chunks

def index_story_files():
    existing = collection.get()
    if existing["ids"]:
        collection.delete(ids=existing["ids"])
        print("Cleared existing index.")

    total_chunks = 0

    for filename in os.listdir(STORY_DIR):
        if not filename.endswith(".md"):
            continue

        npc_id = filename.replace(".md", "")
        filepath = os.path.join(STORY_DIR, filename)

        with open(filepath, "r", encoding="utf-8") as f:
            text = f.read()

        chunks = chunk_text(text)

        for i, chunk in enumerate(chunks):
            chunk_id = f"{npc_id}_{i}"
            embedding = get_embedding(chunk)
            collection.add(
                ids=[chunk_id],
                embeddings=[embedding],
                documents=[chunk],
                metadatas=[{"npc": npc_id}]
            )

        print(f"Indexed {len(chunks)} chunks from {filename}")
        total_chunks += len(chunks)

    print(f"Done. Total chunks indexed: {total_chunks}")

if __name__ == "__main__":
    index_story_files()