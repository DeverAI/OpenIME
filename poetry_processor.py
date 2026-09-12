"""
古诗文处理模块（竞赛向）

策略：
1. 整句入库：每句（≤12字）作为完整词条，便于整句打出
2. 节奏组入库：按格律切分，便于边想边打
3. 词/较长句按标点断开后仍保证 ≤12 字
"""

import re
from typing import Dict, List, Optional, Tuple

PUNCT_RE = re.compile(r'[\s，。、；：！？“”‘’（）《》【】…—\-·,.!?;:"\'()\[\]{}<>]+')
CJK_RE = re.compile(r'[一-鿿]')

# UDL 单条最大字数（60 字节结构限制）
MAX_WORD_LEN = 12


def clean_line(text: str) -> str:
    return PUNCT_RE.sub('', text.strip())


def is_mostly_cjk(text: str) -> bool:
    if not text:
        return False
    cjk = sum(1 for ch in text if '一' <= ch <= '鿿')
    return cjk >= max(1, int(len(text) * 0.8))


def detect_form(clean: str) -> str:
    n = len(clean)
    if n <= 0:
        return '杂言'
    if n == 4 or n % 4 == 0 and n <= 8:
        # 4 字多为四言；8 字可能是四言两句合并，交给分句处理
        if n == 4:
            return '四言'
    if n == 5:
        return '五言'
    if n == 6:
        return '六言'
    if n == 7:
        return '七言'
    if n == 8:
        return '杂言'
    if n == 9 or n == 10:
        return '杂言'
    return '杂言'


def rhythm_groups(clean: str, form: Optional[str] = None) -> List[str]:
    """按格律切节奏组；过长句按 2/3 优先滚动切分"""
    if not clean:
        return []
    if form is None:
        form = detect_form(clean)

    patterns = {
        '四言': [2, 2],
        '五言': [2, 3],
        '六言': [2, 2, 2],
        '七言': [2, 2, 3],
    }
    pattern = patterns.get(form)
    groups: List[str] = []
    pos = 0
    if pattern:
        for size in pattern:
            if pos < len(clean):
                chunk = clean[pos:pos + size]
                if chunk:
                    groups.append(chunk)
                pos += size
    # 剩余或杂言：2-3 混合滚动
    while pos < len(clean):
        size = 2 if (len(clean) - pos) != 3 else 3
        # 末尾若只剩 1 字，并入上一组
        if len(clean) - pos == 1 and groups:
            groups[-1] += clean[pos]
            pos += 1
            continue
        chunk = clean[pos:pos + size]
        if chunk:
            groups.append(chunk)
        pos += size
    return [g for g in groups if len(g) >= 2]


def split_poetry_lines(text: str) -> List[str]:
    parts = re.split(r'[，。；：！？!?,;:\n\r]+', text.strip())
    return [p.strip() for p in parts if p.strip()]


def entries_from_line(line: str) -> List[str]:
    """
    单句 → 候选词条：整句 + 节奏组
    自动裁剪到 MAX_WORD_LEN
    """
    clean = clean_line(line)
    if not clean or not is_mostly_cjk(clean):
        return []

    out: List[str] = []

    def push(w: str):
        w = clean_line(w)
        if not w or len(w) < 2 or len(w) > MAX_WORD_LEN:
            return
        if not is_mostly_cjk(w):
            return
        if w not in out:
            out.append(w)

    # 整句（过长则按节奏组拼接出多条 ≤12 字）
    if len(clean) <= MAX_WORD_LEN:
        push(clean)
    else:
        # 滚动窗口：每 7 字左右一条完整短语
        i = 0
        while i < len(clean):
            take = min(7, len(clean) - i)
            # 避免末尾单字
            if len(clean) - (i + take) == 1 and take > 2:
                take -= 1
            push(clean[i:i + take])
            i += take

    for g in rhythm_groups(clean):
        push(g)

    return out


def entries_from_poem(title: str, lines: List[str]) -> List[str]:
    """整首诗 → 词条列表（含标题）"""
    out: List[str] = []

    def push(w: str):
        w = clean_line(w)
        if w and 2 <= len(w) <= MAX_WORD_LEN and w not in out:
            out.append(w)

    push(title)
    for line in lines:
        for w in entries_from_line(line):
            push(w)
    return out


def extract_poem_blocks(text: str) -> List[Dict]:
    """
    从自由文本提取诗块。

    支持：
    - 《标题》作者
    - 标题
      正文...
    - 纯正文多句
    """
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    lines_raw = [ln.strip() for ln in text.split('\n') if ln.strip()]
    poems: List[Dict] = []
    current: Optional[Dict] = None

    def flush():
        nonlocal current
        if current and current['lines']:
            poems.append(current)
        current = None

    for raw in lines_raw:
        clean = clean_line(raw)
        if not clean:
            continue

        # 《标题》 或 短标题行（≤10字且不像正文整句）
        m = re.match(r'^《([^》]+)》\s*(.*)$', raw)
        if m:
            flush()
            title = m.group(1).strip()
            author = clean_line(m.group(2)) if m.group(2) else ''
            current = {'title': title, 'author': author, 'lines': []}
            continue

        # 纯短标题：4-12 字，无标点，且下一行才开始正文
        if (
            current is None
            and len(clean) <= 12
            and not re.search(r'[，。；：！？]', raw)
            and is_mostly_cjk(clean)
        ):
            # 可能是标题也可能是单句诗；先当标题，若后面没有正文会在 flush 时把本行当正文
            current = {'title': clean, 'author': '', 'lines': []}
            continue

        if current is None:
            current = {'title': '', 'author': '', 'lines': []}

        current['lines'].extend(split_poetry_lines(raw))

    flush()

    # 修正：标题误吞单句诗（标题对象只有一行且标题本身像正文）
    fixed = []
    for p in poems:
        if not p['title'] and not p['lines']:
            continue
        if p['title'] and not p['lines']:
            # 标题被当成唯一内容 → 当作一句诗
            fixed.append({'title': '', 'author': '', 'lines': [p['title']]})
        else:
            fixed.append(p)
    return fixed


def process_text_to_entries(text: str) -> Tuple[List[str], Dict]:
    """
    自由文本 → 去重词条列表 + 统计
    """
    poems = extract_poem_blocks(text)
    entries: List[str] = []
    seen = set()

    def push(w: str):
        if w and w not in seen:
            seen.add(w)
            entries.append(w)

    n_poems = len(poems)
    for p in poems:
        if p['title']:
            t = clean_line(p['title'])
            if 2 <= len(t) <= MAX_WORD_LEN:
                push(t)
        for line in p['lines']:
            for w in entries_from_line(line):
                push(w)

    stats = {
        'poems': n_poems,
        'lines': sum(len(p['lines']) for p in poems),
        'entries': len(entries),
    }
    return entries, stats


# 旧接口兼容
def is_poetry_line(text: str) -> bool:
    clean = clean_line(text)
    return 2 <= len(clean) <= MAX_WORD_LEN and is_mostly_cjk(clean)


def tokenize_poetry_line(line: str, form: str = None) -> List[str]:
    return entries_from_line(line)


def process_poetry(text: str) -> List[Tuple[List[str], str]]:
    results = []
    for line in split_poetry_lines(text):
        clean = clean_line(line)
        if clean:
            results.append((entries_from_line(clean), clean))
    return results


def split_mixed_text(text: str) -> Dict:
    entries, stats = process_text_to_entries(text)
    return {
        'normal': entries,
        'poetry': [( [e], e) for e in entries],
        'stats': stats,
    }
