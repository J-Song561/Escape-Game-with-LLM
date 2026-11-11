from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI

from config import (
    LM_STUDIO_BASE_URL,
    LM_STUDIO_MODEL,
    RECENT_MESSAGES,
    GEN_TEMPERATURE,
    GEN_TOP_P,
    GEN_TOP_K,
    GEN_PRESENCE_PENALTY,
    GEN_REPEAT_PENALTY,
    ANALYSIS_TEMPERATURE,
    ANALYSIS_MAX_TOKENS,
)
from models.schemas import (
    ChatRequest,
    ChatResponse,
    EndingUnlockRequest,
    EndingRecord,
    EndingsSummaryResponse,
    AffinityResponse,
    AffinityRecord,
    SessionAffinityResponse,
)
from npc.prompts import (
    build_system_prompt, example_lines, npc_address, AFFINITY_HIGH,
    SECRET_PATTERNS, SECRET_RETRY_RULE, DEFLECT_LINES,
)
from npc.npc_list import NPC_LIST, VALID_NPCS
from npc.postprocess import (
    clean_reply, has_foreign_script, drop_foreign_sentences, repeated_sentences, drop_sentences,
    secret_sentences, has_meta_word, fix_meta_words, strip_leading_connective,
    copied_example_sentences, fix_self_reference,
)
from rag.retriever import retrieve_context
from memory import store

import os
from dotenv import load_dotenv
load_dotenv()

import json
import re
import threading
MOCK_MODE = os.getenv("MOCK_MODE", "false").lower() == "true"

# 관리자용 엔딩 조회 엔드포인트 보호용 키.
# .env에 ADMIN_KEY=아무값 을 설정하면 /admin/endings?key=그값 으로만 조회 가능.
# 설정 안 하면(전시 기간 중 내부망에서만 쓰는 경우 등) 그냥 열려있음.
ADMIN_KEY = os.getenv("ADMIN_KEY", "")

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

# 같은 NPC와 메시지가 몇 개 쌓일 때마다 그 NPC와의 요약/facts를 갱신할지 (테스트 2, 실사용 6)
SUMMARY_EVERY = 6

# 요약이 연속 이만큼 실패하면 그 구간은 포기하고 넘어감 (무한 재시도 방지)
MAX_SUMMARY_FAILS = 3

# 같은 NPC와 몇 턴마다 호감도를 재판단할지
AFFINITY_EVERY = 4

# 이 점수(0~100) 이상이면 "열쇠 위치 공개" 조건 충족 (사이드퀘스트)
AFFINITY_THRESHOLD = AFFINITY_HIGH

# 한 번 판단할 때 호감도가 움직일 수 있는 최대 폭
AFFINITY_MAX_STEP = 15
# 반복 검사에 쓰는 직전 NPC 답변 개수
REPEAT_LOOKBACK = 3

# ── 세션별 락 ──
# 같은 세션에서 요약/호감도 판단이 동시에 두 번 도는 것을 막는다.
# 백그라운드로 던지면 이론상 겹칠 수 있으므로,
# (세션, NPC, 작업종류) 조합마다 락을 하나씩 두고 "이미 처리 중이면 스킵"한다.
_session_locks = {}
_locks_guard = threading.Lock()  # _session_locks 딕셔너리 자체를 보호


def _get_session_lock(key: str) -> threading.Lock:
    """키별 락 객체를 가져온다 (없으면 생성). 'session_id:npc:memory', 'session_id:npc:affinity' 형태로 사용."""
    with _locks_guard:
        if key not in _session_locks:
            _session_locks[key] = threading.Lock()
        return _session_locks[key]


@app.get("/health")
def health():
    return {"status": "ok"}


# ── LLM 호출 헬퍼 ──────────────────────────────

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


# LM Studio의 구조화 출력(json_schema)이 안 되는 버전이면 한 번 실패한 뒤로는 시도하지 않는다
_json_schema_supported = True


def _llm_json(system_prompt: str, user_text: str, schema_name: str, schema: dict):
    """
    분석용 LLM 호출. JSON 객체를 돌려준다 (실패 시 None).
    가능하면 LM Studio 구조화 출력으로 JSON 형식을 강제하고, 안 되면 일반 호출 후 파싱한다.
    """
    global _json_schema_supported
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text},
    ]
    params = dict(
        model=LM_STUDIO_MODEL,
        messages=messages,
        temperature=ANALYSIS_TEMPERATURE,
        max_tokens=ANALYSIS_MAX_TOKENS,
    )

    if _json_schema_supported:
        try:
            resp = client.chat.completions.create(
                **params,
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": schema_name, "strict": True, "schema": schema},
                },
            )
            raw = (resp.choices[0].message.content or "").strip()
            print(f">>> [LLM-JSON] {schema_name} raw: {raw[:200]}", flush=True)
            return _extract_json(raw)
        except Exception as e:
            print(f">>> [LLM-JSON] 구조화 출력 실패 → 일반 호출로 전환 ({type(e).__name__}: {e})", flush=True)
            _json_schema_supported = False

    resp = client.chat.completions.create(**params)
    raw = (resp.choices[0].message.content or "").strip()
    print(f">>> [LLM-JSON] {schema_name} raw: {raw[:200]}", flush=True)
    return _extract_json(raw)


def _format_convo(history, npc_id: str) -> str:
    """분석용 대화 텍스트. [user]/[assistant] 대신 실제 이름으로 표시한다."""
    npc_name = NPC_LIST[npc_id]["name"]
    return "\n".join(
        f"[{'유저' if m['role'] == 'user' else npc_name}] {m['content']}" for m in history
    )


# ── 백그라운드: NPC별 요약 + facts ──────────────────────────────

SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "facts": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "facts"],
}


def _maybe_update_memory(session_id: str, npc_id: str):
    """
    이 NPC와 마지막 요약 이후 SUMMARY_EVERY개 이상 쌓이면, 이 NPC와의 대화만으로 요약 + facts를 갱신한다.
    (다른 NPC와의 대화 내용이 섞이지 않게 NPC별로 따로 저장한다)
    백그라운드에서 실행되며, 락으로 중복 실행을 방지한다.
    """
    lock = _get_session_lock(f"{session_id}:{npc_id}:memory")

    # 이미 이 세션-NPC의 요약이 돌고 있으면 스킵 (non-blocking)
    if not lock.acquire(blocking=False):
        print(f">>> [MEMORY] {session_id}/{npc_id} 이미 요약 중 — 스킵", flush=True)
        return

    try:
        total = store.count_messages_by_npc(session_id, npc_id)
        last = store.get_last_summary_at(session_id, npc_id)
        new_messages = total - last
        print(f">>> [MEMORY] {session_id}/{npc_id} | total={total} | 마지막 요약 이후 {new_messages}개", flush=True)

        if new_messages < SUMMARY_EVERY:
            return
        if MOCK_MODE:
            print(">>> [MEMORY] MOCK_MODE라 스킵", flush=True)
            return

        npc_name = NPC_LIST[npc_id]["name"]
        prev_summary = store.get_summary(session_id, npc_id)
        history = store.get_recent_messages(session_id, npc=npc_id, limit=SUMMARY_EVERY * 2)
        convo_text = _format_convo(history, npc_id)

        system_prompt = (
            f"너는 추리 게임의 대화 분석기다. 아래는 유저와 NPC '{npc_name}'의 대화다.\n"
            f"[기존 요약]\n{prev_summary or '없음'}\n\n"
            "기존 요약에 새 대화 내용을 반영해서 갱신하라. 반드시 아래 JSON 형식으로만 답하라. 다른 말은 절대 붙이지 마라.\n\n"
            "{\n"
            f'  "summary": "유저가 {npc_name}에게 무엇을 묻고 원했는지, 어떤 태도를 보였는지 3문장 이내 요약",\n'
            f'  "facts": ["이 대화에서 {npc_name}이(가) 유저에게 실제로 말해 준 정보, 또는 유저가 {npc_name}에게 밝힌 사실. '
            '대화에 실제로 나온 내용만 쓴다. 각 항목은 짧은 한 문장."]\n'
            "}\n\n"
            "facts 예시: [\"유저는 이스터 경이라는 인물에 대해 물었음\", "
            "\"유저는 저택에서 나가는 방법을 계속 찾고 있음\", "
            "\"유저는 엘라를 의심하는 말을 했음\"]\n"
            "/no_think"
        )

        try:
            data = _llm_json(system_prompt, convo_text, "npc_memory", SUMMARY_SCHEMA)
            print(f">>> [MEMORY] 파싱 결과: {data}", flush=True)

            if data:
                summary = str(data.get("summary", "")).strip()
                if summary:
                    store.set_summary(session_id, npc_id, summary)

                facts = data.get("facts", [])
                saved = 0
                if isinstance(facts, list):
                    for f in facts:
                        f = str(f).strip()
                        if f:
                            store.add_fact(session_id, npc_id, f)
                            saved += 1
                print(f">>> [MEMORY] {npc_id} 요약 저장, facts {saved}개 저장", flush=True)

                # 성공: 카운터 갱신 + 실패 횟수 리셋
                store.set_last_summary_at(session_id, npc_id, total)
                store.reset_fail_count(session_id, npc_id)
            else:
                _record_summary_failure(session_id, npc_id, total, "JSON 파싱 실패")

        except Exception as e:
            # LLM 호출 자체 실패도 동일하게 카운트 (무한 재시도 방지)
            _record_summary_failure(session_id, npc_id, total, f"{type(e).__name__}: {e}")

    finally:
        lock.release()


def _record_summary_failure(session_id: str, npc_id: str, total: int, reason: str):
    """요약 실패를 기록하고, 연속 실패 한계를 넘으면 그 구간은 포기하고 넘어간다."""
    store.increment_fail_count(session_id, npc_id)
    fails = store.get_fail_count(session_id, npc_id)
    print(f">>> [MEMORY] {npc_id} 요약 실패: {reason} ({fails}/{MAX_SUMMARY_FAILS})", flush=True)
    if fails >= MAX_SUMMARY_FAILS:
        store.set_last_summary_at(session_id, npc_id, total)
        store.reset_fail_count(session_id, npc_id)
        print(">>> [MEMORY] 연속 실패 한계 도달 — 이번 구간 포기하고 다음으로 넘어감", flush=True)


# ── 백그라운드: 호감도 ──────────────────────────────

AFFINITY_SCHEMA = {
    "type": "object",
    "properties": {"score": {"type": "integer"}},
    "required": ["score"],
}


def _maybe_update_affinity(session_id: str, npc_id: str):
    """
    이 NPC와 AFFINITY_EVERY개 이상 새로 대화했으면, 최근 대화 내용을 바탕으로
    LLM에게 호감도 점수(0~100)를 다시 판단시켜 저장한다.
    백그라운드에서 실행되며, (세션, NPC) 조합 락으로 중복 실행을 방지한다.
    """
    lock = _get_session_lock(f"{session_id}:{npc_id}:affinity")

    if not lock.acquire(blocking=False):
        print(f">>> [AFFINITY] {session_id}/{npc_id} 이미 판단 중 — 스킵", flush=True)
        return

    try:
        total = store.count_messages_by_npc(session_id, npc_id)
        last = store.get_last_affinity_update_at(session_id, npc_id)
        new_messages = total - last

        if new_messages < AFFINITY_EVERY:
            return
        if MOCK_MODE:
            return

        npc = NPC_LIST[npc_id]
        current_score = store.get_affinity(session_id, npc_id)
        history = store.get_recent_messages(session_id, npc=npc_id, limit=AFFINITY_EVERY * 2)
        convo_text = _format_convo(history, npc_id)

        system_prompt = (
            "너는 추리 게임 속 NPC와 유저 사이의 호감도를 평가하는 분석기다.\n"
            f"NPC: {npc['name']} — {npc['description']}\n"
            f"이 NPC에 대한 유저의 현재 호감도 점수는 {current_score}점(0~100 범위)이다.\n"
            "호감도는 '예의 바른 말투'가 아니라 '얼마나 진정성 있게 이 NPC 개인에게 관심을 가졌는가'로 "
            "평가해야 한다. 형식적으로 존댓말만 쓰거나 인사치레만 하는 대화는 점수를 올리면 안 된다.\n\n"
            "아래 기준으로 판단하라:\n"
            "- 점수를 올려야 하는 경우: 유저가 이 NPC의 과거·감정·고민에 대해 구체적으로 묻거나, "
            "NPC가 털어놓은 이야기에 진심으로 공감하거나, NPC가 처한 상황을 배려하는 태도를 보인 경우\n"
            "- 점수를 올리면 안 되는 경우: 단순히 공손한 말투만 쓰는 경우, 단서/정보 캐내기에만 집중하고 "
            "NPC 개인에는 관심이 없는 경우, 의례적인 인사나 추임새만 반복하는 경우\n"
            "- 점수를 내려야 하는 경우: 무례하거나 공격적인 경우, NPC를 추궁·의심하는 투로 몰아붙이는 경우\n\n"
            f"변화는 점진적이어야 한다 (현재 점수에서 ±{AFFINITY_MAX_STEP}점 이내). "
            "반드시 아래 JSON 형식으로만 답하라. 다른 말은 절대 붙이지 마라.\n\n"
            "{\n"
            '  "score": 0부터 100 사이의 정수\n'
            "}\n/no_think"
        )

        try:
            data = _llm_json(system_prompt, convo_text, "affinity", AFFINITY_SCHEMA)

            if data and "score" in data:
                new_score = int(data["score"])
                # 모델이 규칙을 어겨도 한 번에 크게 움직이지 않도록 코드에서 한 번 더 제한
                new_score = max(current_score - AFFINITY_MAX_STEP, min(current_score + AFFINITY_MAX_STEP, new_score))
                store.set_affinity(session_id, npc_id, new_score)
                print(f">>> [AFFINITY] {npc_id} 호감도 {current_score} → {new_score}", flush=True)
            else:
                print(f">>> [AFFINITY] {npc_id} JSON 파싱 실패, 점수 유지", flush=True)

            store.set_last_affinity_update_at(session_id, npc_id, total)

        except Exception as e:
            print(f">>> [AFFINITY ERROR] {type(e).__name__}: {e}", flush=True)
            # 실패해도 카운터는 갱신해서 다음 AFFINITY_EVERY 턴까지 재시도를 미룸 (무한 재시도 방지)
            store.set_last_affinity_update_at(session_id, npc_id, total)

    finally:
        lock.release()


# ── 대화 ──────────────────────────────

def _build_rag_query(recent, user_message: str) -> str:
    """
    RAG 검색어. 최신 발화만 쓰면 "그래서요?" 같은 짧은 말에 엉뚱한 내용이 검색되므로
    직전 유저 발화와 직전 NPC 답변을 앞에 붙인다. (최신 발화를 마지막에 둔다)
    """
    prev_user = ""
    prev_npc = ""
    # recent의 마지막은 방금 저장한 유저 발화이므로 그 앞에서 찾는다
    for m in reversed(recent[:-1]):
        if m["role"] == "assistant" and not prev_npc:
            prev_npc = m["content"]
        elif m["role"] == "user" and not prev_user:
            prev_user = m["content"]
        if prev_user and prev_npc:
            break
    parts = [p[:200] for p in (prev_user, prev_npc) if p]
    parts.append(user_message)
    return "\n".join(parts)


def _call_npc_llm(npc_id: str, system_prompt: str, convo_messages: list, temperature: float):
    resp = client.chat.completions.create(
        model=LM_STUDIO_MODEL,
        messages=[{"role": "system", "content": system_prompt}, *convo_messages],
        temperature=temperature,
        top_p=GEN_TOP_P,
        presence_penalty=GEN_PRESENCE_PENALTY,
        max_tokens=NPC_LIST[npc_id]["max_tokens"],
        # OpenAI 표준에 없는 LM Studio 전용 파라미터
        extra_body={"top_k": GEN_TOP_K, "repeat_penalty": GEN_REPEAT_PENALTY},
    )
    choice = resp.choices[0]
    return choice.message.content or "", choice.finish_reason == "length"


def _generate_reply(npc_id: str, system_prompt: str, convo_messages: list) -> str:
    """
    NPC 답변 생성 + 후처리.
    아래 문제가 있으면 한 번 다시 생성한다.
      - 빈 답변
      - 다른 언어(한자/일본어/영어 등)가 섞임
      - 직전 답변(최근 REPEAT_LOOKBACK개)이나 프롬프트 예시 대사와 거의 같은 문장을 씀
      - 숨겨야 할 비밀을 털어놓음 (SECRET_PATTERNS)
    다시 만든 답변에도 문제가 남으면 문제 있는 문장만 빼고,
    비밀을 말한 문장은 캐릭터다운 회피 대사(DEFLECT_LINES)로 바꾼다. 비밀은 어떤 경우에도 내보내지 않는다.
    """
    npc = NPC_LIST[npc_id]
    names = [npc["name"], npc["name"].split()[0], npc_id]
    # 반복 검사: 직전 답변과 비슷한 문장(유사도 0.6), 프롬프트 예시를 거의 그대로 베낀 문장(0.85)
    recent_replies = [m["content"] for m in convo_messages if m["role"] == "assistant"][-REPEAT_LOOKBACK:]
    examples = example_lines(npc_id)
    secret_patterns = SECRET_PATTERNS.get(npc_id, [])

    def find_repeats(text: str) -> list:
        found = repeated_sentences(text, recent_replies)
        return found + [s for s in copied_example_sentences(text, examples) if s not in found]

    def generate(prompt: str, temperature: float) -> str:
        raw, truncated = _call_npc_llm(npc_id, prompt, convo_messages, temperature)
        text = clean_reply(raw, names, npc["max_sentences"], truncated)
        # "엘라의 마음속에서"처럼 자기를 3인칭으로 말하면 1인칭으로 바꾼다
        text = fix_self_reference(text, npc["name"].split()[0])
        # "…"만 있는 답변은 유저가 받을 정보가 없으므로 빈 답변으로 보고 다시 만든다
        return text if re.sub(r"[\s….!?~]", "", text) else ""

    def problems(text: str) -> dict:
        return {
            "empty": not text,
            "foreign": has_foreign_script(text),
            "repeats": find_repeats(text),
            "secrets": secret_sentences(text, secret_patterns),
            "meta": has_meta_word(text),
        }

    reply = generate(system_prompt, GEN_TEMPERATURE)
    prob = problems(reply)
    if not any(prob.values()):
        return reply

    print(f">>> [REPLY] {npc_id} 재생성 {prob} 원문: {reply[:120]!r}", flush=True)
    extra = []
    temperature = GEN_TEMPERATURE
    if prob["secrets"]:
        extra.append(SECRET_RETRY_RULE)
    if prob["meta"]:
        extra.append(f'- 상대를 "유저", "플레이어"라고 부르지 않는다. "{npc_address(npc_id)}"라고 부른다.')
    if prob["foreign"] or prob["empty"]:
        extra.append("- 한자, 일본어, 영어를 한 글자도 쓰지 않는다. 이모지도 쓰지 않는다. 순수한 한국어로만 말한다.")
        temperature = max(0.3, GEN_TEMPERATURE - 0.3)
    if prob["repeats"]:
        quoted = ", ".join(f'"{s}"' for s in prob["repeats"][:3])
        extra.append(f"- 다음 말은 이미 했으므로 쓰지 않는다: {quoted}. 다른 내용과 다른 문장 구조로 답한다.")
        if not prob["foreign"]:
            temperature = min(1.0, GEN_TEMPERATURE + 0.2)
    retry_prompt = system_prompt.replace("\n/no_think", "\n" + "\n".join(extra) + "\n/no_think")

    reply2 = generate(retry_prompt, temperature)
    if reply2 and not any(problems(reply2).values()):
        return reply2

    # 두 번 다 문제가 있으면 문제 문장을 정리한다
    # 깨진 글자(�)는 "…" 바로 뒤에 붙어 나오는 경우가 많아서, 문장째 버리지 않고 글자만 지운다
    best = drop_foreign_sentences(fix_meta_words((reply2 or reply).replace("�", ""), npc_address(npc_id)))
    # 마지막 단계에서는 '직전 답변 반복'만 뺀다. 예시 대사를 베낀 정도는 앞뒤가 안 맞는 답보다 낫다.
    leftover = drop_sentences(best, repeated_sentences(best, recent_replies))
    best = strip_leading_connective(leftover) or best
    secrets = secret_sentences(best, secret_patterns)
    if secrets:
        print(f">>> [REPLY] {npc_id} 비밀 문장 차단: {secrets}", flush=True)
        kept = strip_leading_connective(drop_sentences(best, secrets))
        best = f"{kept} {DEFLECT_LINES[npc_id]}".strip()
    return best or DEFLECT_LINES.get(npc_id, "…")


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, background_tasks: BackgroundTasks):
    # 1. Validate NPC
    if req.npc not in VALID_NPCS:
        raise HTTPException(status_code=400, detail=f"Unknown NPC: {req.npc}")

    # 2. 최신 유저 메시지 저장
    user_message = req.messages[-1].content
    store.add_message(req.session_id, req.npc, "user", user_message)

    # 3. 이 NPC와의 기억 로드 (다른 NPC와의 대화는 섞지 않는다)
    recent = store.get_recent_messages(req.session_id, npc=req.npc, limit=RECENT_MESSAGES)
    summary = store.get_summary(req.session_id, req.npc)
    facts = store.get_facts(req.session_id, req.npc)
    affinity_score = store.get_affinity(req.session_id, req.npc)

    # 4. RAG 검색 (최근 대화 흐름까지 반영한 검색어)
    context = retrieve_context(_build_rag_query(recent, user_message), req.npc)

    # 5. 시스템 프롬프트 구성
    system_prompt = build_system_prompt(
        req.npc,
        context=context,
        summary=summary,
        facts=facts,
        affinity_score=affinity_score,
    )

    # 6. LM Studio 호출
    if MOCK_MODE:
        reply = (
            f"[MOCK] {req.npc} | RAG:{'있음' if context else '없음'} | 요약:{'있음' if summary else '없음'} "
            f"| facts:{len(facts)}개 | 호감도:{affinity_score} | 프롬프트:{len(system_prompt)}자"
        )
    else:
        convo_messages = [{"role": m["role"], "content": m["content"]} for m in recent]
        try:
            reply = _generate_reply(req.npc, system_prompt, convo_messages)
        except Exception as e:
            print(f">>> [CHAT ERROR] {type(e).__name__}: {e}", flush=True)
            raise HTTPException(status_code=503, detail="LLM 서버 응답 실패")

    # 6-1. NPC 응답 저장
    store.add_message(req.session_id, req.npc, "assistant", reply)

    # 7. 요약 + facts 갱신, 호감도 갱신을 백그라운드로 던짐 (이 NPC와의 대화 기준)
    #    → 유저는 응답을 즉시 받고, 분석은 뒤에서 처리됨
    background_tasks.add_task(_maybe_update_memory, req.session_id, req.npc)
    background_tasks.add_task(_maybe_update_affinity, req.session_id, req.npc)

    return ChatResponse(reply=reply, npc=req.npc)


# ── 엔딩 수집함 ──────────────────────────────

@app.post("/endings/unlock")
def unlock_ending(req: EndingUnlockRequest):
    """
    방문자(세션)가 엔딩에 도달하면 Unity에서 호출.
    같은 세션에서 같은 엔딩을 재시도로 또 봐도 중복 저장되지 않는다.
    """
    store.unlock_ending(req.session_id, req.ending_id)
    return {"status": "ok", "session_id": req.session_id, "ending_id": req.ending_id}


@app.get("/endings/session/{session_id}")
def get_session_endings(session_id: str):
    """이 방문자(세션)가 지금까지 해금한 엔딩 목록 — 엔딩수집함 UI용."""
    return {"session_id": session_id, "endings": store.get_endings(session_id)}


@app.get("/admin/endings", response_model=EndingsSummaryResponse)
def admin_endings(key: str = ""):
    """
    관리자용 — 전시장에서 나온 모든 방문자(세션)의 엔딩 해금 기록 전체 조회.
    ADMIN_KEY가 설정되어 있으면 ?key=... 가 일치해야만 조회 가능.
    """
    if ADMIN_KEY and key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")

    records = store.get_all_endings()
    return EndingsSummaryResponse(
        total_unlocks=len(records),
        records=[EndingRecord(**r) for r in records],
    )


# ── 호감도 ──────────────────────────────

@app.get("/affinity/{session_id}/{npc}", response_model=AffinityResponse)
def get_npc_affinity(session_id: str, npc: str):
    """
    특정 세션(방문자)의 특정 NPC에 대한 호감도 조회.
    reveal_key가 true면 그 NPC가 열쇠 위치를 알려줄 조건을 충족한 것 (사이드퀘스트).
    """
    score = store.get_affinity(session_id, npc)
    return AffinityResponse(
        session_id=session_id,
        npc=npc,
        score=score,
        threshold=AFFINITY_THRESHOLD,
        reveal_key=score >= AFFINITY_THRESHOLD,
    )


@app.get("/affinity/{session_id}", response_model=SessionAffinityResponse)
def get_session_affinity(session_id: str):
    """특정 세션(방문자)의 NPC별 호감도 전체 조회."""
    records = store.get_all_affinity(session_id)
    return SessionAffinityResponse(
        session_id=session_id,
        threshold=AFFINITY_THRESHOLD,
        affinities=[AffinityRecord(**r) for r in records],
    )
