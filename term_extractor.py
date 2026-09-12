"""
通用词条抽取：从任意文本抽出适合写入微软拼音用户词库的短语/术语

不做垂域绑定：医学、法律、游戏、公司黑话、教材名词都走同一套规则。
古诗文节奏切分保留为可选模式（poetry）。
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

MAX_WORD_LEN = 12
MIN_WORD_LEN = 2

# 中文/兼容汉字
_CJK = re.compile(r"[㐀-䶿一-鿿豈-﫿]")
_LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_+\-./]{1,31}")
_LINE_SPLIT = re.compile(r"[\r\n]+")
# 句读切分：中英标点
_SENT_SPLIT = re.compile(r"[，。！？；：、,!?;:\s—…·「」『』【】（）()\[\]{}<>《》\"'\"]+")

_STOP_SINGLE = set(
    "的了和是在有我不这为之以而其于上下来个们地中到说得出也那得着"
    "与及或等被把让给从向对很能会可但若因所以则且又并再就只都还很"
    "theandanorofinonattoitis"  # 极短英文虚词按整词再滤
)
_STOP_WORDS = {
    "一个", "我们", "你们", "他们", "这个", "那个", "可以", "什么", "怎么",
    "因为", "所以", "但是", "如果", "然后", "已经", "没有", "不是", "就是",
    "这样", "那样", "这些", "那些", "自己", "以及", "或者", "而且", "不过",
    # 英文虚词（整词匹配，小写比较）
    "the", "and", "for", "you", "are", "with", "this", "that", "from",
    "have", "has", "was", "were", "not", "but", "all", "any", "can",
    "will", "just", "into", "than", "then", "them", "they", "what",
    "when", "who", "how", "why", "its", "it's", "a", "an", "of", "to",
    "in", "on", "at", "by", "as", "is", "or", "if", "so", "up", "out",
}


def is_cjk_ch(ch: str) -> bool:
    return bool(_CJK.match(ch))


def mostly_cjk(s: str) -> bool:
    if not s:
        return False
    cjk = sum(1 for ch in s if is_cjk_ch(ch))
    return cjk >= max(1, int(len(s) * 0.6))


def normalize_term(raw: str) -> str:
    s = raw.strip()
    s = re.sub(r"^[\s\-\*•·•·]+", "", s)
    s = re.sub(r"[\s\-\*•·•·]+$", "", s)
    s = re.sub(r"\s+", " ", s)
    s = s.strip()
    # 中文词去掉内部空格，避免占 UDL 字位
    if any(is_cjk_ch(ch) for ch in s):
        s = re.sub(r"\s+", "", s)
    return s


def looks_like_term(s: str) -> bool:
    if not s:
        return False
    s2 = normalize_term(s)
    if not s2:
        return False

    compact = re.sub(r"\s+", "", s2)
    if len(compact) < MIN_WORD_LEN:
        return False

    # 纯英文/数字术语（可含 + - _ . /）
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_+\-./]*", s2):
        if len(s2) > MAX_WORD_LEN * 2:
            return False
        if s2.lower() in _STOP_WORDS:
            return False
        return True

    # 含中文：长度按去空白后计
    if any(is_cjk_ch(ch) for ch in compact):
        if len(compact) < MIN_WORD_LEN or len(compact) > MAX_WORD_LEN:
            return False
        if s2 in _STOP_WORDS:
            return False
        return True

    return False


def _push(bucket: List[str], seen: set, term: str):
    t = normalize_term(term)
    if not looks_like_term(t):
        return
    t = normalize_term(t)
    if t in seen:
        return
    seen.add(t)
    bucket.append(t)


def extract_from_lines(text: str) -> List[str]:
    """逐行术语：整行当作一个词条（词表/名单最常见的形态）"""
    out: List[str] = []
    seen: set = set()
    for line in _LINE_SPLIT.split(text):
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"^[\s]*([-–—*•·•]|\d+[\.、)])\s*", "", line)
        # 英文多词行：空格拆成多个术语，也保留整句（若长度允许）
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_+\-./ ]*", line):
            words = [w for w in line.split() if w]
            if len(words) > 1:
                for w in words:
                    _push(out, seen, w)
                # 也收一个无空格拼接形态（便于整词联想）
                joined = "".join(words)
                if len(joined) <= MAX_WORD_LEN * 2:
                    _push(out, seen, joined)
                continue
        parts = re.split(r"[、，,;；|/]+", line)
        for p in parts:
            _push(out, seen, p)
    return out


def extract_from_sentences(text: str) -> List[str]:
    """自由文本：按标点切成短语后入词"""
    out: List[str] = []
    seen: set = set()
    # 先按行，再按标点
    for line in _LINE_SPLIT.split(text):
        if not line.strip():
            continue
        # 括号内容常是术语
        for m in re.finditer(r"[（(]([^）)]{2,20})[）)]", line):
            _push(out, seen, m.group(1))
        parts = _SENT_SPLIT.split(line)
        for p in parts:
            _push(out, seen, p)
        # 行本身若短且像术语
        _push(out, seen, line.strip())
    return out


def extract_latin_terms(text: str) -> List[str]:
    out: List[str] = []
    seen: set = set()
    for m in _LATIN_WORD.finditer(text):
        w = m.group(0)
        if len(w) >= 2 and w.lower() not in _STOP_WORDS:
            _push(out, seen, w)
    return out


def extract_auto(text: str, include_latin: bool = True) -> Dict:
    """
    自动模式：
    - 短行优先当术语
    - 长行按句读抽短语
    - 附带拉丁术语
    """
    lines = [ln for ln in _LINE_SPLIT.split(text) if ln.strip()]
    short = [ln for ln in lines if len(re.sub(r"\s+", "", ln)) <= MAX_WORD_LEN]
    long_lines = [ln for ln in lines if len(re.sub(r"\s+", "", ln)) > MAX_WORD_LEN]

    terms: List[str] = []
    seen: set = set()
    for ln in short:
        # 行内顿号拆分
        for p in re.split(r"[、，,;；|/]+", ln):
            _push(terms, seen, p)

    blob = "\n".join(long_lines)
    for t in extract_from_sentences(blob):
        _push(terms, seen, t)

    if include_latin:
        for t in extract_latin_terms(text):
            _push(terms, seen, t)

    return {
        "terms": terms,
        "stats": {
            "input_lines": len(lines),
            "short_lines": len(short),
            "long_lines": len(long_lines),
            "terms": len(terms),
        },
    }


def extract_poetry(text: str) -> Dict:
    """可选：古诗文整句 + 节奏组（临时垂域，非默认）"""
    from poetry_processor import process_text_to_entries
    terms, stats = process_text_to_entries(text)
    return {"terms": terms, "stats": stats}


def extract(
    text: str,
    mode: str = "auto",
    include_latin: bool = True,
) -> Dict:
    """
    mode:
      - auto: 自动（推荐）
      - lines: 整行/顿号术语表
      - sentences: 按句读抽短语
      - poetry: 古诗文整句+节奏组
    """
    if not text or not text.strip():
        return {"terms": [], "stats": {"terms": 0, "mode": mode}}
    if mode == "lines":
        terms = extract_from_lines(text)
        if include_latin:
            seen = set(terms)
            for t in extract_latin_terms(text):
                if t not in seen:
                    terms.append(t)
                    seen.add(t)
        return {"terms": terms, "stats": {"mode": "lines", "terms": len(terms), "input_lines": text.count(chr(10)) + 1}}
    if mode == "sentences":
        terms = extract_from_sentences(text)
        if include_latin:
            seen = set(terms)
            for t in extract_latin_terms(text):
                if t not in seen:
                    terms.append(t)
                    seen.add(t)
        return {"terms": terms, "stats": {"mode": "sentences", "terms": len(terms)}}
    if mode == "poetry":
        return extract_poetry(text)
    result = extract_auto(text, include_latin=include_latin)
    result["stats"]["mode"] = "auto"
    return result


def term_frequency(text: str, top: int = 40) -> List[Tuple[str, int]]:
    """粗频次，便于预览哪些词在反复出现（2–4 字滑窗，仅诊断用）"""
    compact = re.sub(r"[^一-鿿A-Za-z0-9]", "", text)
    c: Counter = Counter()
    for n in (2, 3, 4):
        for i in range(0, max(0, len(compact) - n + 1)):
            w = compact[i:i + n]
            if mostly_cjk(w) or w.isascii():
                c[w] += 1
    # 过滤单次且含停用倾向的
    items = [(w, n) for w, n in c.most_common(top * 3) if n >= 2 and w not in _STOP_WORDS]
    return items[:top]
