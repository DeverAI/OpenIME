"""第二轮修复回归：原子写入 / 缓存 / 备份保留 / 恢复验货 / 历史撤销 / 改拼音 / 空词条。
全部在临时 APPDATA，不碰真实词库。"""
import os
import tempfile
import shutil

TMP = tempfile.mkdtemp(prefix="openime_fixes_")
os.environ["APPDATA"] = TMP

import app_core
from udl_core import UdlFile, UdlEntry, load_pinyin_table, get_default_udl_path

load_pinyin_table()
path = get_default_udl_path()
os.makedirs(os.path.dirname(path), exist_ok=True)
assert path.startswith(TMP)
failures = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}  {detail}")
        failures.append(name)


print("== 1. 原子写入：无临时文件残留，回读一致 ==")
udl = UdlFile()
udl.add_entry("机器学习")
udl.add_entry("特征工程")
udl.write(path, preserve_header=True)
leftovers = [f for f in os.listdir(os.path.dirname(path)) if ".tmp_openime" in f]
check("no tmp leftovers", not leftovers, leftovers)
back = UdlFile().read(path)
check("words roundtrip", [e.word for e in back] == ["机器学习", "特征工程"], [e.word for e in back])

print("== 2. load_entries 缓存：未变更同对象，写入后失效 ==")
e1 = app_core.load_entries()
e2 = app_core.load_entries()
check("cache same object", e1 is e2)
r = app_core.add_words(["模型蒸馏"])
check("add ok", r.ok, r.message)
e3 = app_core.load_entries()
check("cache invalidated", e3 is not e1 and any(x.word == "模型蒸馏" for x in e3))

print("== 3. 备份保留策略：只留最近 30 份 ==")
for i in range(35):
    app_core.add_words([f"测试词{i:02d}"])
n_backups = len(app_core.list_backups())
check("backups pruned", n_backups <= 30, n_backups)

print("== 4. 恢复验货：坏备份拒绝覆盖 ==")
bad = os.path.join(TMP, "bad.dat")
with open(bad, "wb") as f:
    f.write(b"not a udl file" * 10)
r = app_core.restore_backup(bad)
check("bad backup rejected", (not r.ok) and "无效" in r.message, r.message)

print("== 5. 历史 + 撤销最近一次导入 ==")
n_imports_before = len([x for x in app_core.list_history() if x.get("action") == "import"])
check("history has import records", n_imports_before >= 1, n_imports_before)
words5 = ["撤销测试甲", "撤销测试乙", "撤销测试丙"]
before = app_core.count_entries()
r = app_core.add_words(words5)
check("batch add ok", r.ok and app_core.count_entries() == before + 3, (r.message, app_core.count_entries()))
r = app_core.undo_last_import()
check("undo ok", r.ok, r.message)
check("undo restored count", app_core.count_entries() == before, app_core.count_entries())
check("undo removed words", not any(app_core.search_entries(w) for w in words5))
n_imports_after = len([x for x in app_core.list_history() if x.get("action") == "import"])
check("undo consumed manifest", n_imports_after == n_imports_before, (n_imports_before, n_imports_after))

print("== 6. 改拼音：写入生效 + 简拼重算 ==")
app_core.add_words(["重庆"])
r = app_core.update_entry_pinyin("重庆", "zhong qing")
check("edit pinyin ok", r.ok, r.message)
ents = UdlFile().read(path)
e = next((x for x in ents if x.word == "重庆"), None)
check("pinyin updated", e is not None and e.pinyin == ["zhong", "qing"], e and e.pinyin)
check("jianpin recomputed", e is not None and e.jianpin_str.strip() == "zq", e and e.jianpin_str)
r = app_core.update_entry_pinyin("不存在的词库词条", "a b")
check("missing word rejected", not r.ok, r.message)

print("== 7. 空词条写入不破坏文件 ==")
u = UdlFile()
u.read(path)
u.entries.append(UdlEntry(word=""))
u.write(path, preserve_header=True)
back2 = UdlFile().read(path)
check("empty entry dropped", not any(x.word == "" for x in back2))
check("count consistent", app_core.count_entries() == len(back2), (app_core.count_entries(), len(back2)))

print()
if failures:
    print(f"FAILED {len(failures)}: {failures}")
    raise SystemExit(1)
print("ALL FIXES TESTS PASSED")
shutil.rmtree(TMP, ignore_errors=True)
