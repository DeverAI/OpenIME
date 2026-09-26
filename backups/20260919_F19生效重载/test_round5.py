"""第五轮检修回归（前端优化 + CLI 确认防护 + 输入法重载）：
预览文案 0 新增分叉（第四轮记而未改项） / CLI 确认 input() 无 stdin 与 EOF 防护 /
reload_ime 重载输入法宿主（全 mock，绝不真杀进程） /
GUI 冒烟：记录区行数上限、busy 联动禁用抽取控件与 watch 光标、对话框 Esc 绑定。
全部临时 APPDATA，子进程探针隔离，不碰真实词库。"""
import os
import shutil
import subprocess
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="openime_round5_")
os.environ["APPDATA"] = TMP
PROJ = os.path.dirname(os.path.abspath(__file__))

import app_core
from udl_core import get_default_udl_path, load_pinyin_table

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
    sub_tmp = tempfile.mkdtemp(prefix="openime_round5_sub_")
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


print("== 1. 预览文案 describe：有新增 / 0 新增分叉（F17，第四轮记而未改） ==")
pv = app_core.ImportPreview(
    to_add=["新词甲", "新词乙"], already=["旧词丙"], rejected=[],
    total_after=10, source_desc="来源文档.txt",
)
text = "\n".join(pv.describe())
check("有新增报新增数", "新增 2 条" in text and "已存在 1 条" in text, text)
check("有新增报导入后总量", "导入后词库约 10 条" in text, text)
check("来源原样在首行", text.startswith("来源文档.txt"), text)

pv2 = app_core.ImportPreview(
    to_add=[], already=["旧词丙", "旧词丁"], rejected=["123"],
    total_after=5, source_desc="来源X",
)
text2 = "\n".join(pv2.describe())
check("0新增明说无词条可写", "已全部在词库中" in text2 and "没有可新增" in text2, text2)
check("0新增不再出现'新增 0 条'歧义", "新增 0 条" not in text2, text2)
check("0新增带过滤计数", "1 条被规则过滤" in text2, text2)

r = app_core.add_words(["明月清风"])
check("seed add ok", r.ok, r.message)
pv3 = app_core.preview_add(["明月清风"], source_desc="再导一次")
check("preview_add 0 新增文案一致", "没有可新增" in "\n".join(pv3.describe()),
      pv3.describe())

print("== 2. CLI 确认输入防护（windowed 无 stdin / EOF 都不许裸崩、不许写库） ==")
probe_head = (
    "import os\n"
    "p = os.path.join(os.environ['APPDATA'], 'terms.txt')\n"
    "open(p, 'w', encoding='utf-8').write('测试新词甲\\n测试新词乙\\n')\n"
)
out = run_probe(
    "import sys\n"
    "sys.stdin = None\n"
    + probe_head +
    "import main, app_core\n"
    "rc = main.run_cli(['OpenIME', 'import', '-f', p])\n"
    "print('RC', rc, 'COUNT', app_core.count_entries())\n"
)
check("stdin=None 确认路径 rc=1 且未写入", "RC 1 COUNT 0" in out, out)

out = run_probe(
    "import sys, os\n"
    "sys.stdin = open(os.devnull)\n"
    + probe_head +
    "import main, app_core\n"
    "rc = main.run_cli(['OpenIME', 'import', '-f', p])\n"
    "print('RC', rc, 'COUNT', app_core.count_entries())\n"
)
check("stdin EOF rc=0 取消且未写入", "RC 0 COUNT 0" in out, out)

out = run_probe(
    probe_head +
    "import main, app_core\n"
    "rc = main.run_cli(['OpenIME', 'import', '-f', p, '--yes'])\n"
    "print('RC', rc, 'COUNT', app_core.count_entries())\n"
)
check("--yes 正常写入 2 条", "RC 0 COUNT 2" in out, out)

print("== 4. reload_ime：重载输入法宿主（全程 mock，绝不真杀进程） ==")
from unittest import mock


class FakeDone:
    def __init__(self, rc, out=b"", err=b""):
        self.returncode, self.stdout, self.stderr = rc, out, err


calls = []


def fake_run_ok(cmd, **kw):
    calls.append(cmd)
    return FakeDone(0)


with mock.patch.object(subprocess, "run", fake_run_ok):
    r = app_core.reload_ime()
check("成功路径 ok 且命令正确",
      r.ok and "已重载" in r.message
      and calls and calls[0][0] == "taskkill" and calls[0][-1] == app_core.IME_HOST_IMAGE,
      (r.message, calls))

with mock.patch.object(subprocess, "run",
                       lambda cmd, **kw: FakeDone(128, out="INFO: No tasks not found.".encode())):
    r = app_core.reload_ime()
check("进程不在视为成功", r.ok and "没在运行" in r.message, r.message)

with mock.patch.object(subprocess, "run",
                       lambda cmd, **kw: FakeDone(1, err="Access denied".encode())):
    r = app_core.reload_ime()
check("真失败如实报错", (not r.ok) and "未能结束" in r.message, r.message)


def boom(cmd, **kw):
    raise OSError("模拟进程调用炸")


with mock.patch.object(subprocess, "run", boom):
    r = app_core.reload_ime()
check("异常被捕获不裸崩", (not r.ok) and "重载输入法失败" in r.message, r.message)

with mock.patch("os.name", "posix"):
    r = app_core.reload_ime()
check("非 Windows 直接拒", (not r.ok) and "非 Windows" in r.message, r.message)

calls.clear()
with mock.patch.object(subprocess, "run", fake_run_ok):
    rc = __import__("main").run_cli(["OpenIME", "reload-ime"])
check("CLI reload-ime 接线", rc == 0 and calls and calls[0][-1] == app_core.IME_HOST_IMAGE,
      (rc, calls))

print("== 5. GUI 冒烟（无显示环境自动跳过） ==")
try:
    import gui
    app = gui.App()
    app.update()
except Exception as e:
    print(f"  SKIP  无法创建窗口（无桌面会话？）：{e}")
    app = None

if app is not None:
    try:
        check("记录区已挂滚动条", str(app.log.cget("yscrollcommand")).strip() != "")
        for i in range(900):
            app.append_log(f"记录行 {i}")
        app.update()
        lines = len(app.log.get("1.0", "end - 1 char").splitlines())
        check("日志行数封顶", lines <= gui.LOG_MAX_LINES, lines)
        content = app.log.get("1.0", "end").rstrip()
        check("封顶后保留最新行", content.endswith("记录行 899"), content[-40:])

        app.set_busy(True, "处理中…")
        check("busy 禁用抽取方式", str(app.mode_cb.cget("state")) == "disabled")
        check("busy 禁用英文术语勾选", str(app.latin_cb.cget("state")) == "disabled")
        check("busy 显示 watch 光标", str(app.cget("cursor")) == "watch", app.cget("cursor"))
        busy_btn = [b for b in app._action_buttons if str(b.cget("state")) == "disabled"]
        check("busy 禁用主窗按钮", len(busy_btn) == len(app._action_buttons),
              f"{len(busy_btn)}/{len(app._action_buttons)}")
        app._run_async(lambda: None, "不应启动")
        check("忙中 _run_async 被拦截", app._busy, "")
        app.set_busy(False)
        check("空闲恢复 readonly", str(app.mode_cb.cget("state")) == "readonly")
        check("空闲光标复原", str(app.cget("cursor")) == "", app.cget("cursor"))
    finally:
        app.destroy()

print()
if failures:
    print(f"FAILED {len(failures)}: {failures}")
    raise SystemExit(1)
print("ALL ROUND5 TESTS PASSED")
shutil.rmtree(TMP, ignore_errors=True)
