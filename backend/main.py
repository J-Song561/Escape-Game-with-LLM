from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI

from config import LM_STUDIO_BASE_URL, LM_STUDIO_MODEL
from models.schemas import ChatRequest, ChatResponse
from npc.prompts import NPC_SYSTEMS, HARD_RULES
from npc.npc_list import VALID_NPCS
from rag.retriever import retrieve_context
from memory import store

import os
import json
import re
import threading
MOCK_MODE = os.getenv("MOCK_MODE", "false").lower() == "true"

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

client = OpenAI(
    base_url=LM_STUDIO_BASE_URL,
    api_key="lm-studio"
)

store.init_db()

# 몇 개의 메시지마다 요약/facts를 갱신할지 (테스트 2, 실사용 6)
SUMMARY_EVERY = 6

# 요약이 연속 이만큼 실패하면 그 구간은 포기하고 넘어감 (무한 재시도 방지)
MAX_SUMMARY_FAILS = 3

# ── 세션별 락 ──
# 같은 세션에서 요약이 동시에 두 번 도는 것을 막는다.
# 백그라운드로 요약을 던지면 이론상 겹칠 수 있으므로,
# 세션마다 락을 하나씩 두고 "이미 요약 중이면 스킵"한다.
_session_locks = {}
_locks_guard = threading.Lock()  # _session_locks 딕셔너리 자체를 보호


def _get_session_lock(session_id: str) -> threading.Lock:
    """세션별 락 객체를 가져온다 (없으면 생성)."""
    with _locks_guard:
        if session_id not in _session_locks:
            _session_locks[session_id] = threading.Lock()
        return _session_locks[session_id]


@app.get("/health")
def health():
    return {"status": "ok"}


def _extract_json(text: str):
    """지저분한 LLM 출력에서 JSON만 안전하게 추출. 실패 시 None."""
    text = re.sub(r"```(json)?", "", text)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None


def _maybe_update_memory(session_id: str):
    """
    마지막 요약 이후 SUMMARY_EVERY개 이상 쌓이면 요약 + facts 추출/저장.
    백그라운드에서 실행되며, 세션 락으로 중복 실행을 방지한다.
    """
    lock = _get_session_lock(session_id)

    # 이미 이 세션의 요약이 돌고 있으면 스킵 (non-blocking)
    if not lock.acquire(blocking=False):
        print(f">>> [MEMORY] 세션 {session_id} 이미 요약 중 — 스킵", flush=True)
        return

    try:
        total = store.count_messages(session_id)
        last = store.get_last_summary_at(session_id)
        new_messages = total - last
        print(f">>> [MEMORY] 함수 진입 | session={session_id} | total={total} | 마지막 요약 이후 {new_messages}개", flush=True)

        if new_messages < SUMMARY_EVERY:
            print(f">>> [MEMORY] 아직 {new_messages}개 (기준 {SUMMARY_EVERY}개) — 대기", flush=True)
            return
        if MOCK_MODE:
            print(">>> [MEMORY] MOCK_MODE라 스킵", flush=True)
            return

        print(">>> [MEMORY] 트리거됨! LLM에게 요약 요청 중...", flush=True)

        history = store.get_recent_messages(session_id, limit=SUMMARY_EVERY * 2)
        convo_text = "\n".join(f"[{m['role']}] {m['content']}" for m in history)

        system_prompt = (
            "너는 추리 게임의 대화 분석기다. 아래 유저와 NPC의 대화를 분석해서 "
            "반드시 아래 JSON 형식으로만 답하라. 다른 말은 절대 붙이지 마라.\n\n"
            "{\n"
            '  "summary": "유저가 무엇을 원하고 어떤 행동 패턴을 보이는지 3문장 이내 요약",\n'
            '  "facts": ["유저가 이 대화를 통해 알게 되었거나 드러난 정보들. 게임 단서뿐 아니라 유저의 의도·관심사·상황도 포함. 각 항목은 짧은 한 문장."]\n'
            "}\n\n"
            "facts 예시: [\"유저는 이스터 경이라는 인물의 존재를 알게 됨\", "
            "\"유저는 저택에서 나가는 방법을 계속 찾고 있음\", "
            "\"유저는 엘라를 의심하기 시작함\"]\n"
            "/no_think"
        )

        try:
            resp = client.chat.completions.create(
                model=LM_STUDIO_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": convo_text},
                ],
            )
            raw = (resp.choices[0].message.content or "").strip()
            data = _extract_json(raw)
            print(f">>> [MEMORY] raw 응답: {raw[:200]}", flush=True)
            print(f">>> [MEMORY] 파싱 결과: {data}", flush=True)

            if data:
                summary = str(data.get("summary", "")).strip()
                if summary:
                    store.set_summary(session_id, summary)
                    print(">>> [MEMORY] 요약 저장 완료", flush=True)

                facts = data.get("facts", [])
                if isinstance(facts, list):
                    saved = 0
                    for f in facts:
                        f = str(f).strip()
                        if f:
                            store.add_fact(session_id, f)
                            saved += 1
                    print(f">>> [MEMORY] facts {saved}개 저장 완료", flush=True)

                # 성공: 카운터 갱신 + 실패 횟수 리셋
                store.set_last_summary_at(session_id, total)
                store.reset_fail_count(session_id)
                print(f">>> [MEMORY] last_summary_at = {total} 갱신", flush=True)
            else:
                # 파싱 실패 → 실패 카운트 증가, 한계 넘으면 포기하고 넘어감
                store.increment_fail_count(session_id)
                fails = store.get_fail_count(session_id)
                print(f">>> [MEMORY] JSON 파싱 실패 ({fails}/{MAX_SUMMARY_FAILS})", flush=True)
                if fails >= MAX_SUMMARY_FAILS:
                    store.set_last_summary_at(session_id, total)
                    store.reset_fail_count(session_id)
                    print(">>> [MEMORY] 연속 실패 한계 도달 — 이번 구간 포기하고 다음으로 넘어감", flush=True)

        except Exception as e:
            # LLM 호출 자체 실패도 동일하게 카운트 (무한 재시도 방지)
            store.increment_fail_count(session_id)
            fails = store.get_fail_count(session_id)
            print(f">>> [MEMORY ERROR] {type(e).__name__}: {e} ({fails}/{MAX_SUMMARY_FAILS})", flush=True)
            if fails >= MAX_SUMMARY_FAILS:
                store.set_last_summary_at(session_id, total)
                store.reset_fail_count(session_id)
                print(">>> [MEMORY] 연속 실패 한계 도달 — 이번 구간 포기하고 다음으로 넘어감", flush=True)

    finally:
        lock.release()


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, background_tasks: BackgroundTasks):
    # 1. Validate NPC
    if req.npc not in VALID_NPCS:
        raise HTTPException(status_code=400, detail=f"Unknown NPC: {req.npc}")

    # 2. 최신 유저 메시지
    user_message = req.messages[-1].content

    # 2-1. 유저 발화 저장
    store.add_message(req.session_id, req.npc, "user", user_message)

    # 3. RAG 검색
    context = retrieve_context(user_message, req.npc)

    # 3-1. 메모리 로드
    summary = store.get_summary(req.session_id)
    facts = store.get_facts(req.session_id)
    recent = store.get_recent_messages(req.session_id, npc=req.npc, limit=6)

    # 4. 시스템 프롬프트 구성
    system_prompt = NPC_SYSTEMS[req.npc]

    if context:
        system_prompt += f"""

[관련 배경 정보 — 절대 직접 언급하지 말 것. 행동 지침에만 활용할 것]
{context}
"""

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

    system_prompt += HARD_RULES + "\n/no_think"

    # 5. LM Studio 호출
    if MOCK_MODE:
        reply = f"[MOCK] {req.npc} | RAG:{'있음' if context else '없음'} | 요약:{'있음' if summary else '없음'} | facts:{len(facts)}개"
    else:
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

    # 5-1. NPC 응답 저장
    store.add_message(req.session_id, req.npc, "assistant", reply)

    # 5-2. 요약 + facts 갱신을 백그라운드로 던짐
    #      → 유저는 응답을 즉시 받고, 요약은 뒤에서 처리됨
    #      → 응답(task1)과 요약(task2)의 분리 + 응답 지연 제거
    background_tasks.add_task(_maybe_update_memory, req.session_id)

    return ChatResponse(reply=reply, npc=req.npc)