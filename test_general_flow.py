"""通用导入链路回归（临时 APPDATA，不碰真实词库）"""

import os
import tempfile
import shutil
import json

TMP = tempfile.mkdtemp(prefix="openime_general_")
os.environ["APPDATA"] = TMP

import app_core
from document_loader import load_document, load_docx
from term_extractor import extract, looks_like_term
from udl_core import get_default_udl_path, UdlFile, load_pinyin_table, MAX_WORD_LEN

load_pinyin_table()
path = get_default_udl_path()
os.makedirs(os.path.dirname(path), exist_ok=True)
assert path.startswith(TMP)

# 1) 术语抽取
text = """产品经理
需求评审
技术方案
发版窗口、灰度发布
系统架构设计与实现要点
The Quick Brown Fox
COVID-19
"""
r = extract(text, mode="lines", include_latin=True)
terms = r["terms"]
assert "产品经理" in terms
assert "需求评审" in terms
assert "灰度发布" in terms
assert any("COVID" in t or "covid" in t.lower() for t in terms)
assert not any(t == "的" for t in terms)
print("lines extract:", terms[:12], "...", len(terms))

r2 = extract("我们今天要做需求评审，然后技术方案评审，最后发版窗口确认。", mode="auto")
assert "需求评审" in r2["terms"] or any("需求" in t for t in r2["terms"])
print("auto extract sample:", r2["terms"][:15])

# 2) TXT 文件
txt = os.path.join(TMP, "terms.txt")
with open(txt, "w", encoding="utf-8") as f:
    f.write("病历首页\n入院记录\n出院小结\n医嘱单\n")
res = app_core.import_file(txt, mode="lines")
assert res.ok, res.message
assert app_core.search_entries("病历首页")
print("import txt:", res.message)

# 3) DOCX（用 python-docx 或 zipfile 构造）
docx_path = os.path.join(TMP, "t.docx")
try:
    import docx
    d = docx.Document()
    d.add_paragraph("数据库索引")
    d.add_paragraph("查询执行计划")
    d.add_paragraph("慢查询优化")
    d.save(docx_path)
    res = app_core.import_file(docx_path, mode="lines")
    assert res.ok, res.message
    assert app_core.search_entries("数据库索引")
    print("import docx:", res.message)
except ImportError:
    print("skip docx (no python-docx)")

# 4) PDF（若有 pypdf 生成最小 PDF 比较麻烦；测加载接口不炸）
# 手写词条
res = app_core.add_words(["机器学习", "特征工程", "模型蒸馏"])
assert res.ok
assert app_core.count_entries() >= 5

# 5) 幂等
c1 = app_core.count_entries()
res = app_core.add_words(["机器学习", "特征工程"])
assert res.ok and app_core.count_entries() == c1

# 6) 词库包导出/导入
pack = os.path.join(TMP, "pack.json")
res = app_core.export_pack(pack, name="测试包")
assert res.ok and os.path.exists(pack)
data = json.load(open(pack, encoding="utf-8"))
assert data["entry_count"] == c1

# 替换模式
res = app_core.import_pack(pack, merge=False)
assert res.ok
assert app_core.count_entries() == data["entry_count"]

# 7) 删除
b = app_core.count_entries()
res = app_core.delete_entries(["机器学习"])
assert res.ok and app_core.count_entries() == b - 1

# 8) UDL 可读回
entries = UdlFile().read(path)
assert len(entries) == app_core.count_entries()
sample = next(e for e in entries if e.word == "病历首页")
assert sample.pinyin and len(sample.pinyin) == 4
print("sample pinyin:", sample.word, sample.pinyin)

print("\nALL GENERAL TESTS PASSED")
shutil.rmtree(TMP, ignore_errors=True)
