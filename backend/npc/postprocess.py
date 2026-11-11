"""
npc/postprocess.py
──────────────────
LLM이 만든 NPC 답변을 유저에게 보여주기 전에 다듬는다.

- <think> 태그, 마크다운, "엘라:" 같은 이름표, 답변 전체를 감싼 따옴표 제거
- 정해진 문장 수를 넘기면 자르기
- max_tokens에 걸려 문장 중간에 끊긴 경우, 마지막 완결 문장까지만 남기기
- 이모지, 이모티콘(^^, ㅎㅎ, ㅠㅠ)은 조용히 지운다 (재생성할 정도의 문제는 아니라서)
- 한국어가 아닌 글자(한자, 일본어, 영어, 러시아어 등)가 섞였는지 검사
- 직전 답변과 거의 같은 문장을 되풀이했는지 검사
  (두 검사는 main.py에서 재생성 여부 판단에 사용)
"""

import difflib
import re
from typing import List

HANZI_RE = re.compile(r"[一-鿿㐀-䶿豈-﫿]")
# 영어 알파벳은 한 글자라도 잡는다. NPC 대사에는 필요 없고,
# 베트남어("lạ")처럼 알파벳 한 글자 + 특수 문자로 섞여 나오는 경우가 있다.
LATIN_WORD_RE = re.compile(r"[A-Za-z]")
# 한자 말고도 Qwen이 가끔 섞는 다른 문자들
OTHER_SCRIPT_RE = re.compile(
    "["
    "぀-ヿㇰ-ㇿｦ-ﾟ"  # 일본어 히라가나/가타카나
    "À-ɏḀ-ỿ"               # 악센트 붙은 라틴 문자 (é, ñ, ư, 베트남어 ạ 등)
    "Ａ-Ｚａ-ｚ"               # 전각 영문 (Ａ, ｂ)
    "Ͱ-ϿЀ-ӿ"               # 그리스, 키릴(러시아)
    "֐-׿؀-ۿ"               # 히브리, 아랍
    "ऀ-ॿ฀-๿"               # 데바나가리, 태국
    "�"                                   # 깨진 글자(�): 모델이 한글을 반쯤 만들다 만 경우
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


_NORM_RE = re.compile(r"[\s.,!?…~\"'“”‘’()\[\]]")
REPEAT_MIN_CHARS = 6      # 이보다 짧은 문장("그렇군요.")은 반복 검사에서 뺀다
REPEAT_THRESHOLD = 0.6    # 직전 답변과 글자 유사도가 이 이상이면 같은 문장으로 본다
# 짧은 문장은 "진짜 긴장해서요"/"진짜 궁금해요"처럼 몇 글자만 겹쳐도 0.6을 넘으므로 더 엄격하게 본다
SHORT_SENTENCE_CHARS = 10
SHORT_REPEAT_THRESHOLD = 0.8
# 예시 대사는 같은 상황이면 비슷한 말이 나오는 게 자연스러우므로, 거의 그대로 베낀 경우만 잡는다
EXAMPLE_COPY_THRESHOLD = 0.85


def _norm(sentence: str) -> str:
    return _NORM_RE.sub("", sentence)


def _similar(a: str, b: str, threshold: float = REPEAT_THRESHOLD) -> bool:
    return difflib.SequenceMatcher(None, a, b).ratio() >= threshold


def copied_example_sentences(reply: str, examples: List[str]) -> List[str]:
    """프롬프트 예시 대사를 거의 그대로 베낀 문장을 찾는다."""
    ex = [_norm(s) for e in examples for s in split_sentences(e)]
    ex = [s for s in ex if len(s) >= REPEAT_MIN_CHARS]
    return [
        sent for sent in split_sentences(reply)
        if len(_norm(sent)) >= REPEAT_MIN_CHARS
        and any(_similar(_norm(sent), e, EXAMPLE_COPY_THRESHOLD) for e in ex)
    ]


def repeated_sentences(reply: str, previous_replies: List[str]) -> List[str]:
    """
    직전 답변들과 거의 같은 문장, 또는 이번 답변 안에서 앞 문장을 되풀이한 문장을 찾는다.
    작은 모델은 "헤일리는 저와 같은 사람입니다" → "루이스씨는 저와 같은 사람입니다"처럼
    이름만 바꿔 같은 틀을 반복하는 일이 많아서, 완전히 같은지가 아니라 유사도로 본다.
    """
    seen = [_norm(s) for r in previous_replies for s in split_sentences(r)]
    seen = [s for s in seen if len(s) >= REPEAT_MIN_CHARS]
    found = []
    for sent in split_sentences(reply):
        n = _norm(sent)
        if len(n) < REPEAT_MIN_CHARS:
            continue
        threshold = SHORT_REPEAT_THRESHOLD if len(n) < SHORT_SENTENCE_CHARS else REPEAT_THRESHOLD
        if any(_similar(n, s, threshold) for s in seen):
            found.append(sent)
        seen.append(n)
    return found


_LEADING_CONNECTIVE_RE = re.compile(r"^(하지만|그런데|근데|그래서|그리고|그러니까|그러나|그래도|게다가)(?:,\s*|\s+)")


def strip_leading_connective(text: str) -> str:
    """앞 문장을 뺀 뒤 남은 답변이 '하지만…'처럼 접속어로 시작하면 접속어를 지운다."""
    return _LEADING_CONNECTIVE_RE.sub("", text.strip())


def drop_sentences(text: str, targets: List[str]) -> str:
    """targets에 든 문장을 뺀다. 다 빠지면 빈 문자열."""
    return " ".join(s for s in split_sentences(text) if s not in targets)


META_WORD_RE = re.compile(r"유저|플레이어|인공지능|챗봇|어시스턴트")


def has_meta_word(text: str) -> bool:
    """캐릭터가 쓰면 몰입이 깨지는 단어("유저분", "플레이어" 등)가 있으면 True."""
    return bool(META_WORD_RE.search(text))


def _has_batchim(word: str) -> bool:
    """마지막 글자에 받침이 있는지 (한글이 아니면 False)."""
    code = ord(word[-1]) - 0xAC00
    return 0 <= code <= 11171 and code % 28 != 0


# 받침 유무에 따라 바뀌는 조사 쌍: (받침 있을 때, 없을 때)
_JOSA_PAIRS = [("은", "는"), ("이", "가"), ("을", "를"), ("과", "와")]


def fix_meta_words(text: str, address: str = "당신") -> str:
    """
    재생성 후에도 남았을 때의 마지막 보정: '유저분/유저님/유저' → NPC의 호칭(당신/아가씨).
    "유저분은" → "아가씨는"처럼 뒤따르는 조사도 호칭의 받침에 맞춘다.
    """
    batchim = _has_batchim(address)

    def repl(m):
        josa = m.group(3) or ""
        for with_b, without_b in _JOSA_PAIRS:
            if josa in (with_b, without_b):
                josa = with_b if batchim else without_b
                break
        return address + josa

    text = re.sub(r"(유저|플레이어)(분|님)?(은|는|이|가|을|를|과|와)?(?=[\s.,!?…~]|$)", repl, text)
    # 조사 판단이 어려운 나머지 경우("유저분이세요")는 호칭만 바꾼다
    return re.sub(r"(유저|플레이어)(분|님)?", address, text)


# 자기 이름 + 조사 → 1인칭 ("엘라의 일상" → "제 일상")
_SELF_JOSA = {
    "가": "제가", "이": "제가", "의": "제", "는": "저는", "은": "저는",
    "를": "저를", "을": "저를", "에게": "저에게", "한테": "저한테", "도": "저도",
}


def fix_self_reference(text: str, self_name: str) -> str:
    """
    작은 모델은 캐릭터를 바깥에서 설명하듯 "엘라의 마음속에서…"처럼 자기를 3인칭으로 말한다.
    NPC 자신의 이름(+ "부인")에 조사가 붙은 경우만 1인칭으로 바꾼다.
    """
    pattern = rf"{re.escape(self_name)}(?:\s?부인)?(에게|한테|가|이|의|는|은|를|을|도)(?![가-힣])"
    return re.sub(pattern, lambda m: _SELF_JOSA[m.group(1)], text)


def secret_sentences(text: str, patterns: List[str]) -> List[str]:
    """비밀을 털어놓는 문장(patterns 중 하나에 걸리는 문장)을 찾는다."""
    regs = [re.compile(p) for p in patterns]
    return [s for s in split_sentences(text) if any(r.search(s) for r in regs)]


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
