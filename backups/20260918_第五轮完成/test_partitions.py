"""分区功能回归：手动分区 / 自动批次分区 / 合并去重 / only_words 分页过滤 /
分区清除（删词+删记录+备份）/ 跨机暴力移植（复制 %APPDATA% 后原机器记录独立成区可清）。
全部临时 APPDATA，不碰真实词库。"""
import json
import os
import platform
import shutil
import tempfile

TMP = tempfile.mkdtemp(prefix="openime_part_")
os.environ["APPDATA"] = TMP
MACHINE = platform.node()

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


print("== 1. 手动分区：创建 / 合并 / 校验 ==")
phys = ["牛顿定律", "焦耳定律", "欧姆定律", "自由落体"]
chem = ["化学平衡", "光的折射"]
r = app_core.add_words(phys + chem)
check("seed 6 条", r.ok and app_core.count_entries() == 6, (r.message, app_core.count_entries()))

r = app_core.create_partition("物理区", phys[:3])
check("建分区", r.ok and r.data.get("total") == 3 and r.data.get("name") == "物理区", r.message)
r2 = app_core.create_partition("物理区", [phys[3], chem[0], phys[0]])  # 含重复
check("重名合并不重复", r2.ok and r2.data.get("total") == 5 and r2.data.get("added") == 2,
      (r2.message, r2.data))
cfg = os.path.join(TMP, "OpenIME", "partitions.json")
check("分区落在自带 config", os.path.exists(cfg))
data = json.load(open(cfg, encoding="utf-8"))
check("config 记录机器名", data["partitions"]["物理区"]["machine"] == MACHINE,
      data["partitions"]["物理区"].get("machine"))
parts = {p["name"]: p for p in app_core.list_partitions()}
check("手动分区列出", parts.get("物理区", {}).get("words") == phys[:3] + [phys[3], chem[0]],
      parts.get("物理区", {}).get("words"))
check("导入历史自动成区", any(p["kind"] == "auto" and p["machine"] == MACHINE
                             for p in app_core.list_partitions()))
check("建分区不碰词库", app_core.count_entries() == 6)
check("保留前缀拒名", not app_core.create_partition("[自动] 冒充", ["牛顿定律"]).ok)
check("空名拒", not app_core.create_partition("  ", ["牛顿定律"]).ok)
check("空词拒", not app_core.create_partition("空区", ["", "  "]).ok)

print("== 2. only_words 过滤 + 分页 + 关键字组合 ==")
r = app_core.query_entries(only_words=phys[:3], page_size=2)
check("过滤 total", r["total"] == 3 and r["pages"] == 2, (r["total"], r["pages"]))
check("第一页 2 条", len(r["items"]) == 2)
check("total_all 仍为全库", r["total_all"] == 6)
r = app_core.query_entries(keyword="定律", only_words=parts["物理区"]["words"])
check("关键字+分区组合", {e.word for e in r["items"]} == {"牛顿定律", "焦耳定律", "欧姆定律"},
      [e.word for e in r["items"]])

print("== 3. 分区清除 ==")
bk_before = len(app_core.list_backups())
r = app_core.remove_partition("物理区", delete_words=True)
check("清除成功且删 5 条", r.ok and r.data.get("deleted") == 5, (r.message, getattr(r, "data", None)))
check("词库少 5 条", app_core.count_entries() == 1, app_core.count_entries())
check("剩的是没进区的词", [e.word for e in app_core.load_entries()] == ["光的折射"],
      [e.word for e in app_core.load_entries()])
check("分区记录消失", all(p["name"] != "物理区" for p in app_core.list_partitions()))
check("清除前有备份", len(app_core.list_backups()) > bk_before)

app_core.create_partition("混合区", ["光的折射", "失踪词条"])
r = app_core.remove_partition("混合区", delete_words=True)
check("缺词分区清除报 missing", r.ok and r.data.get("deleted") == 1 and r.data.get("missing") == 1,
      (r.message, r.data))

app_core.add_words(["临时记忆"])
app_core.create_partition("只忘记", ["临时记忆"])
r = app_core.remove_partition("只忘记", delete_words=False)
check("不删词模式词仍在本体库",
      r.ok and "临时记忆" in {e.word for e in app_core.load_entries()})
r = app_core.remove_partition("不存在的区")
check("清除不存在的分区报错", not r.ok)

print("== 4. manifest 带 machine（跨机识别的前提） ==")
r = app_core.apply_tokens(["巴甫洛夫", "细胞壁"], source_desc="词库包「生物」")
check("导入 ok", r.ok)
files = app_core._history_files()
rec = json.load(open(files[0], encoding="utf-8"))
check("manifest 有 machine", rec.get("machine") == MACHINE, rec.get("machine"))
names = [p["name"] for p in app_core.list_partitions() if p["kind"] == "auto"]
check("自动区名含来源", any("词库包「生物」" in n for n in names), names)

print("== 5. 暴力移植：复制配置目录到新机器后原机器记录独立成区、可单独清除 ==")
app_core.add_words(["道尔顿分压"])  # 归"旧机器"自动导入的一批，稍后模拟被拷到新机器
NEW = tempfile.mkdtemp(prefix="openime_part_new_")
shutil.copytree(os.path.join(TMP, "OpenIME"), os.path.join(NEW, "OpenIME"))
os.makedirs(os.path.join(NEW, "Microsoft", "InputMethod", "Chs"), exist_ok=True)
shutil.copy2(path, os.path.join(NEW, "Microsoft", "InputMethod", "Chs", "ChsPinyinUDL.dat"))
# 模拟旧版本机器拷来的老记录：无 machine 字段
old_rec = os.path.join(NEW, "OpenIME", "history", "import_20260101_000000_legacy.json")
json.dump({"time": "2026-01-01T00:00:00", "action": "import", "source": "老机器导入",
           "added": ["道尔顿分压"], "removed": [], "total": 3},
          open(old_rec, "w", encoding="utf-8"), ensure_ascii=False)
os.environ["APPDATA"] = NEW
import app_core as _probe  # 同模块对象，路径按 env 动态解析
parts_new = _probe.list_partitions()
legacy = [p for p in parts_new if p["kind"] == "auto" and p["machine"] == "旧记录"]
check("无 machine 老记录归入 旧记录 独立区", len(legacy) == 1 and legacy[0]["words"] == ["道尔顿分压"],
      [(p["machine"], p["name"]) for p in parts_new if p["kind"] == "auto"])
mine = [p for p in parts_new if p["kind"] == "auto" and p["machine"] == MACHINE]
check("新机器本机导入自成另一批区", len(mine) >= 1, [p["name"] for p in mine])
r = _probe.remove_partition(legacy[0]["name"], delete_words=True)
check("单独清掉旧机器区", r.ok and r.data.get("deleted") == 1, (r.message, r.data))
check("新机器其它词不受影响",
      {e.word for e in _probe.load_entries()} == {"临时记忆", "巴甫洛夫", "细胞壁"},
      [e.word for e in _probe.load_entries()])
orig_words = {x.word for x in app_core.UdlFile().read(path)}
check("旧机器原 env 词库未被动", "道尔顿分压" in orig_words, orig_words)
os.environ["APPDATA"] = TMP

print("== 6. 审查修复契约：保留名 / 坏文件拒写 / 记录删除失败如实报 / 并发保存 ==")
r = app_core.create_partition("全部词条", ["临时记忆"])
check("保留名「全部词条」拒", (not r.ok) and "保留名" in r.message, r.message)

cfg_path = os.path.join(TMP, "OpenIME", "partitions.json")
good_cfg = open(cfg_path, encoding="utf-8").read()
with open(cfg_path, "w", encoding="utf-8") as f:
    f.write("{ broken json !!!")
r = app_core.create_partition("覆写区", ["临时记忆"])
check("坏 partitions.json 拒写不覆掉", (not r.ok) and "拒绝" in r.message, r.message)
check("坏文件原样保留", open(cfg_path, encoding="utf-8").read() == "{ broken json !!!")
with open(cfg_path, "w", encoding="utf-8") as f:
    f.write(good_cfg)
r = app_core.remove_partition("覆写区")
check("坏文件期间确实没建成区", (not r.ok) and "找不到" in r.message, r.message)

r = app_core.apply_tokens(["并发测试词甲", "并发测试词乙"], source_desc="并发探针")
check("并发种子导入 ok", r.ok)
import threading
barrier = threading.Barrier(2)
results = []


def _worker(nm):
    barrier.wait()
    results.append(app_core.create_partition(nm, ["并发测试词甲"]))


ts = [threading.Thread(target=_worker, args=(f"并发区{i}",)) for i in (1, 2)]
[t.start() for t in ts]
[t.join() for t in ts]
check("双线程建区都成功", all(r0.ok for r0 in results), results)
names_now = {p["name"] for p in app_core.list_partitions()}
check("两区都在且文件完好", {"并发区1", "并发区2"} <= names_now
      and isinstance(json.load(open(cfg_path, encoding="utf-8"))["partitions"], dict))
for nm in ("并发区1", "并发区2"):
    app_core.remove_partition(nm, delete_words=False)

# 自动批次 manifest 删不掉（Windows 只读文件 os.remove 抛 PermissionError）必须如实报
import stat
mf = app_core._history_files()[0]
auto_part = next(p for p in app_core.list_partitions()
                 if p["kind"] == "auto" and p.get("_file") == mf)
os.chmod(mf, stat.S_IREAD)
r = app_core.remove_partition(auto_part["name"], delete_words=True)
os.chmod(mf, stat.S_IWRITE)
check("manifest 删失败仍报词删结果", r.ok and r.data.get("deleted") >= 1
      and r.data.get("record_error") and "未能移除" in r.message, (r.message, r.data))
check("幽灵分区如实仍在列表", any(p["name"] == auto_part["name"] for p in app_core.list_partitions()))
os.remove(mf)  # 清场，避免影响后续

print()
if failures:
    print(f"FAILED {len(failures)}: {failures}")
    raise SystemExit(1)
print("ALL PARTITION TESTS PASSED")
shutil.rmtree(TMP, ignore_errors=True)
shutil.rmtree(NEW, ignore_errors=True)
