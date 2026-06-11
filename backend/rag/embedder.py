from sentence_transformers import SentenceTransformer

# Load once at startup
embedder = SentenceTransformer("nlpai-lab/KURE-v1") #한국어 최적화 임베딩 모델 적용"

def get_embedding(text: str) -> list:
    return embedder.encode(text).tolist()