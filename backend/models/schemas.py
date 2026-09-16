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
