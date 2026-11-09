from sentence_transformers import SentenceTransformer

# Load once at startup
embedder = SentenceTransformer("nlpai-lab/KURE-v1")  # 한국어 최적화 임베딩 모델


def get_embedding(text: str) -> list:
    # 코사인 유사도로 검색하므로 정규화해서 저장/검색한다
    return embedder.encode(text, normalize_embeddings=True).tolist()
