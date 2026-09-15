"""
应用核心：微软拼音用户词库（UDL）管理

通用垂域词库工具：导入文档/文本 → 抽词 → 增删查改 → 备份恢复 → 导出词库包。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, List, Optional, Sequence

from udl_core import UdlFile, UdlEntry, get_default_udl_path, load_pinyin_table, MAX_WORD_LEN
from term_extractor import extract, normalize_term, looks_like_term, MIN_WORD_LEN
from document_loader import load_document, load_many, SUPPORTED_EXT
from paths import user_data_dir

# 串行化所有写 UDL 的操作，避免 GUI 多线程并发写坏文件
_WRITE_LOCK = threading.RLock()

# 词库解析缓存：按 (mtime_ns, size) 失效，避免 status/preview/query 反复全量解析
_ENTRIES_CACHE: dict = {"key": None, "path": None, "entries": []}


def _cache_invalidate():
    _ENTRIES_CACHE["key"] = None
    _ENTRIES_CACHE["path"] = None
    _ENTRIES_CACHE["entries"] = []


# ---------- 导入历史（manifest + 撤销） ----------

HISTORY_KEEP = 200


def _history_dir() -> str:
    d = os.path.join(user_data_dir(), "history")
    os.makedirs(d, exist_ok=True)
    return d


def _record_history(
    action: str,
    source_desc: str = "",
    added: Optional[Sequence[str]] = None,
    removed: Optional[Sequence[str]] = None,
    total: Optional[int] = None,
    backup: str = "",
):
    """每次写入成功后记一条 manifest。历史记录失败绝不影响主流程。"""
    try:
        rec = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "action": action,
            "source": source_desc or "",
            "added": list(added or []),
            "removed": list(removed or []),
            "total": total,
            "backup": backup or "",
        }
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = os.path.join(_history_dir(), f"{ts}_{action}")
        path = base + ".json"
        n = 2
        while os.path.exists(path):
            path = f"{base}_{n}.json"
            n += 1
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=2)
        # 只保留最近 HISTORY_KEEP 份（按 mtime 排序，勿按文件名——同秒 _N 后缀是字典序陷阱）
        files = _history_files()
        for old in files[HISTORY_KEEP:]:
            try:
                os.remove(old)
            except OSError:
                pass
    except Exception:
        pass


def _history_files() -> List[str]:
    """history 目录下全部 manifest 路径，新的在前。

    排序必须按文件 mtime：文件名里的同秒冲突后缀是字典序陷阱
    （import_9 > import_10），按名倒序会把"最近一次导入"取错。
    """
    d = _history_dir()
    out: List[tuple] = []
    for fn in os.listdir(d):
        if not fn.endswith(".json"):
            continue
        p = os.path.join(d, fn)
        try:
            out.append((os.path.getmtime(p), fn, p))
        except OSError:
            continue
    out.sort(reverse=True)
    return [p for _, _, p in out]


def list_history() -> List[dict]:
    """最近的操作记录，新的在前。"""
    out: List[dict] = []
    for path in _history_files():
        try:
            with open(path, "r", encoding="utf-8") as f:
                rec = json.load(f)
            rec["_file"] = path
            out.append(rec)
        except Exception:
            continue
    return out


def undo_last_import() -> OperationResult:
    """撤销最近一次导入：精确删除那批新增词条（其余词条不动）。"""
    recs = [r for r in list_history() if r.get("action") == "import"]
    if not recs:
        return OperationResult(False, "没有可撤销的导入记录")
    rec = recs[0]
    words = [w for w in (rec.get("added") or []) if w]
    if not words:
        try:
            os.remove(rec["_file"])
        except OSError:
            pass
        return OperationResult(True, "该次导入没有新增词条，已清除记录", detail=rec.get("source", ""))
    r = delete_entries(words)
    if r.ok:
        try:
            os.remove(rec["_file"])
        except OSError:
            pass
        sample = "、".join(words[:3])
        more = f" 等 {len(words)} 条" if len(words) > 3 else ""
        r.message = f"已撤销导入：删除「{sample}」{more}"
    else:
        r.message = f"撤销失败：{r.message}"
    return r


@dataclass
class ImportPreview:
    to_add: List[str]
    already: List[str]
    rejected: List[str]
    total_after: int
    source_desc: str = ""

    @property
    def add_count(self) -> int:
        return len(self.to_add)


@dataclass
class OperationResult:
    ok: bool
    message: str
    detail: str = ""
    data: dict = field(default_factory=dict)


def ensure_ready():
    load_pinyin_table()


def get_udl_path() -> str:
    return get_default_udl_path()


def udl_exists() -> bool:
    return os.path.exists(get_udl_path())


def count_entries() -> int:
    try:
        return len(load_entries())
    except Exception:
        return 0


def load_entries() -> List[UdlEntry]:
    """读取全部词条；文件未变化时直接返回缓存（返回值为共享列表，调用方不得修改）"""
    path = get_udl_path()
    if not os.path.exists(path):
        return []
    st = os.stat(path)
    key = (st.st_mtime_ns, st.st_size)
    if (
        _ENTRIES_CACHE["key"] == key
        and _ENTRIES_CACHE["path"] == path
    ):
        return _ENTRIES_CACHE["entries"]
    udl = UdlFile()
    udl.read(path)
    _ENTRIES_CACHE["key"] = key
    _ENTRIES_CACHE["path"] = path
    _ENTRIES_CACHE["entries"] = udl.entries
    return udl.entries


def _normalize_list(tokens: Iterable[str]) -> tuple[List[str], List[str]]:
    """返回 (有效, 因规则被拒)"""
    ok: List[str] = []
    bad: List[str] = []
    seen = set()
    for t in tokens:
        w = normalize_term(str(t or ""))
        if not w:
            continue
        if not looks_like_term(w):
            bad.append(w)
            continue
        if w in seen:
            continue
        seen.add(w)
        ok.append(w)
    return ok, bad


def preview_add(tokens: Sequence[str], source_desc: str = "") -> ImportPreview:
    ensure_ready()
    ok, bad = _normalize_list(tokens)
    existing = {e.word for e in load_entries()}
    to_add = [t for t in ok if t not in existing]
    already = [t for t in ok if t in existing]
    return ImportPreview(
        to_add=to_add,
        already=already,
        rejected=bad,
        total_after=len(existing) + len(to_add),
        source_desc=source_desc,
    )


def backup_udl(label: str = "manual") -> Optional[str]:
    path = get_udl_path()
    if not os.path.exists(path):
        return None
    backup_dir = os.path.join(os.path.dirname(path), "OpenIME_Backups")
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(backup_dir, f"ChsPinyinUDL_{label}_{ts}.dat")
    shutil.copy2(path, dest)
    try:
        shutil.copy2(path, path + ".bak_openime")
    except Exception:
        pass
    _prune_backups(backup_dir, keep=30)
    return dest


def _prune_backups(backup_dir: str, keep: int = 30):
    """备份只保留最近 keep 份，防止无限增长。"""
    try:
        files = [
            os.path.join(backup_dir, f)
            for f in os.listdir(backup_dir)
            if f.lower().endswith(".dat")
        ]
        files.sort(key=os.path.getmtime, reverse=True)
        for old in files[keep:]:
            try:
                os.remove(old)
            except OSError:
                pass
    except OSError:
        pass


def list_backups() -> List[str]:
    backup_dir = os.path.join(os.path.dirname(get_udl_path()), "OpenIME_Backups")
    if not os.path.isdir(backup_dir):
        return []
    files = [
        os.path.join(backup_dir, f)
        for f in os.listdir(backup_dir)
        if f.lower().endswith(".dat")
    ]
    files.sort(key=os.path.getmtime, reverse=True)
    return files


def restore_backup(backup_path: str) -> OperationResult:
    if not os.path.exists(backup_path):
        return OperationResult(False, "找不到备份文件")
    # 先验货：备份必须能解析出词条，才允许覆盖当前词库
    try:
        check = UdlFile()
        check_entries = check.read(backup_path)
    except Exception as e:
        return OperationResult(False, f"备份文件无效，已中止恢复：{e}")
    if not check_entries:
        return OperationResult(
            False,
            "备份文件里没有任何词条，已中止恢复",
            detail="如确要恢复空词库，请手动复制文件覆盖 ChsPinyinUDL.dat",
        )
    path = get_udl_path()
    if os.path.exists(path):
        backup_udl("before_restore")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        shutil.copy2(backup_path, path)
    except Exception as e:
        return OperationResult(False, f"恢复失败：{e}")
    _cache_invalidate()
    _record_history("restore", os.path.basename(backup_path), total=len(check_entries), backup=backup_path)
    return OperationResult(
        True, f"已恢复备份（{len(check_entries)} 条）", detail=backup_path, data={"count": count_entries()}
    )


def apply_tokens(tokens: Sequence[str], source_desc: str = "") -> OperationResult:
    ensure_ready()
    tokens, _bad = _normalize_list(tokens)
    if not tokens:
        return OperationResult(
            False,
            "没有可导入的有效词条",
            detail=f"词条需约 {MIN_WORD_LEN}–{MAX_WORD_LEN} 字，且不是停用虚词",
        )

    with _WRITE_LOCK:
        return _apply_tokens_locked(tokens, source_desc)


def _apply_tokens_locked(tokens: Sequence[str], source_desc: str = "") -> OperationResult:
    path = get_udl_path()
    preview = preview_add(tokens, source_desc)
    if preview.add_count == 0:
        return OperationResult(
            True,
            f"没有新增：{len(preview.already)} 条都已在词库中",
            detail=source_desc,
            data={"added": 0, "already": len(preview.already)},
        )

    try:
        backup_path = backup_udl("before_import")
    except Exception as e:
        return OperationResult(
            False,
            f"备份失败，已中止写入：{e}",
            detail="安全红线：写词库前必须完成备份。请检查 OpenIME_Backups 备份目录是否可写。",
        )
    udl = UdlFile()
    if os.path.exists(path):
        try:
            udl.read(path)
        except Exception as e:
            return OperationResult(False, f"读取现有词库失败：{e}", detail="已中止，未写入")

    existing_words = {e.word for e in udl.entries}
    added = 0
    for w in preview.to_add:
        if w not in existing_words:
            udl.add_entry(w)
            existing_words.add(w)
            added += 1

    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        udl.write(path, preserve_header=True)
    except Exception as e:
        return OperationResult(False, f"写入失败：{e}", detail=f"备份：{backup_path}")

    _cache_invalidate()
    _record_history(
        "import", source_desc, added=preview.to_add,
        total=len(udl.entries), backup=backup_path or "",
    )

    samples = preview.to_add[:3]
    tip = ""
    if samples:
        tip = "\n导入后请试一试：打开记事本，打对应拼音或简拼，看候选里有没有新词。"
    return OperationResult(
        True,
        f"写入 {added} 条新词条",
        detail=(
            f"词库现共 {len(udl.entries)} 条。"
            + (f"备份：{backup_path}" if backup_path else "（原词库为空，已新建）")
            + "\n请注销重新登录，或中/英文切换一次使输入法加载。"
            + tip
        ),
        data={"added": added, "total": len(udl.entries), "backup": backup_path, "samples": samples},
    )


def import_competition_library() -> OperationResult:
    """把内置古诗文竞赛篇目（整句+节奏组）合并写入词库，幂等。"""
    try:
        import competition_data
        from poetry_processor import entries_from_poem
    except ImportError as e:
        return OperationResult(False, f"缺少竞赛库模块：{e}")
    ensure_ready()
    terms: List[str] = []
    seen = set()
    for poem in competition_data.all_poems():
        for w in entries_from_poem(poem["title"], poem["lines"]):
            if w not in seen:
                seen.add(w)
                terms.append(w)
    if not terms:
        return OperationResult(False, "竞赛库为空")
    return apply_tokens(
        terms, source_desc=f"古诗文竞赛库（{competition_data.library_summary()}）"
    )


def import_text(
    text: str,
    mode: str = "auto",
    include_latin: bool = True,
    source_desc: str = "",
) -> OperationResult:
    if not text or not text.strip():
        return OperationResult(False, "内容是空的")
    result = extract(text, mode=mode, include_latin=include_latin)
    terms = result.get("terms") or []
    stats = result.get("stats") or {}
    desc = source_desc or f"文本抽取 mode={stats.get('mode', mode)}，候选 {len(terms)} 条"
    r = apply_tokens(terms, source_desc=desc)
    r.data.setdefault("extract_stats", stats)
    return r


def import_files(
    paths: Sequence[str],
    mode: str = "auto",
    include_latin: bool = True,
) -> OperationResult:
    paths = list(paths)
    if not paths:
        return OperationResult(False, "未选择文件")
    docs, errors = load_many(paths)
    if not docs:
        return OperationResult(
            False,
            "文件都没读成",
            detail=(
                "\n".join(errors)
                if errors
                else "请检查格式：支持 .txt .md .csv .tsv .log .pdf .docx；.json 词库包请用「导入词库包」/ import-pack"
            ),
        )

    all_terms: List[str] = []
    seen = set()
    for d in docs:
        res = extract(d.text, mode=mode, include_latin=include_latin)
        for t in res.get("terms") or []:
            if t not in seen:
                seen.add(t)
                all_terms.append(t)

    desc = "；".join(os.path.basename(d.path) for d in docs[:5])
    if len(docs) > 5:
        desc += f" 等 {len(docs)} 个文件"
    r = apply_tokens(all_terms, source_desc=desc)
    warn = "\n".join(w for w in [d.warning for d in docs if d.warning] + errors if w)
    if warn:
        r.detail = (r.detail + "\n\n提示：\n" + warn) if r.detail else ("提示：\n" + warn)
    return r


def import_file(path: str, mode: str = "auto", include_latin: bool = True) -> OperationResult:
    return import_files([path], mode=mode, include_latin=include_latin)


def add_words(words: Sequence[str]) -> OperationResult:
    return apply_tokens(words, source_desc="手动添加")


def import_pack(path: str, merge: bool = True) -> OperationResult:
    """导入 OpenIME 词库包 JSON"""
    if not os.path.exists(path):
        return OperationResult(False, f"找不到文件：{path}")
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except Exception as e:
        return OperationResult(False, f"JSON 解析失败：{e}")

    items = data.get("entries") or data.get("words") or []
    words = []
    for it in items:
        if isinstance(it, str):
            words.append(it)
        elif isinstance(it, dict):
            words.append(it.get("word") or it.get("text") or "")

    name = data.get("name") or os.path.basename(path)
    words, _ = _normalize_list(words)
    if not merge:
        if not words:
            return OperationResult(
                False,
                "词库包里没有有效词条，已中止",
                detail="替换模式不会用空包清空你的词库",
            )
        with _WRITE_LOCK:
            ensure_ready()
            path_udl = get_udl_path()
            backup_path = backup_udl("before_replace")
            udl = UdlFile()
            if os.path.exists(path_udl):
                try:
                    udl.read(path_udl)  # 取 raw_header
                except Exception as e:
                    return OperationResult(
                        False,
                        f"当前词库无法解析，已中止替换：{e}",
                        detail="替换会覆盖旧词库；读不出旧词库头（0x470+ 索引区）时不能安全写入。请先恢复备份或手动处理。",
                    )
            udl.entries = []
            for w in words:
                udl.add_entry(w)
            try:
                os.makedirs(os.path.dirname(path_udl), exist_ok=True)
                udl.write(path_udl, preserve_header=True)
            except Exception as e:
                return OperationResult(False, f"写入失败：{e}")
            _cache_invalidate()
            _record_history(
                "replace", f"词库包「{name}」", added=words,
                total=len(udl.entries), backup=backup_path or "",
            )
            return OperationResult(True, f"已替换为 {len(udl.entries)} 条（{name}）", detail=f"备份：{backup_path}")

    return apply_tokens(words, source_desc=f"词库包「{name}」")


def export_pack(output_path: Optional[str] = None, name: str = "OpenIME 词库包") -> OperationResult:
    ensure_ready()
    if not udl_exists():
        return OperationResult(False, "本机还没有微软拼音用户词库文件")
    entries = load_entries()
    if output_path is None:
        output_path = os.path.join(
            user_data_dir(), f"词库包_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
    data = {
        "format": "openime-pack",
        "version": 1,
        "name": name,
        "export_time": datetime.now().isoformat(),
        "entry_count": len(entries),
        "entries": [
            {"word": e.word, "pinyin": e.pinyin, "timestamp": e.insert_timestamp}
            for e in entries
        ],
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return OperationResult(
        True, f"已导出 {len(entries)} 条", detail=output_path, data={"path": output_path}
    )


# 兼容旧名
def export_json(output_path: Optional[str] = None) -> OperationResult:
    return export_pack(output_path)


def import_json_config(path: str, merge: bool = True) -> OperationResult:
    return import_pack(path, merge=merge)


def _match_entry(entry: UdlEntry, kw: str) -> bool:
    """增强匹配：词条子串、拼音连写/分音节、简拼。"""
    if not kw:
        return True
    if kw in entry.word:
        return True
    # 英文词条大小写不敏感子串（如用 base / BASE 找 HBase）
    if kw.lower() in entry.word.lower():
        return True
    # 纯中文/含中文已用子串；拼音仅对 ascii 查询有意义
    if not kw.isascii():
        return False

    k = kw.lower().replace(" ", "")
    if not k:
        return False

    pys = [p for p in entry.pinyin if p]
    py_join = "".join(pys).lower()
    jp = entry.jianpin_str.strip().lower()

    if k in py_join:
        return True
    if jp and (k == jp or (len(k) <= 3 and jp.startswith(k)) or (len(jp) >= 2 and k.startswith(jp))):
        return True

    # 分音节前缀：ming yue / mingyue
    if len(k) >= 2:
        # 连续音节拼接匹配
        if py_join.startswith(k):
            return True
        # 每个查询片段都像音节前缀
        parts = [p for p in re.split(r"[ '\-]", kw.lower()) if p]
        if len(parts) >= 2:
            idx = 0
            ok = True
            for part in parts:
                found = False
                while idx < len(pys):
                    if pys[idx].lower().startswith(part):
                        found = True
                        idx += 1
                        break
                    idx += 1
                if not found:
                    ok = False
                    break
            if ok:
                return True
    return False


def query_entries(
    keyword: str = "",
    page: int = 0,
    page_size: int = 100,
) -> dict:
    """
    分页查询词库。

    返回 items / total（过滤后）/ total_all / page / pages / stats
    """
    ensure_ready()
    entries = load_entries()
    total_all = len(entries)
    kw = (keyword or "").strip()

    if kw:
        filtered = [e for e in entries if _match_entry(e, kw)]
    else:
        filtered = entries

    total = len(filtered)
    page_size = max(1, int(page_size))
    pages = max(1, (total + page_size - 1) // page_size)
    page = max(0, min(int(page), pages - 1))
    start = page * page_size
    items = filtered[start:start + page_size]

    from collections import Counter
    len_dist = Counter(len(e.word) for e in filtered)

    return {
        "items": items,
        "total": total,
        "total_all": total_all,
        "page": page,
        "page_size": page_size,
        "pages": pages,
        "keyword": kw,
        "stats": {
            "length_dist": dict(sorted(len_dist.items())),
            "avg_len": (sum(len(e.word) for e in filtered) / total) if total else 0,
        },
    }


def search_entries(keyword: str = "", limit: int = 50) -> List[UdlEntry]:
    """兼容旧接口：增强搜索 + 截断。"""
    result = query_entries(keyword=keyword, page=0, page_size=max(1, limit))
    return list(result["items"])


def delete_entries(words: Sequence[str]) -> OperationResult:
    words = [w.strip() for w in words if w and str(w).strip()]
    if not words:
        return OperationResult(False, "未选择要删除的词条")
    with _WRITE_LOCK:
        ensure_ready()
        path = get_udl_path()
        if not os.path.exists(path):
            return OperationResult(False, "词库文件不存在")
        try:
            backup_path = backup_udl("before_delete")
        except Exception as e:
            return OperationResult(False, f"备份失败，已中止删除：{e}")
        udl = UdlFile()
        try:
            udl.read(path)
        except Exception as e:
            return OperationResult(False, f"读取现有词库失败，已中止删除：{e}")
        before = len(udl.entries)
        word_set = set(words)
        removed_words = [e.word for e in udl.entries if e.word in word_set]
        udl.entries = [e for e in udl.entries if e.word not in word_set]
        removed = before - len(udl.entries)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            udl.write(path, preserve_header=True)
        except Exception as e:
            return OperationResult(False, f"写入失败：{e}")
        _cache_invalidate()
        _record_history(
            "delete", "手动删除", removed=removed_words,
            total=len(udl.entries), backup=backup_path or "",
        )
        return OperationResult(True, f"已删除 {removed} 条", detail=f"备份：{backup_path}")


def update_entry_pinyin(word: str, pinyin_input) -> OperationResult:
    """人工修正某条词条的拼音（多音字）；简拼会按新拼音自动重算。"""
    word = (word or "").strip()
    if not word:
        return OperationResult(False, "缺少词条")
    if isinstance(pinyin_input, str):
        pys = [p for p in re.split(r"[\s,，、]+", pinyin_input.strip()) if p]
    else:
        pys = [str(p).strip() for p in (pinyin_input or []) if str(p).strip()]

    with _WRITE_LOCK:
        ensure_ready()
        path = get_udl_path()
        if not os.path.exists(path):
            return OperationResult(False, "词库文件不存在")
        udl = UdlFile()
        try:
            udl.read(path)
        except Exception as e:
            return OperationResult(False, f"读取现有词库失败，已中止：{e}")
        target = udl.find_entry(word)
        if not target:
            return OperationResult(False, f"词库里没有「{word}」")
        n = len(target.word)
        if len(pys) < n:
            pys = pys + [""] * (n - len(pys))
        pys = pys[:n]
        try:
            backup_path = backup_udl("before_edit")
        except Exception as e:
            return OperationResult(False, f"备份失败，已中止修改：{e}")
        target.pinyin = pys
        target.jianpin = b"\x00\x00\x00"  # 写入时按新拼音重算简拼
        try:
            udl.write(path, preserve_header=True)
        except Exception as e:
            return OperationResult(False, f"写入失败：{e}", detail=f"备份：{backup_path}")
        _cache_invalidate()
        _record_history(
            "edit", f"修改拼音：{word}", added=[word],
            total=len(udl.entries), backup=backup_path or "",
        )
        shown = " ".join(p for p in pys if p) or "（未提供音节，缺省位将用哨兵索引）"
        return OperationResult(True, f"已更新「{word}」的拼音", detail=shown)


def status_summary() -> dict:
    ensure_ready()
    path = get_udl_path()
    exists = os.path.exists(path)
    return {
        "path": path,
        "exists": exists,
        "count": count_entries() if exists else 0,
        "backups": len(list_backups()),
        "supported": " ".join(sorted(SUPPORTED_EXT)),
    }
