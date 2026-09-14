"""词库分页与增强搜索回归（临时 APPDATA）"""
import os
import tempfile
import shutil

TMP = tempfile.mkdtemp(prefix="openime_query_")
os.environ["APPDATA"] = TMP

import app_core

app_core.ensure_ready()
r = app_core.add_words(["明月几时有", "静夜思", "数据库索引", "HBase", "产品原型", "春眠不觉晓"])
assert r.ok, r.message

# 分页
q0 = app_core.query_entries(page=0, page_size=2)
assert q0["total_all"] >= 6
assert q0["pages"] >= 3
assert len(q0["items"]) == 2
q1 = app_core.query_entries(page=1, page_size=2)
assert q1["page"] == 1
assert q1["items"][0].word != q0["items"][0].word

# 越界页钳制
q99 = app_core.query_entries(page=99, page_size=2)
assert q99["page"] == q99["pages"] - 1

# 搜索：中文子串
qh = app_core.query_entries(keyword="明月")
assert any(e.word == "明月几时有" for e in qh["items"]), qh["items"]

# 拼音连写
# 明月 ming yue
qm = app_core.query_entries(keyword="mingyue")
words = [e.word for e in qm["items"]]
assert "明月几时有" in words or any("明月" in w for w in words), words

# 简拼 my
qj = app_core.query_entries(keyword="my")
assert qj["total"] >= 1

# 旧接口
hits = app_core.search_entries("数据库", limit=10)
assert any(e.word == "数据库索引" for e in hits)

print("QUERY/PAGE TESTS PASSED")
print("total", q0["total_all"], "pages", q0["pages"], "dist", q0["stats"]["length_dist"])
shutil.rmtree(TMP, ignore_errors=True)
