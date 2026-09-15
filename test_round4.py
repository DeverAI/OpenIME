"""第四轮检修回归：重复音节主用槽位 / 词库包拼音往返 / 替换备份保护 /
纯数字拒收 / 列表记号剥离 / 同秒备份撞名 / 改拼音音节校验 / 竞赛库 CLI 入口。
全部临时 APPDATA，子进程探针隔离，不碰真实词库。"""
import json
import os
import struct
import subprocess
import sys
import tempfile
import shutil
from unittest import mock
import datetime as _dt

TMP = tempfile.mkdtemp(prefix="openime_round4_")
os.environ["APPDATA"] = TMP
PROJ = os.path.dirname(os.path.abspath(__file__))

import app_core
import main
from udl_core import (
    UdlFile, load_pinyin_table, get_default_udl_path,
    get_index_by_pinyin, UDL_HEADER_SIZE, UDL_ENTRY_SIZE,
)
from term_extractor import extract, looks_like_term

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


def run_probe(code: str) -> str:
    sub_tmp = tempfile.mkdtemp(prefix="openime_round4_sub_")
    env = dict(os.environ)
    env["APPDATA"] = sub_tmp
    env["PYTHONPATH"] = PROJ
    env["PYTHONIOENCODING"] = "utf-8"
    script = os.path.join(sub_tmp, "probe.py")
    with open(script, "w", encoding="utf-8") as f:
        f.write(code)
    r = subprocess.run(
        [sys.executable, script], capture_output=True,
        encoding="utf-8", errors="replace",
        env=env, cwd=tempfile.gettempdir(), timeout=120,
    )
    if r.returncode != 0:
        return f"PROBE-ERROR: {(r.stderr or '')[-400:]}"
    return r.stdout


print("== 1. 重复音节主用槽位（真机 8697 条实测：ai→1 de→61 ge→99 fu→93） ==")
check("de -> 61", get_index_by_pinyin("de") == 61, get_index_by_pinyin("de"))
check("ai -> 1", get_index_by_pinyin("ai") == 1, get_index_by_pinyin("ai"))
check("ge -> 99", get_index_by_pinyin("ge") == 99, get_index_by_pinyin("ge"))
check("fu -> 93", get_index_by_pinyin("fu") == 93, get_index_by_pinyin("fu"))
u = UdlFile()
u.add_entry("的确良")
u.add_entry("个别人")
p1 = os.path.join(TMP, "dup.dat")
u.write(p1)
data = open(p1, "rb").read()
first = UDL_HEADER_SIZE
wl = data[first + 10]
idx0 = struct.unpack_from("<H", data, first + 12 + wl * 2)[0]
check("的字写主用槽位 61", idx0 == 61, idx0)
back = UdlFile().read(p1)
check("de 词回读音节不变", back[0].pinyin[0] == "de" and back[1].pinyin[0] == "ge",
      [(e.word, e.pinyin) for e in back])

print("== 2. 词库包拼音往返（导出→导入不再丢改音） ==")
r = app_core.add_words(["重庆"])
check("add 重庆", r.ok, r.message)
r = app_core.update_entry_pinyin("重庆", "chong qing")
check("改音 chong qing", r.ok, r.message)
pack = os.path.join(TMP, "roundtrip.json")
r = app_core.export_pack(pack)
check("export ok", r.ok, r.message)
app_core.delete_entries(["重庆"])
r = app_core.import_pack(pack, merge=True)
check("re-import ok", r.ok, r.message)
back = {e.word: e.pinyin for e in app_core.load_entries()}
check("pinyin preserved", back.get("重庆") == ["chong", "qing"], back.get("重庆"))

# 直接构造带拼音的包：新增 + 更新已有词拼音（包里拼音与现库不同才触发"更新"）
pack2 = os.path.join(TMP, "withpy.json")
with open(pack2, "w", encoding="utf-8") as f:
    json.dump({
        "name": "带拼音包",
        "entries": [
            {"word": "重庆", "pinyin": ["zhong", "qing"]},
            {"word": "长安街", "pinyin": ["chang", "an", "jie"]},
        ],
    }, f, ensure_ascii=False)
r = app_core.import_pack(pack2, merge=True)
check("pack-with-pinyin merge ok", r.ok, r.message)
check("pack-with-pinyin updates", r.data.get("updated") == 1 and r.data.get("added") == 1,
      r.data)
back = {e.word: e.pinyin for e in app_core.load_entries()}
check("长安街 pinyin", back.get("长安街") == ["chang", "an", "jie"], back.get("长安街"))

# 非法拼音（带声调/数字）宁可重新猜，不写坏
pack3 = os.path.join(TMP, "badpy.json")
with open(pack3, "w", encoding="utf-8") as f:
    json.dump({"name": "bad", "entries": [{"word": "天津", "pinyin": ["tiān", "jin1"]}]},
              f, ensure_ascii=False)
r = app_core.import_pack(pack3, merge=True)
check("bad pinyin falls back", r.ok, r.message)
back = {e.word: e.pinyin for e in app_core.load_entries()}
check("天津 re-guessed", back.get("天津") == ["tian", "jin"], back.get("天津"))

# 替换分支也保拼音（此时重庆已被 pack2 更新为 zhong qing，替换后应保持包里的值）
r = app_core.import_pack(pack2, merge=False)
check("pack-with-pinyin replace ok", r.ok, r.message)
ents = UdlFile().read(path)
by_w = {e.word: e.pinyin for e in ents}
check("replace keeps pinyin",
      by_w.get("重庆") == ["zhong", "qing"] and by_w.get("长安街") == ["chang", "an", "jie"],
      by_w)

print("== 3. 替换/恢复的备份失败保护（子进程探针） ==")
out = run_probe(
    "import os, json\n"
    "import app_core\n"
    "from udl_core import UdlFile, get_default_udl_path, load_pinyin_table\n"
    "load_pinyin_table()\n"
    "path = get_default_udl_path()\n"
    "os.makedirs(os.path.dirname(path), exist_ok=True)\n"
    "u = UdlFile(); u.add_entry('旧词保留'); u.write(path)\n"
    "bdir = os.path.join(os.path.dirname(path), 'OpenIME_Backups')\n"
    "open(bdir, 'w').write('not a dir')\n"
    "pack = os.path.join(os.environ['APPDATA'], 'p.json')\n"
    "json.dump({'name':'x','entries':['新词甲乙']}, open(pack,'w',encoding='utf-8'), ensure_ascii=False)\n"
    "r1 = app_core.import_pack(pack, merge=False)\n"
    "raw_before = open(path,'rb').read()\n"
    "r2 = app_core.restore_backup(path)\n"
    "same = open(path,'rb').read() == raw_before\n"
    "ok = (not r1.ok) and ('备份失败' in r1.message) and (not r2.ok) and same\n"
    "print('OK' if ok else 'BAD', '|', r1.message[:40], '|', r2.message[:40])\n",
)
check("replace/restore backup failure aborts", out.startswith("OK"), out)

# 恢复走临时文件原子替换，无残留
b = app_core.backup_udl("r4")
r = app_core.restore_backup(b)
leftovers = [f for f in os.listdir(os.path.dirname(path)) if ".restore_tmp" in f]
check("restore ok, no tmp leftovers", r.ok and not leftovers, (r.message, leftovers))

print("== 4. 纯数字/纯标点拒收（字母或汉字至少其一） ==")
check("12345 rejected", not looks_like_term("12345"))
check("2026 rejected", not looks_like_term("2026"))
check("3.5 rejected", not looks_like_term("3.5"))
check("1. rejected", not looks_like_term("1."))
check("5G kept", looks_like_term("5G"))
check("HBase kept", looks_like_term("HBase"))
check("pH值 kept", looks_like_term("pH值"))
r = app_core.add_words(["12345"])
check("add pure digits rejected", (not r.ok) and app_core.count_entries() == 2,
      (r.message, app_core.count_entries()))

print("== 5. 列表记号剥离（auto / sentences 与 lines 一致） ==")
r = extract("1. 化学变化\n2. 物理变化\n* 质量守恒\n", mode="auto")
terms = r["terms"]
check("auto no dotted terms", all("." not in t for t in terms), terms)
check("auto keeps core terms", all(t in terms for t in ("化学变化", "物理变化", "质量守恒")), terms)
r2 = extract("他说，1. 化学变化很重要，所以要注意。", mode="sentences")
check("sentences no '1.' fragment", all(t != "1." for t in r2["terms"]), r2["terms"])
check("sentences keeps term", "化学变化很重要" in r2["terms"], r2["terms"])

print("== 6. 同秒同标签备份不互相覆盖 ==")
class FixedDT:
    @staticmethod
    def now():
        return _dt.datetime(2026, 9, 15, 12, 0, 0)
with mock.patch.object(app_core, "datetime", FixedDT):
    a = app_core.backup_udl("same")
    b2 = app_core.backup_udl("same")
check("distinct backup files", a != b2 and os.path.exists(a) and os.path.exists(b2),
      (a, b2))

print("== 7. 改拼音音节校验（带声调/带数字明确拒绝） ==")
py_before = {e.word: e.pinyin for e in app_core.load_entries()}.get("重庆")
r = app_core.update_entry_pinyin("重庆", "zhòng qing4")
check("tone input rejected", (not r.ok) and "拼音表" in r.message, r.message)
py_after = {e.word: e.pinyin for e in app_core.load_entries()}.get("重庆")
check("pinyin untouched on reject", py_after == py_before, (py_before, py_after))
r = app_core.update_entry_pinyin("重庆", "chong qing")
back2 = {e.word: e.pinyin for e in app_core.load_entries()}
check("valid still works", r.ok and back2.get("重庆") == ["chong", "qing"],
      (r.message, back2.get("重庆")))

print("== 8. 竞赛库 CLI/GUI 后端入口 ==")
before = app_core.count_entries()
rc = main.run_cli(["OpenIME", "import-comp"])
check("import-comp rc=0", rc == 0, rc)
after = app_core.count_entries()
check("import-comp added >500", after - before > 500, (before, after))
rc2 = main.run_cli(["OpenIME", "import-comp"])
check("import-comp idempotent", rc2 == 0 and app_core.count_entries() == after,
      app_core.count_entries())

print("== 9. windowed 无 stdin 不崩（子进程探针） ==")
out = run_probe(
    "import sys\n"
    "sys.stdin = None\n"
    "import main\n"
    "rc = main.run_cli(['OpenIME', 'import'])\n"
    "print('RC', rc)\n",
)
check("no stdin returns rc=1", "RC 1" in out, out)

print()
if failures:
    print(f"FAILED {len(failures)}: {failures}")
    raise SystemExit(1)
print("ALL ROUND4 TESTS PASSED")
shutil.rmtree(TMP, ignore_errors=True)
