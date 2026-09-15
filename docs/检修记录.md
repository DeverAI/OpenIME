# OpenIME 深度检修记录

日期：2026-09-12  
范围：全量源码审阅 + 真机 UDL 对照 + 预期逻辑回归

## 必须知道的结论

### 1. 真机文件头不能清零（严重）
真机 `ChsPinyinUDL.dat` 头 0x2400 中，**0x470 起有大量索引/统计数据**。
旧版 `write()` 每次新建全零头再写词条，会抹掉这些区域（约 299 字节差异）。

**修复**：`UdlFile.read()` 保存 `raw_header`；`write(..., preserve_header=True)`
默认复制原头，只更新 count@0xC 与 timestamp@0x14。合并/删除/替换均走此路径。

### 2. 拼音索引表必须与真机对齐
`pinyin_table.json` 已用真机 8242 条投票重建；idx0=`a`。对真机校验约 98.6%
（剩余为多音字默认读音差异）。禁止改回未校准表。

### 3. 简拼写入
默认 `jianpin=b'\x00\x00\x00'` 必须重新计算，不能当成已写好。

### 4. 空拼音哨兵
空拼音写 `0xFFFF`，不能写 0（0=音节 a）。

## 本轮修复清单

| 级别 | 问题 | 处理 |
|------|------|------|
| 严重 | 写入清空真机头 0x470+ | preserve_header |
| 严重 | 读文件 count 越界 | 按文件长度截断 |
| 高 | APPDATA 为空写到相对路径 | 明确报错 |
| 高 | GUI 忙时按钮可连点 | busy 时 disable |
| 高 | 并发写无锁 | `_WRITE_LOCK` |
| 中 | 替换模式可空包清库 | 已拦；替换也保留头 |
| 中 | 不能按拼音搜 | 子串 + 拼音/简拼回退 |
| 中 | 导入后无自测提示 | detail 增加试一试 |
| 低 | 诗题超长仍 push | 标题长度过滤 |

## 功能线索（初三场景）

已补样例词库包（可直接「导入文档」）：
- `词库包_初三数学.txt`
- `词库包_初三物理.txt`
- `词库包_初三化学.txt`
- `词库包_古诗文比赛.txt`

仍可增强（未做，避免一次改太大）：
- 导入历史时间线（精确撤销某一次导入）
- 学科词库包向导（点选学科一键装）
- 古诗文「篇目→全文」联想练习模式
- 与云端词库包同步

## 验证

```bash
python test_logic_expected.py
python test_general_flow.py
python test_header_preserve.py
```

真机只做过「写入→校验→整文件回滚」实验（SHA256 一致）。
**未**在保留修改的情况下让输入法热加载后人工打字验证——需要你本机点一下。

---

# 第二轮检修（2026-09-14）：原子写 / 历史 / 撤销 / 改拼音

## 修复清单

| 级别 | 问题 | 处理 |
|------|------|------|
| 严重 | exe 排除 fitz 后 `load_pdf` 的 `warn` 未定义 → 打包版导 PDF 必报「无法解析 PDF：name 'warn' is not defined」 | 函数开头初始化 `warn=""` |
| 严重 | `UdlFile.write` 直接覆盖目标文件，写一半崩溃 = 半个坏词库 | 同目录临时文件 + 回读校验（条数+逐词，超长词按截断后对比）+ `os.replace` 原子替换；空词条不落盘不计数 |
| 高 | `restore_backup` 不验货直接覆盖当前词库 | 恢复前先解析备份；解析失败或 0 条拒绝恢复 |
| 高 | 备份无限增长 | 每次备份后只保留最近 30 份（`_prune_backups`） |
| 中 | GUI 删除后固定 `after(300/500)` 刷新与写入竞速，可能显示旧数据 | `_run_async` 增加 `on_done` 回调，写入真正完成后才刷新 |
| 中 | CSV 导出手拼逗号，词条含逗号会串列 | 改用 `csv` 模块 + `utf-8-sig`（Excel 直开） |
| 中 | status/preview/query 反复全量解析 UDL | `load_entries` 按 (mtime_ns, size) 缓存；所有写路径成功后 `_cache_invalidate()` |
| 低 | 死代码 | 删 `term_frequency`、`_STOP_SINGLE`、`UdlEntry.frequency/word_length/pinyin_indices`、gui 未用 import |
| 旧账 | `test_competition_flow` 调 `app_core.import_competition_library` 但函数不存在，整条链路一直跑不过 | app_core 补该函数（竞赛库 → `entries_from_poem` → `apply_tokens` 同一安全链路，幂等） |

## 新功能

- **导入历史**：每次写入成功记 manifest 到 `%APPDATA%\OpenIME\history\`（time/action/source/added/removed/total/backup，保留最近 200 条；记录失败不影响主流程）
- **撤销上次导入**：`undo_last_import()` 按最近 manifest 精确删那批新增词；GUI「撤销上次导入」按钮 + CLI `undo` / `history`
- **改拼音**：`update_entry_pinyin(word, "yin jie")` 人工修多音字，缺省位落哨兵 `0xFFFF`，简拼按新拼音重算；浏览词库「改拼音」按钮（单选一条，回车保存）
- **内置词库包**：主界面「内置词库包」一键导入数学/物理/化学/古诗文（mode=lines）；`build_exe.py` 已把 4 个包打进 exe，`--add-data` 分隔符改用 `os.pathsep`（Windows 是 `;`）

## 新增注意事项

- `load_entries()` 返回**共享缓存列表**，调用方不得修改；要改请自建 `UdlFile().read()`
- 两个旧 spec（`OpenIME.spec` / `古诗文输入助手.spec`）未删（构建会重新生成 spec，属产物），构建一律走 `python build_exe.py`
- 新回归测试 `test_fixes.py`（7 节，全部临时 APPDATA）

## 验证

```bash
python test_header_preserve.py
python test_logic_expected.py
python test_general_flow.py
python test_query_page.py
python test_competition_flow.py
python test_fixes.py
```

六套全过（2026-09-14）。

---

# 第三轮检修（2026-09-14 深夜）：混英词拼音错位 / 静默截断 / 代理对 / JSON 词库包引导 / 历史界面

## 修复清单

| 级别 | 问题 | 处理 |
|------|------|------|
| 严重 | `_guess_pinyin` 按 pypinyin「段」对齐：连续英文并成一段，后面的汉字全部错位。实测 `AI助手` 的「助」拿到 `shou`（手的音）、「手」没音 | 改为**逐字取音**；`AI助手`→`['','','zhu','shou']`，`X光片`、`维生素C` 均对齐（test_round3 §1） |
| 严重 | `looks_like_term` 纯英文放行到 24 字符，而 UDL 单条上限 12 字 → 预览说会导入、写入时被**静默截断**，预览与实际不符 | 纯英文上限收至 12 字；超长在预览层即拒；`extract_from_lines` 拼接形态同步收紧（test_round3 §2） |
| 严重 | 基本平面外字符（如 `𠮷`，UTF-16 代理对）能过预览与 `add_entry`；写入时拼音区按「字符数」偏移，覆盖代理对低半区 → 回读校验失败 → **整个导入失败** | 三道防线：`looks_like_term` 拒收 / `add_entry`、`from_dict_list` 跳过 / `write()` payload 过滤（test_round3 §2） |
| 高 | `apply_tokens` / `delete_entries` / `update_entry_pinyin` 里备份或读库抛异常会带裸 traceback 冒给用户 | 统一包住：**备份失败 → 明确报错并中止写入（写库红线）**；读库失败 → 明确报错并中止（test_round3 §6） |
| 高 | `import_pack` 替换模式下，当前词库解析失败被 `except: pass` 吞掉，接着用最小头写入 → 抹掉 0x470+ 索引区 | 解析失败直接中止替换（test_round3 §7） |
| 严重 | **`undo_last_import` 会删错词**（存量 bug，本轮实测触发）：同秒冲突后缀 `_2.._99` 按文件名排序时 `import_9 > import_10`，同一秒内第 10 条同类型记录会被第 9 条压住 → "取最近导入"取错 manifest，实测删掉了「测试词27」而不是刚导入的「撤销测试甲乙丙」 | 历史记录统一改为**按文件 mtime 排序**（`_history_files()`，文件名仅作并列决胜）；`list_history` 与 `_record_history` 的裁剪共用；test_fixes §5 从 flaky 变稳定 |
| 中 | 英文词条搜索大小写敏感：搜 `base` 找不到 `HBase` | `_match_entry` 增加大小写不敏感子串匹配（test_round3 §3） |
| 中 | 「选择文档…」选 .json 词库包会被当文本抽词出一堆垃圾 | GUI：.json 自动路由到「导入词库包」流程（与文档混选时先文档后词库包串行）；`load_document('.json')` 报错并指引；CLI `import -f x.json` 会得到明确警告（test_round3 §4） |
| 中 | `paths.user_data_dir` 在 APPDATA=**空字符串**时回退成相对路径 `OpenIME/`（写进当前工作目录） | `os.environ.get("APPDATA") or app_dir()`；子进程实测返回绝对路径（test_round3 §5） |
| 低 | PyMuPDF 分支异常时 `doc` 不关闭（句柄泄漏） | `try/finally: doc.close()` |
| 低 | 扫描版 PDF 抽不出任何文本时无提示 | 文本为空 → warning「可能是扫描版 PDF，需要先 OCR」 |
| 低 | `test_competition_flow` §9 断言 `... or sample[0].pinyin` 恒真 | 收紧为 `pinyin[0] == "chuang"` |
| 测试设施 | `run_probe` 子进程：中文输出按 GBK 解码崩（stdout=None）；脚本路径跟随被覆盖的空 APPDATA 落进 CWD | `subprocess.run(encoding="utf-8", errors="replace")`；脚本路径固定在子临时目录 |

> 关于触发条件的说明：历史排序 bug 需要「同一秒内 ≥10 次同类型写入」才会显形（例如批量脚本一秒导入几十次后立即 undo）。人工 GUI 操作几乎不会碰到，但 CLI/脚本场景是真实风险。此前两轮测试未触发纯属侥幸。

## 新功能 / 功能线索评估

- **GUI「历史…」（新）**：`list_history()` 后端早已存在、CLI 有 `history`、GUI 没有入口 → 补了历史查看对话框（时间 / 操作 / 内容 / 来源 + 刷新），管理区新增第二行放「历史…」。
- **`ai_refine.py`（未接线半成品）**：全项目无任何调用（检修确认）。云 API 部分（OpenAI 兼容）与本项目「不依赖云 API」规范冲突；`local_refine` 的「短词是长词子串就删」对输入法词库是有损的（短词+长词常常都要）。**决定：不接线**，模块 docstring 已标注实验性/未接入与原因。将来若要接，走「仅本地规则 + GUI 可选开关」。
- `poetry_processor.split_mixed_text` 无调用者（旧接口，暂保留）；`_normalize_list` 死变量已删。
- 上一轮遗留「仍可增强」（历史时间线/学科向导/篇目联想/云同步）维持不动，本轮只补了历史查看。
- **AGENT.txt**：旧的通用工作流提示词（要求 Design.md/dev_log 等另一套文档体系，与本项目 AGENTS.md 规范冲突）。未删除（等用户决定）；本项目文档仍以 `docs/检修记录.md` + README 为准。
- 根目录杂项（`pinyin_output.txt`、`*_output.log`、`build.log`、`exe_test.log`、`test_import.txt`、根目录 `OpenIME.exe`、旧 spec、`build/`、`dist/`）多为产物/日志，未动，是否清理由用户决定。

## 备份

- 修改前快照（逐份校验：CRLF 归一后与原文件全等）：`backups/20260914_第三轮检修前/`，共 11 份
  （udl_core / app_core / term_extractor / document_loader / paths / gui / ai_refine / test_competition_flow + README / 检修记录 / AGENTS）

## 验证

```bash
python test_header_preserve.py
python test_logic_expected.py
python test_general_flow.py
python test_query_page.py
python test_competition_flow.py
python test_fixes.py
python test_round3.py   # 本轮新增（18 项断言）
```

七套全过（2026-09-14 深夜）。GUI 部分改动（.json 路由、历史对话框、管理区第二行）无自动化覆盖，需要双击程序点一遍确认。
