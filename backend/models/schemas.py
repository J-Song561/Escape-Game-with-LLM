from pydantic import BaseModel
from typing import List

class Message(BaseModel):
    role: str       # "user" or "assistant"
    content: str

class ChatRequest(BaseModel):
    npc: str        # "ella", "louis", "hailey"
    messages: List[Message]
    session_id: str # tracks which player/playthrough

class ChatResponse(BaseModel):
    reply: str
    npc: str


# ── 엔딩 수집함 ──────────────────────────────
# 방문자(세션)가 엔딩에 도달했을 때 클라이언트가 보내는 기록 요청과,
# 관리자가 전시장에서 나온 전체 엔딩 기록을 조회할 때 쓰는 응답 모델.

class EndingUnlockRequest(BaseModel):
    session_id: str  # 어떤 방문자(세션)가
    ending_id: str   # 어떤 엔딩을 해금했는지


class EndingRecord(BaseModel):
    session_id: str
    ending_id: str
    unlocked_at: str


class EndingsSummaryResponse(BaseModel):
    total_unlocks: int
    records: List[EndingRecord]


# ── 호감도(NPC 신뢰도) ──────────────────────────────
# LLM과의 자유 대화 내용을 바탕으로 세션(방문자)별 · NPC별 호감도를 추적한다.
# 특정 NPC의 호감도가 임계치를 넘으면 그 NPC가 열쇠 위치를 알려주는 식으로 활용 예정.
# (대상 NPC는 아직 미정이라 전 NPC 공통으로 동작하게 설계)

class AffinityResponse(BaseModel):
    session_id: str
    npc: str
    score: int              # 0~100
    threshold: int          # 이 값 이상이면 reveal_key = True
    reveal_key: bool        # 유니티가 바로 분기에 쓸 수 있도록 미리 계산해서 내려줌


class AffinityRecord(BaseModel):
    npc: str
    score: int


class SessionAffinityResponse(BaseModel):
    session_id: str
    threshold: int
    affinities: List[AffinityRecord]