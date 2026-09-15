"""端到端回归：用临时 UDL 路径验证竞赛导入链路（不碰真实词库）"""

import os
import sys
import tempfile
import shutil

# 隔离：先设 APPDATA 到临时目录，再导入
TMP = tempfile.mkdtemp(prefix="openime_test_")
os.environ["APPDATA"] = TMP

# 现在再导入（get_default_udl_path 依赖 APPDATA）
import app_core
import competition_data
from udl_core import UdlFile, get_default_udl_path, load_pinyin_table, MAX_WORD_LEN
from poetry_processor import entries_from_line, process_text_to_entries, entries_from_poem

load_pinyin_table()
path = get_default_udl_path()
os.makedirs(os.path.dirname(path), exist_ok=True)
assert path.startswith(TMP), path
print("temp udl:", path)

# 1) 库摘要
print("library:", competition_data.library_summary())
assert len(competition_data.all_poems()) >= 100

# 2) 整句 + 节奏组
ents = entries_from_line("床前明月光")
assert "床前明月光" in ents
assert "床前" in ents and "明月光" in ents
assert all(2 <= len(w) <= MAX_WORD_LEN for w in ents)

# 3) 自由文本
text = "静夜思\n床前明月光，疑是地上霜。\n举头望明月，低头思故乡。\n"
tokens, stats = process_text_to_entries(text)
assert stats["lines"] == 4
assert "举头望明月" in tokens

# 4) 空库导入竞赛诗库
r = app_core.import_competition_library()
print("import:", r.ok, r.message)
print(r.detail)
assert r.ok, r.message
assert app_core.count_entries() > 500

# 5) 幂等：再导入不应新增
count1 = app_core.count_entries()
r2 = app_core.import_competition_library()
assert r2.ok
count2 = app_core.count_entries()
assert count1 == count2, (count1, count2)
print("idempotent ok, count =", count2)

# 6) 自定义文本合并
r3 = app_core.import_text("满江红\n怒发冲冠，凭栏处、潇潇雨歇。")
assert r3.ok, r3.message
assert app_core.count_entries() > count2
assert app_core.search_entries("怒发冲冠")

# 7) 备份/恢复
b = app_core.backup_udl("test")
assert b and os.path.exists(b)
r4 = app_core.restore_backup(b)
assert r4.ok

# 8) 导出
out = os.path.join(TMP, "export.json")
r5 = app_core.export_json(out)
assert r5.ok and os.path.exists(out)
import json
data = json.load(open(out, encoding="utf-8"))
assert data["entry_count"] == app_core.count_entries()
assert data["entry_count"] > 0

# 9) 写回可读
udl = UdlFile()
entries = udl.read(path)
assert len(entries) == data["entry_count"]
sample = [e for e in entries if e.word == "床前明月光"]
assert sample, "床前明月光 未写回词库"
assert sample[0].pinyin and sample[0].pinyin[0] == "chuang", sample[0].pinyin
print("sample entry:", sample[0].word, sample[0].pinyin, sample[0].jianpin_str)

# 10) 删除
before = app_core.count_entries()
r6 = app_core.delete_entries(["床前明月光"])
assert r6.ok
assert app_core.count_entries() == before - 1

print("\nALL TESTS PASSED")
shutil.rmtree(TMP, ignore_errors=True)
