from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI

from config import LM_STUDIO_BASE_URL, LM_STUDIO_MODEL
from models.schemas import ChatRequest, ChatResponse
from npc.prompts import NPC_SYSTEMS
from npc.npc_list import VALID_NPCS
from rag.retriever import retrieve_context
from memory import store  # ← 추가: 메모리 모듈

import os
MOCK_MODE = os.getenv("MOCK_MODE", "false").lower() == "true"

app = FastAPI()

# CORS — allows Unity and frontend to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# LM Studio client
client = OpenAI(
    base_url=LM_STUDIO_BASE_URL,
    api_key="lm-studio"  # required by library but ignored by LM Studio
)

# ← 추가: 서버 시작 시 메모리 DB 초기화 (테이블 없으면 생성)
store.init_db()

# 대화가 이만큼 쌓이면 요약을 갱신 (LLM 호출 최소화를 위해 매턴 X)
SUMMARY_EVERY = 6


@app.get("/health")
def health():
    return {"status": "ok"}


def _maybe_update_summary(session_id: str):
    """
    대화가 SUMMARY_EVERY 개수마다 한 번씩만 요약을 갱신한다.
    매턴 요약하면 느려지므로 주기적으로만 수행.
    """
    total = store.count_messages(session_id)
    if total == 0 or total % SUMMARY_EVERY != 0:
        return
    if MOCK_MODE:
        return

    # 세션 전체 대화를 가져와 요약
    history = store.get_recent_messages(session_id, limit=SUMMARY_EVERY * 2)
    convo_text = "\n".join(f"[{m['role']}] {m['content']}" for m in history)

    try:
        resp = client.chat.completions.create(
            model=LM_STUDIO_MODEL,
            messages=[
                {"role": "system", "content":
                    "다음 대화를 3문장 이내로 요약해. "
                    "유저가 무엇을 알아냈는지, 무엇을 원하는지, 어떤 행동 패턴을 보이는지 위주로. "
                    "/no_think"},
                {"role": "user", "content": convo_text},
            ],
        )
        summary = (resp.choices[0].message.content or "").strip()
        if summary:
            store.set_summary(session_id, summary)
    except Exception:
        # 요약 실패해도 대화는 계속 진행 (치명적이지 않음)
        pass


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    # 1. Validate NPC
    if req.npc not in VALID_NPCS:
        raise HTTPException(status_code=400, detail=f"Unknown NPC: {req.npc}")

    # 2. Get latest user message for RAG query
    user_message = req.messages[-1].content

    # 2-1. ← 추가: 유저 발화를 메모리에 저장
    store.add_message(req.session_id, req.npc, "user", user_message)

    # 3. Retrieve relevant story context from ChromaDB
    context = retrieve_context(user_message, req.npc)

    # 3-1. ← 추가: 메모리에서 맥락 로드
    summary = store.get_summary(req.session_id)                       # 누적 요약
    facts = store.get_facts(req.session_id)                           # 유저가 알아낸 단서
    recent = store.get_recent_messages(req.session_id, npc=req.npc, limit=6)  # 이 NPC와의 최근 대화

    # 4. Build enriched system prompt
    system_prompt = NPC_SYSTEMS[req.npc]

    if context:
        system_prompt += f"""

[관련 배경 정보 — 절대 직접 언급하지 말 것. 행동 지침에만 활용할 것]
{context}
"""

    # 4-1. ← 추가: 메모리 맥락을 프롬프트에 주입
    if summary:
        system_prompt += f"""

[지금까지의 대화 맥락 — 이 유저에 대해 파악한 것]
{summary}
"""

    if facts:
        facts_text = "\n".join(f"- {f}" for f in facts)
        system_prompt += f"""

[유저가 이미 알아낸 것들 — 유저가 이걸 다시 물으면 '이미 아시잖아요' 식으로 반응 가능]
{facts_text}
"""

    system_prompt += "\n/no_think"

    # 5. Call LM Studio
    if MOCK_MODE:
        reply = f"[MOCK] {req.npc} | RAG:{'있음' if context else '없음'} | 요약:{'있음' if summary else '없음'} | facts:{len(facts)}개"
    else:
        # 최근 대화(메모리) + 이번 턴을 함께 전달
        # Unity가 보낸 req.messages 대신 서버 메모리 기준으로 재구성 → 세션 지속성 확보
        convo_messages = [{"role": m["role"], "content": m["content"]} for m in recent]

        response = client.chat.completions.create(
            model=LM_STUDIO_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                *convo_messages,
            ]
        )
        reply = response.choices[0].message.content
        if not reply:
            reply = "..."
        reply = reply.strip()

    # NPC 응답도 메모리에 저장
    store.add_message(req.session_id, req.npc, "assistant", reply)

    # 주기적으로 요약 갱신
    _maybe_update_summary(req.session_id)

    return ChatResponse(reply=reply, npc=req.npc)