from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI

from config import LM_STUDIO_BASE_URL, LM_STUDIO_MODEL
from models.schemas import ChatRequest, ChatResponse
from npc.prompts import NPC_SYSTEMS
from npc.npc_list import VALID_NPCS
from rag.retriever import retrieve_context 

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

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    # 1. Validate NPC
    if req.npc not in VALID_NPCS:
        raise HTTPException(status_code=400, detail=f"Unknown NPC: {req.npc}")

    # 2. Get latest user message for RAG query
    user_message = req.messages[-1].content

    # 3. Retrieve relevant story context from ChromaDB
    context = retrieve_context(user_message, req.npc)

    # 4. Build enriched system prompt
    system_prompt = NPC_SYSTEMS[req.npc]
    if context:
        system_prompt += f"""

[관련 배경 정보 — 절대 직접 언급하지 말 것. 행동 지침에만 활용할 것]
{context}
"""
    system_prompt += "\n/no_think"
    
    # 5. Call LM Studio
    if MOCK_MODE:
        reply = f"[MOCK] {req.npc} 응답 테스트 | RAG context: {context[:100] if context else '없음'}"
    else:
        response = client.chat.completions.create(
            model=LM_STUDIO_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                *[{"role": m.role, "content": m.content} for m in req.messages]
            ]
        )
        reply = response.choices[0].message.content
        if not reply:  # ← 추가 (None 방어)
            reply = "..."
            
    return ChatResponse(reply=reply, npc=req.npc)