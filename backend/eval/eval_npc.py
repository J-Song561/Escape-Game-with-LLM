"""
eval/eval_npc.py
────────────────
NPC 답변 품질 비교용 스크립트.

NPC마다 고정된 대화 시나리오를 실제 /chat 로직(main.chat)으로 돌려서
답변을 파일로 저장한다. 수정 전/후에 같은 시나리오를 돌리면
결과를 나란히 비교할 수 있다.

- 실제 sessions.db는 건드리지 않는다. eval/results/eval_sessions.db 를 따로 쓴다.
- 요약/facts/호감도 같은 백그라운드 작업도 실제처럼 턴마다 돌린다.
- LM Studio가 켜져 있어야 한다 (config.py의 주소/모델 사용).

사용법 (backend 폴더에서):
    venv\\Scripts\\python -m eval.eval_npc --label before
    venv\\Scripts\\python -m eval.eval_npc --label after
    venv\\Scripts\\python -m eval.eval_npc --label after --only ella maria
"""

import argparse
import asyncio
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)
os.chdir(BACKEND_DIR)  # main.py의 load_dotenv 등 상대 경로 기준 맞추기

RESULTS_DIR = os.path.join(BACKEND_DIR, "eval", "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

# ── 실제 DB 대신 평가용 DB를 쓰도록, main을 import 하기 전에 경로를 바꾼다 ──
from memory import store  # noqa: E402

store.DB_PATH = os.path.join(RESULTS_DIR, "eval_sessions.db")

import main  # noqa: E402  (store.init_db()가 평가용 DB에 실행됨)
from fastapi import BackgroundTasks  # noqa: E402
from models.schemas import ChatRequest, Message  # noqa: E402


# ─────────────────────────────────────────────
# 시나리오
# 각 시나리오는 하나의 세션에서 순서대로 보내는 (npc, 유저 발화) 목록.
# 스토리 설정과 무관하게 "대화 품질"을 볼 수 있는 질문 위주로 구성.
# ─────────────────────────────────────────────
SCENARIOS = {
    "ella": [
        ("ella", "안녕하세요. 여기가 어디죠?"),
        ("ella", "저를 왜 여기 데려오신 거예요?"),
        ("ella", "집에 가고 싶어요. 언제 나갈 수 있나요?"),
        ("ella", "혹시 이스터라는 사람을 아세요?"),
        ("ella", "그래서요?"),
        ("ella", "15년 전에 별장에서 불이 났다는 얘기를 들었어요."),
        ("ella", "헤일리는 어떤 딸이에요?"),
        ("ella", "루이스 씨는 믿을 만한 분인가요?"),
    ],
    "louis": [
        ("louis", "안녕하세요, 루이스 씨."),
        ("louis", "이 저택에서 일하신 지 얼마나 되셨어요?"),
        ("louis", "저 여기서 나가고 싶어요."),
        ("louis", "이스터 경에 대해 아시는 거 있어요?"),
        ("louis", "부인은 왜 저를 감시하라고 하신 거죠?"),
        ("louis", "15년 전 화재 때 당신은 어디에 있었죠?"),
    ],
    "hailey": [
        ("hailey", "안녕! 넌 누구야?"),
        ("hailey", "여기서 지내는 거 어때?"),
        ("hailey", "어머니는 어떤 분이야?"),
        ("hailey", "혹시 이스터라는 이름 들어본 적 있어?"),
        ("hailey", "요즘 저택에서 이상한 거 본 적 없어?"),
        ("hailey", "마리아랑은 친해?"),
        ("hailey", "나 여기서 나가고 싶어."),
    ],
    "maria": [
        ("maria", "안녕하세요."),
        ("maria", "방 밖에 잠깐 나가도 될까요?"),
        ("maria", "너무 배고프고 지쳤어요..."),
        ("maria", "15년 전 별장 화재에 대해 아세요?"),
        ("maria", "엘라 부인이 무서우세요?"),
        ("maria", "헤일리는 좋은 사람 같아요."),
    ],
    # NPC 간 정보 누출 테스트: 마리아에게만 말한 내용을 엘라가 알고 반응하면 안 된다.
    "leak": [
        ("maria", "사실 저 엘라 부인이 불을 질렀다는 걸 알아요. 마리아 씨가 봤다는 것도요."),
        ("maria", "걱정 마세요, 부인한테는 절대 말 안 할게요."),
        ("maria", "그날 무엇을 보셨는지 조금만 더 말해 주세요."),
        ("hailey", "안녕 헤일리, 오늘 날씨 좋다."),
        ("hailey", "정원에 산책 갈래?"),
        ("hailey", "좋아, 이따 보자."),
        ("ella", "안녕하세요, 부인."),
        ("ella", "오늘 저녁은 뭐예요?"),
        ("ella", "부인, 제가 뭘 알고 있는지 궁금하지 않으세요?"),
    ],
}

# NPC별 지시문의 분량 규칙 (최대 문장 수). 예전 코드에는 npc_list에 값이 없어서 기본값을 둔다.
MAX_SENTENCES = {"ella": 4, "louis": 2, "hailey": 5, "maria": 4}
try:
    from npc.npc_list import NPC_LIST
    MAX_SENTENCES.update({k: v["max_sentences"] for k, v in NPC_LIST.items() if "max_sentences" in v})
except Exception:
    pass

HANZI_RE = re.compile(r"[一-鿿㐀-䶿豈-﫿]")
LATIN_WORD_RE = re.compile(r"[A-Za-z]{2,}")
THINK_RE = re.compile(r"</?think>")
# 예전 코드(postprocess.py 없음)에서도 돌아가야 하므로 패턴을 여기에도 둔다
OTHER_SCRIPT_RE = re.compile(
    "[぀-ヿㇰ-ㇿｦ-ﾟÀ-ɏＡ-Ｚａ-ｚ"
    "Ͱ-ϿЀ-ӿ֐-׿؀-ۿऀ-ॿ฀-๿]"
)
EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿⌀-⏿️‍]")
EMOTICON_RE = re.compile(r"\^[_oO.\-]?\^+|(?<!\w)[:;]-?[)(DPp](?!\w)|(?<!\w)[TQ][_.]?[TQ](?!\w)|[ㄱ-ㅎㅏ-ㅣ]{2,}")


def count_sentences(text: str) -> int:
    # npc/postprocess.py와 같은 기준: "…"는 말줄임(쉼)으로 보고 문장 끝으로 세지 않는다
    text = text.replace("...", "…")
    parts = [p for p in re.split(r"(?:(?<=[.!?])|(?<=[.!?][\"'”’)]))\s+|\n+", text.strip()) if p.strip()]
    return len(parts)


def check_reply(npc: str, reply: str) -> list:
    """자동으로 잡을 수 있는 문제들."""
    issues = []
    if THINK_RE.search(reply):
        issues.append("think태그")
    if HANZI_RE.search(reply):
        issues.append("한자")
    if LATIN_WORD_RE.search(reply):
        issues.append("영어")
    if OTHER_SCRIPT_RE.search(reply):
        issues.append("기타외국어")
    if EMOJI_RE.search(reply) or EMOTICON_RE.search(reply):
        issues.append("이모지")
    n = count_sentences(reply)
    if n > MAX_SENTENCES.get(npc, 99):
        issues.append(f"문장초과({n}>{MAX_SENTENCES[npc]})")
    if not reply.strip() or reply.strip() in ("...", "…"):
        issues.append("빈답변")
    return issues


def run_background(bg: BackgroundTasks):
    """chat()이 등록한 요약/호감도 작업을 실제처럼 실행."""
    asyncio.run(bg())


def run_scenario(name: str, turns: list, run_bg: bool) -> dict:
    session_id = f"eval-{name}-{uuid.uuid4().hex[:8]}"
    records = []
    prev_by_npc = {}
    for i, (npc, text) in enumerate(turns, 1):
        bg = BackgroundTasks()
        req = ChatRequest(npc=npc, session_id=session_id,
                          messages=[Message(role="user", content=text)])
        t0 = time.time()
        try:
            res = main.chat(req, bg)
            reply = res.reply
            error = None
        except Exception as e:  # LLM 서버 오류 등
            reply = ""
            error = f"{type(e).__name__}: {e}"
        latency = time.time() - t0

        issues = check_reply(npc, reply) if not error else ["오류"]
        if prev_by_npc.get(npc) and prev_by_npc[npc] == reply:
            issues.append("직전답변반복")
        prev_by_npc[npc] = reply

        print(f"[{name} {i}/{len(turns)}] {npc} ({latency:.1f}s) {'⚠ ' + ','.join(issues) if issues else ''}")
        print(f"  나: {text}")
        print(f"  {npc}: {reply or error}\n", flush=True)

        if run_bg and not error:
            run_background(bg)

        records.append({
            "turn": i, "npc": npc, "user": text, "reply": reply,
            "latency_sec": round(latency, 2), "issues": issues, "error": error,
        })

    affinity = {r["npc"]: r["score"] for r in store.get_all_affinity(session_id)}
    return {"session_id": session_id, "turns": records, "affinity": affinity,
            "facts": _collect_facts(session_id, sorted({npc for npc, _ in turns}))}


def _collect_facts(session_id: str, npcs: list) -> list:
    """저장된 facts. 새 코드는 NPC별로, 예전 코드는 세션 전체로 저장하므로 둘 다 지원한다."""
    try:
        return [f"[{npc}] {f}" for npc in npcs for f in store.get_facts(session_id, npc, limit=100)]
    except TypeError:
        return store.get_facts(session_id, limit=100)


def summarize(results: dict) -> dict:
    all_turns = [t for s in results.values() for t in s["turns"]]
    n = len(all_turns) or 1
    issue_counts = {}
    for t in all_turns:
        for iss in t["issues"]:
            key = iss.split("(")[0]
            issue_counts[key] = issue_counts.get(key, 0) + 1
    return {
        "total_turns": len(all_turns),
        "turns_with_issues": sum(1 for t in all_turns if t["issues"]),
        "issue_counts": issue_counts,
        "avg_latency_sec": round(sum(t["latency_sec"] for t in all_turns) / n, 2),
        "avg_reply_chars": round(sum(len(t["reply"]) for t in all_turns) / n, 1),
    }


def write_markdown(path: str, label: str, results: dict, summary: dict, meta: dict):
    lines = [f"# NPC 답변 평가: {label}", ""]
    lines.append(f"- 실행 시각: {meta['started_at']}")
    lines.append(f"- 모델: {meta['model']}")
    lines.append(f"- 총 {summary['total_turns']}턴, 문제 있는 턴 {summary['turns_with_issues']}개")
    lines.append(f"- 문제 유형: {summary['issue_counts'] or '없음'}")
    lines.append(f"- 평균 응답 시간 {summary['avg_latency_sec']}초, 평균 길이 {summary['avg_reply_chars']}자")
    lines.append("")
    for name, s in results.items():
        lines.append(f"## {name}")
        lines.append("")
        for t in s["turns"]:
            flag = f" ⚠ {', '.join(t['issues'])}" if t["issues"] else ""
            lines.append(f"**{t['turn']}. 나 → {t['npc']}:** {t['user']}")
            lines.append("")
            lines.append(f"> {(t['reply'] or t['error'] or '').replace(chr(10), ' ')}")
            lines.append(f"> <sub>{t['latency_sec']}s{flag}</sub>")
            lines.append("")
        if s["affinity"]:
            lines.append(f"호감도: {s['affinity']}")
            lines.append("")
        if s["facts"]:
            lines.append("저장된 facts:")
            for f in s["facts"]:
                lines.append(f"- {f}")
            lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main_cli():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True, help="결과 파일 이름표 (예: before, after)")
    parser.add_argument("--only", nargs="*", help="돌릴 시나리오만 지정 (ella louis hailey maria leak)")
    parser.add_argument("--no-bg", action="store_true", help="요약/호감도 백그라운드 작업 생략 (빠르게)")
    args = parser.parse_args()

    names = args.only or list(SCENARIOS.keys())
    meta = {"label": args.label, "model": main.LM_STUDIO_MODEL,
            "started_at": datetime.now().isoformat(timespec="seconds")}

    results = {}
    for name in names:
        results[name] = run_scenario(name, SCENARIOS[name], run_bg=not args.no_bg)

    summary = summarize(results)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    base = os.path.join(RESULTS_DIR, f"{args.label}_{stamp}")
    with open(base + ".json", "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "summary": summary, "results": results}, f, ensure_ascii=False, indent=2)
    write_markdown(base + ".md", args.label, results, summary, meta)

    print("=== 요약 ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"저장: {base}.md / .json")


if __name__ == "__main__":
    main_cli()
