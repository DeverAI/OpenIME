"""预期逻辑回归：UDL 往返、简拼、拼音表、抽词、导入安全。全部在临时 APPDATA。"""
import os
import tempfile
import shutil
from pathlib import Path

TMP = tempfile.mkdtemp(prefix="openime_logic_")
os.environ["APPDATA"] = TMP

import udl_core
from udl_core import (
    UdlFile, load_pinyin_table, get_default_udl_path, get_index_by_pinyin,
    MAX_WORD_LEN, UNKNOWN_PY_INDEX,
)
import app_core
from term_extractor import extract, looks_like_term, normalize_term

load_pinyin_table()
path = get_default_udl_path()
os.makedirs(os.path.dirname(path), exist_ok=True)
failures = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}  {detail}")
        failures.append(name)


print("== 1. 拼音表 ==")
table = udl_core.PINYIN_TABLE
check("table non-empty", len(table) >= 400, len(table))
check("idx0 is a", table[0] == "a", table[0])
check("a in table", "a" in udl_core.PINYIN_TABLE_INDEX)
check("unknown sentinel", get_index_by_pinyin("") == UNKNOWN_PY_INDEX)
check("unknown syllable", get_index_by_pinyin("notaphonesyll") == UNKNOWN_PY_INDEX)

print("== 2. 中文写入：简拼 + 拼音对齐 ==")
udl = UdlFile()
udl.add_entry("产品经理")
udl.add_entry("需求评审")
p = Path(TMP) / "u1.dat"
udl.write(str(p))
back = UdlFile()
back.read(str(p))
by_w = {e.word: e for e in back.entries}
check("2 entries", len(back.entries) == 2, len(back.entries))
e = by_w.get("产品经理")
check("exists 产品经理", e is not None)
check("pinyin 4", e and len(e.pinyin) == 4, e and e.pinyin)
check("pinyin chan", e and e.pinyin[0] == "chan", e and e.pinyin)
check("jianpin not zeros", e and e.jianpin != b"\x00\x00\x00", e and e.jianpin)
check("jianpin cpjl letters", e and e.jianpin_str.strip() in ("cpl", "cpj", "cpjl"[:3], e.jianpin_str.strip()), e and e.jianpin_str)
# 产品经理 -> chan pin jing li -> c p j
check("jianpin == cpj", e and e.jianpin_str.strip() == "cpj", e and e.jianpin_str)

print("== 3. 英文/混合词条 ==")
udl2 = UdlFile()
udl2.add_entry("HBase")
udl2.add_entry("COVID-19")
udl2.add_entry("新冠COVID")
p2 = Path(TMP) / "u2.dat"
udl2.write(str(p2))
back2 = UdlFile()
ents = back2.read(str(p2))
words = [e.word for e in ents]
check("HBase stored", "HBase" in words, words)
check("COVID-19 stored", "COVID-19" in words, words)
check("mixed stored", "新冠COVID" in words, words)
hb = next(e for e in ents if e.word == "HBase")
check("HBase pinyin aligned", len(hb.pinyin) == 5, hb.pinyin)
check("HBase pinyin empty not ai", all(py == "" for py in hb.pinyin), hb.pinyin)
check("HBase jianpin bytes", hb.jianpin and any(hb.jianpin), hb.jianpin)
check("HBase jianpin hb*", hb.jianpin_str.strip().startswith("h"), hb.jianpin_str)
cv = next(e for e in ents if e.word == "新冠COVID")
check("mixed pinyin has xin", "xin" in cv.pinyin, cv.pinyin)

print("== 4. 超长词不写坏文件 ==")
udl3 = UdlFile()
udl3.add_entry("短词有效")
udl3.from_dict_list([{"word": "一二三四五六七八九十一二三"}, {"word": "好词"}])
# from_dict_list 应跳过 13 字
check("skip 13-char in from_dict", all(len(e.word) <= 12 for e in udl3.entries), [e.word for e in udl3.entries])
# 强塞一条超长到 entries 后 write 不应抛、文件可读
udl3.entries.append(udl_core.UdlEntry(word="一二三四五六七八九十一二三四", pinyin=[]))
p3 = Path(TMP) / "u3.dat"
try:
    udl3.write(str(p3))
    check("write overflow no crash", True)
except Exception as e:
    check("write overflow no crash", False, str(e))
back3 = UdlFile()
try:
    ents3 = back3.read(str(p3))
    check("read after overflow", len(ents3) >= 1, len(ents3))
    check("all words <=12", all(len(e.word) <= 12 for e in ents3), [len(e.word) for e in ents3])
except Exception as e:
    check("read after overflow", False, str(e))

print("== 5. 抽词规则 ==")
r = extract("产品经理\n需求评审\nService Level Objective\nThe\nHBase\n新冠COVID-19\n", mode="lines")
terms = r["terms"]
check("产品经理", "产品经理" in terms)
check("Service split", "Service" in terms and "Level" in terms, terms)
check("The filtered", "The" not in terms, terms)
check("HBase kept", "HBase" in terms)
check("mixed COVID", any("COVID" in t for t in terms), terms)
check("looks mixed", looks_like_term("新冠COVID-19") or looks_like_term("新冠COVID"), "新冠COVID-19")
check("long rejected", not looks_like_term("一二三四五六七八九十一二三"))
check("stopword 我们", not looks_like_term("我们"))
check("space cjk norm", normalize_term(" 数据 库 ") == "数据库", normalize_term(" 数据 库 "))

print("== 6. 导入合并 / 幂等 / 空包保护 ==")
app_core.ensure_ready()
r = app_core.add_words(["甲乙产品", "丙丁方案"])
check("add ok", r.ok, r.message)
c1 = app_core.count_entries()
r = app_core.add_words(["甲乙产品"])
check("idempotent", r.ok and app_core.count_entries() == c1, (c1, app_core.count_entries()))
pack = Path(TMP) / "empty.json"
pack.write_text('{"name":"empty","entries":[]}', encoding="utf-8")
r = app_core.import_pack(str(pack), merge=False)
check("empty replace blocked", (not r.ok) and app_core.count_entries() == c1, (r.message, app_core.count_entries()))
pack2 = Path(TMP) / "ok.json"
pack2.write_text('{"name":"ok","entries":["庚辛术语"]}', encoding="utf-8")
r = app_core.import_pack(str(pack2), merge=True)
check("pack merge", r.ok and app_core.search_entries("庚辛术语"), r.message)
r = app_core.import_pack(str(pack2), merge=False)
check("pack replace", r.ok and app_core.count_entries() == 1 and app_core.search_entries("庚辛术语"), app_core.count_entries())

print("== 7. 备份恢复 ==")
b = app_core.backup_udl("logic")
check("backup exists", b and os.path.exists(b), b)
c_before = app_core.count_entries()
app_core.add_words(["临时甲乙"])
check("added", app_core.count_entries() == c_before + 1)
r = app_core.restore_backup(b)
check("restore", r.ok and app_core.count_entries() == c_before, app_core.count_entries())

print("== 8. 真机拼音表读回一致性（用本机词库副本）==")
# 不读真机路径；用 votes 已校验的表再写一批常见词
common = ["数据库索引", "查询执行计划", "慢查询优化", "特征工程", "模型蒸馏"]
udl4 = UdlFile()
for w in common:
    udl4.add_entry(w)
p4 = Path(TMP) / "u4.dat"
udl4.write(str(p4))
from pypinyin import pinyin, Style
back4 = UdlFile()
back4.read(str(p4))
ok = 0
for e in back4.entries:
    true = [x[0] for x in pinyin(e.word, style=Style.NORMAL, errors="default")]
    if e.pinyin == true:
        ok += 1
    else:
        print("   py mismatch", e.word, e.pinyin, true)
check("common words pinyin match pypinyin", ok == len(common), f"{ok}/{len(common)}")

print()
if failures:
    print(f"FAILED {len(failures)}: {failures}")
    raise SystemExit(1)
print("ALL LOGIC TESTS PASSED")
shutil.rmtree(TMP, ignore_errors=True)
