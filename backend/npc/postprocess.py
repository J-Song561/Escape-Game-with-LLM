"""
npc/postprocess.py
──────────────────
LLM이 만든 NPC 답변을 유저에게 보여주기 전에 다듬는다.

- <think> 태그, 마크다운, "엘라:" 같은 이름표, 답변 전체를 감싼 따옴표 제거
- 정해진 문장 수를 넘기면 자르기
- max_tokens에 걸려 문장 중간에 끊긴 경우, 마지막 완결 문장까지만 남기기
- 이모지, 이모티콘(^^, ㅎㅎ, ㅠㅠ)은 조용히 지운다 (재생성할 정도의 문제는 아니라서)
- 한국어가 아닌 글자(한자, 일본어, 영어, 러시아어 등)가 섞였는지 검사
  (main.py에서 재생성 여부 판단에 사용)
"""

import re
from typing import List

HANZI_RE = re.compile(r"[一-鿿㐀-䶿豈-﫿]")
# 2글자 이상 영어 단어. (OK, AI 같은 짧은 단어도 잡히지만 NPC 대사에는 필요 없다)
LATIN_WORD_RE = re.compile(r"[A-Za-z]{2,}")
# 한자 말고도 Qwen이 가끔 섞는 다른 문자들
OTHER_SCRIPT_RE = re.compile(
    "["
    "぀-ヿㇰ-ㇿｦ-ﾟ"  # 일본어 히라가나/가타카나
    "À-ɏ"                            # 악센트 붙은 라틴 문자 (é, ñ, ư 등)
    "Ａ-Ｚａ-ｚ"               # 전각 영문 (Ａ, ｂ)
    "Ͱ-ϿЀ-ӿ"               # 그리스, 키릴(러시아)
    "֐-׿؀-ۿ"               # 히브리, 아랍
    "ऀ-ॿ฀-๿"               # 데바나가리, 태국
    "]"
)

# 이모지: 그림 문자, 기호/딩뱃(♡ ★ ♪ ✨ ⌛), 별(⭐), 국기, 이모지 조합용 문자
EMOJI_RE = re.compile(
    "["
    "\U0001F000-\U0001FAFF"
    "☀-➿"
    "⬀-⯿"
    "⌀-⏿"
    "︎️‍⃣"
    "]+"
)
# 텍스트 이모티콘: ^^ ^_^ ^o^ / :) :D ;) / T_T ㅠㅠ ㅜㅜ / ㅎㅎ ㅋㅋ 같은 자음·모음만 연달아 쓴 것
EMOTICON_RE = re.compile(
    r"\^[_oO.\-]?\^+"
    r"|(?<!\w)[:;]-?[)(DPp](?!\w)"
    r"|(?<!\w)[TQ][_.]?[TQ](?!\w)"
    r"|[ㄱ-ㅎㅏ-ㅣ]{2,}"
)

_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_TAG_RE = re.compile(r"</?think>")
# 문장 끝: . ! ? 뒤에 공백/끝. "…"는 말줄임(쉼)으로 보고 문장 끝으로 치지 않는다.
_SENTENCE_SPLIT_RE = re.compile(r"(?:(?<=[.!?])|(?<=[.!?][\"'”’)]))\s+")
_SENTENCE_END_RE = re.compile(r"[.!?…~][\"'”’)]*$")


def split_sentences(text: str) -> List[str]:
    """한국어 대사를 문장 단위로 나눈다. 줄바꿈도 문장 경계로 본다."""
    sentences = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        sentences.extend(s.strip() for s in _SENTENCE_SPLIT_RE.split(line) if s.strip())
    return sentences


def has_foreign_script(text: str) -> bool:
    """한국어가 아닌 글자(한자, 일본어, 영어 단어, 러시아어 등)가 섞여 있으면 True."""
    return bool(HANZI_RE.search(text) or LATIN_WORD_RE.search(text) or OTHER_SCRIPT_RE.search(text))


def strip_emoji(text: str) -> str:
    """이모지와 텍스트 이모티콘을 지우고, 그 자리에 남은 공백을 정리한다."""
    text = EMOJI_RE.sub("", text)
    text = EMOTICON_RE.sub("", text)
    text = re.sub(r"[ \t]+([.!?,…~])", r"\1", text)  # "좋아요 !" → "좋아요!"
    text = re.sub(r"[ \t]{2,}", " ", text)
    return "\n".join(line.strip() for line in text.splitlines())


def drop_foreign_sentences(text: str) -> str:
    """다른 언어가 섞인 문장만 빼고 돌려준다. 다 빠지면 빈 문자열."""
    kept = [s for s in split_sentences(text) if not has_foreign_script(s)]
    return " ".join(kept)


def _strip_wrapping(text: str, npc_names: List[str]) -> str:
    text = _THINK_BLOCK_RE.sub("", text)
    text = _TAG_RE.sub("", text)
    text = strip_emoji(text)
    text = text.replace("...", "…")
    # 마크다운 강조/제목 기호
    text = re.sub(r"\*\*|__|^#+\s*", "", text, flags=re.MULTILINE)
    text = text.replace("*", "")
    text = text.strip()

    # "엘라 부인: ..." / "[엘라] ..." 같은 이름표
    for name in npc_names:
        if not name:
            continue
        text = re.sub(rf"^\[?{re.escape(name)}\]?\s*[:：]\s*", "", text)
    text = text.strip()

    # 답변 전체가 따옴표로 감싸져 있으면 벗긴다
    pairs = [('"', '"'), ("“", "”"), ("'", "'"), ("‘", "’"), ("「", "」")]
    for left, right in pairs:
        if len(text) >= 2 and text.startswith(left) and text.endswith(right):
            inner = text[1:-1]
            if left not in inner and right not in inner:
                text = inner.strip()
            break
    return text


def clean_reply(raw: str, npc_names: List[str], max_sentences: int, truncated: bool = False) -> str:
    """
    raw        : LLM 원문
    npc_names  : 이름표 제거용 (예: ["엘라 부인", "엘라"])
    max_sentences : 이 개수를 넘으면 뒤를 자른다
    truncated  : max_tokens에 걸려 끊겼는지 (finish_reason == "length")
    """
    text = _strip_wrapping(raw or "", npc_names)
    sentences = split_sentences(text)
    if not sentences:
        return ""

    # 토큰 한도로 끊겼으면 마지막 미완성 문장은 버린다 (전부 미완성이면 그대로 둔다)
    if truncated and len(sentences) > 1 and not _SENTENCE_END_RE.search(sentences[-1]):
        sentences = sentences[:-1]

    if max_sentences and len(sentences) > max_sentences:
        sentences = sentences[:max_sentences]

    return " ".join(sentences).strip()
