LM_STUDIO_BASE_URL = "http://localhost:1234/v1"
LM_STUDIO_MODEL = "qwen3-4b"

# ── RAG ──
TOP_K_CHUNKS = 3  # how many RAG chunks to retrieve per query
# 스토리 문서가 이 글자 수 이하인 NPC는 검색 대신 문서 전체를 프롬프트에 넣는다
# (문서가 짧으면 검색으로 일부만 뽑는 것보다 전체가 더 정확하다)
FULL_STORY_MAX_CHARS = 3500

# ── 대화 기억 ──
# NPC 답변을 만들 때 넣어 주는 "이 NPC와의 최근 메시지" 개수 (유저+NPC 합계, 10 = 5턴)
RECENT_MESSAGES = 10

# ── NPC 답변 생성 파라미터 (Qwen3 non-thinking 모드 권장값 기준) ──
GEN_TEMPERATURE = 0.7
GEN_TOP_P = 0.8
GEN_TOP_K = 20
GEN_PRESENCE_PENALTY = 1.0   # 같은 표현 반복 억제 (0~2)
GEN_REPEAT_PENALTY = 1.05    # LM Studio 전용 반복 억제

# ── 요약/호감도 같은 분석용 호출 파라미터 (일관된 JSON이 필요해서 낮은 온도) ──
ANALYSIS_TEMPERATURE = 0.2
ANALYSIS_MAX_TOKENS = 500
