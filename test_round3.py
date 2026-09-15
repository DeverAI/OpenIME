"""第三轮检修回归：混合词拼音对齐 / 超长英文拒绝 / 代理对防护 / 大小写搜索 /
JSON 词库包引导 / 空 APPDATA / 备份失败与坏词库时的安全中止。全部临时 APPDATA。"""
import os
import sys
import subprocess
import tempfile
import shutil

TMP = tempfile.mkdtemp(prefix="openime_round3_")
os.environ["APPDATA"] = TMP
PROJ = os.path.dirname(os.path.abspath(__file__))

import app_core
from udl_core import UdlFile, UdlEntry, load_pinyin_table, get_default_udl_path
from term_extractor import extract, looks_like_term
from document_loader import load_document

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


def run_probe(code: str, extra_env: dict = None) -> str:
    """在独立进程、干净 APPDATA 里跑一段探针代码，返回 stdout（异常时返回错误文本）。"""
    sub_tmp = tempfile.mkdtemp(prefix="openime_round3_sub_")
    env = dict(os.environ)
    env["APPDATA"] = sub_tmp
    env["PYTHONPATH"] = PROJ
    env["PYTHONIOENCODING"] = "utf-8"
    if extra_env:
        env.update(extra_env)
    # 脚本路径固定在本次子临时目录，不跟随被覆盖的 APPDATA
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


print("== 1. 混合词拼音逐字对齐（修复：连续英文不再让后面的汉字错位） ==")
u = UdlFile()
for w in ["AI助手", "X光片", "维生素C"]:
    u.add_entry(w)
by_w = {e.word: e.pinyin for e in u.entries}
check("AI助手 aligned", by_w.get("AI助手") == ["", "", "zhu", "shou"], by_w.get("AI助手"))
check("X光片 aligned", by_w.get("X光片") == ["", "guang", "pian"], by_w.get("X光片"))
check("维生素C aligned", by_w.get("维生素C") == ["wei", "sheng", "su", ""], by_w.get("维生素C"))

print("== 2. 超长英文/代理对在预览层就拒绝（不再静默截断/写崩） ==")
check("13-char latin rejected", not looks_like_term("abcdefghijklm"))
check("20-char latin rejected", not looks_like_term("internationalization"))
check("short latin kept", looks_like_term("HBase"))
check("astral rejected", not looks_like_term(chr(0x20BB7) + "吉"))
u2 = UdlFile()
u2.add_entry(chr(0x20BB7) + "吉")
check("astral add_entry skipped", u2.entries == [], [e.word for e in u2.entries])
u3 = UdlFile()
u3.add_entry("正常词条")
u3.entries.append(UdlEntry(word=chr(0x20BB7) + "吉", pinyin=[]))
p3 = os.path.join(TMP, "astral.dat")
try:
    u3.write(p3)
    back3 = UdlFile().read(p3)
    check("astral excluded on write", [e.word for e in back3] == ["正常词条"], [e.word for e in back3])
except Exception as e:
    check("astral excluded on write", False, str(e))

r = extract("Service Level Objective\ninternationalization\n", mode="lines", include_latin=True)
check("lines no >12 latin", all(len(t) <= 12 for t in r["terms"]), r["terms"])

print("== 3. 英文词条大小写不敏感搜索 ==")
r = app_core.add_words(["HBase"])
check("add HBase", r.ok, r.message)
hits = [e.word for e in app_core.query_entries(keyword="base")["items"]]
check("search base -> HBase", "HBase" in hits, hits)
hits2 = [e.word for e in app_core.query_entries(keyword="BASE")["items"]]
check("search BASE -> HBase", "HBase" in hits2, hits2)

print("== 4. .json 按词库包引导，不再当文本抽词 ==")
jp = os.path.join(TMP, "pack.json")
with open(jp, "w", encoding="utf-8") as f:
    f.write('{"name":"t","entries":["甲乙词条"]}')
try:
    load_document(jp)
    check("json raises guidance", False, "no exception")
except RuntimeError as e:
    check("json raises guidance", "词库包" in str(e), str(e))
except Exception as e:
    check("json raises guidance", False, repr(e))
r = app_core.import_files([jp])
check("import_files json guided", (not r.ok) and "词库包" in (r.detail or ""), (r.ok, r.detail))
r = app_core.import_pack(jp, merge=True)
check("import_pack still works", r.ok, r.message)

print("== 5. 空 APPDATA 不写相对路径（子进程验证） ==")
out = run_probe(
    "import os, tempfile\n"
    "import paths\n"
    "paths.app_dir = lambda: tempfile.mkdtemp(prefix='openime_round3_fallback_')\n"
    "d = paths.user_data_dir()\n"
    "print('ABS' if os.path.isabs(d) else 'REL', d)\n",
    extra_env={"APPDATA": ""},
)
check("empty APPDATA absolute", out.startswith("ABS"), out)

print("== 6. 备份失败 → 写入中止、原库不动（子进程验证） ==")
out = run_probe(
    "import os\n"
    "import app_core\n"
    "from udl_core import UdlFile, get_default_udl_path, load_pinyin_table\n"
    "load_pinyin_table()\n"
    "path = get_default_udl_path()\n"
    "os.makedirs(os.path.dirname(path), exist_ok=True)\n"
    "u = UdlFile(); u.add_entry('种子词条'); u.write(path)\n"
    "marker = os.path.join(os.path.dirname(path), 'OpenIME_Backups')\n"
    "open(marker, 'wb').write(b'not a dir')\n"
    "r = app_core.add_words(['新词甲乙'])\n"
    "back = UdlFile().read(path)\n"
    "ok = (not r.ok) and ('备份失败' in r.message) and [e.word for e in back] == ['种子词条']\n"
    "print('OK' if ok else 'BAD', '|', r.message.replace(chr(10), ' '))\n",
)
check("backup failure aborts import", out.startswith("OK"), out)

print("== 7. 当前词库损坏 → 替换/删除安全中止、文件不动（子进程验证） ==")
out = run_probe(
    "import os, json\n"
    "import app_core\n"
    "from udl_core import UdlFile, get_default_udl_path, load_pinyin_table\n"
    "load_pinyin_table()\n"
    "path = get_default_udl_path()\n"
    "os.makedirs(os.path.dirname(path), exist_ok=True)\n"
    "u = UdlFile(); u.add_entry('旧词保留'); u.write(path)\n"
    "corrupt = b'CORRUPTED-NOT-UDL' * 100\n"
    "open(path, 'wb').write(corrupt)\n"
    "pack = os.path.join(os.environ['APPDATA'], 'p.json')\n"
    "json.dump({'name': 'x', 'entries': ['新词甲乙']}, open(pack, 'w', encoding='utf-8'), ensure_ascii=False)\n"
    "r1 = app_core.import_pack(pack, merge=False)\n"
    "r2 = app_core.delete_entries(['旧词保留'])\n"
    "same = open(path, 'rb').read() == corrupt\n"
    "print('OK' if ((not r1.ok) and (not r2.ok) and same) else 'BAD', '|', r1.message, '|', r2.message)\n",
)
check("corrupt udl blocks replace/delete", out.startswith("OK"), out)

print()
if failures:
    print(f"FAILED {len(failures)}: {failures}")
    raise SystemExit(1)
print("ALL ROUND3 TESTS PASSED")
shutil.rmtree(TMP, ignore_errors=True)
