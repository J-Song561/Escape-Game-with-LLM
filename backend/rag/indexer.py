import os
import chromadb
from rag.embedder import get_embedding

# Point to your story folder and ChromaDB storage
STORY_DIR = os.path.join(os.path.dirname(__file__), "../story")
DB_DIR = os.path.join(os.path.dirname(__file__), "../db/story_db")

# Initialize ChromaDB
client = chromadb.PersistentClient(path=DB_DIR)
collection = client.get_or_create_collection("story")

def chunk_text(text: str, chunk_size: int = 300, overlap: int = 50) -> list:
    """Split text into overlapping chunks."""
    words = text.split()
    chunks = []
    start = 0

    while start < len(words):
        end = start + chunk_size
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        start += chunk_size - overlap  # overlap so context isn't lost at boundaries

    return chunks

def index_story_files():
    """Read all .md files in story/ and index them into ChromaDB."""
    
    # Clear existing data so re-running doesn't duplicate
    existing = collection.get()
    if existing["ids"]:
        collection.delete(ids=existing["ids"])
        print("Cleared existing index.")

    total_chunks = 0

    for filename in os.listdir(STORY_DIR):
        if not filename.endswith(".md"):
            continue

        npc_id = filename.replace(".md", "")  # e.g. "ella.md" → "ella"
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
                metadatas=[{"npc": npc_id}]  # tag each chunk with its NPC
            )

        print(f"Indexed {len(chunks)} chunks from {filename}")
        total_chunks += len(chunks)

    print(f"Done. Total chunks indexed: {total_chunks}")

if __name__ == "__main__":
    index_story_files()