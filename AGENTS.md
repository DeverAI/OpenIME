# OpenIME - 微软拼音用户词库管家

## 产品定位
通用 **垂域 IME 适配** 工具：把任意文档/术语表写入微软拼音用户词库（UDL）。
- 双击 GUI，默认路径
- 支持 TXT / MD / CSV / PDF / DOCX / JSON 词库包
- 增删查改、预览导入、自动备份、词库包分发
- 古诗文仅为可选抽取模式，**不是**产品主领域

## UDL 技术要点
- 路径: `%APPDATA%\Microsoft\InputMethod\Chs\ChsPinyinUDL.dat`
- 头 0x2400；词条数 offset 0xC u32 LE
- 每词条 60 字节；词 UTF-16LE + 拼音 u16 索引
- **单条最大 12 字**；超长写入前必须截断，禁止 overflow 写坏相邻词条
- 拼音表: `pinyin_table.json`（与真机 UDL 对齐，idx0=`a`；真机校验约 98.6%）
- 空拼音写哨兵 `0xFFFF`，**不得**写成 0（0 是合法音节 `a`）
- 简拼：前 3 音节首字母（英文取前 3 字母）；默认 `0x00*3` 必须重新计算
- **文件头 0x470+ 有索引/统计**：合并写入必须 `preserve_header=True` 复制原头，只改 count/timestamp
- 写路径用 `_WRITE_LOCK`；写入是原子的（临时文件+回读校验+`os.replace`），空词条不落盘
- **基本平面外字符（UTF-16 代理对，如 𠮷）写不进 60 字节词条结构**：`looks_like_term` / `add_entry` / `write` payload 三处都必须拒收
- `load_entries()` 按 (mtime,size) 缓存并返回共享列表，调用方**不得修改**；写路径成功后必须 `_cache_invalidate()`
- 导入历史 manifest 在 `%APPDATA%\OpenIME\history\`；`undo_last_import()` 删最近一批新增词；**历史排序必须按文件 mtime（`_history_files()`）**——文件名同秒 `_N` 后缀有字典序陷阱（`import_9 > import_10`），按名排会取错"最近"
- APPDATA 为空必须报错
- 备份目录: 同级 `OpenIME_Backups/`，只保留最近 30 份
- 检修记录: `docs/检修记录.md`

## 抽词策略
1. `lines`: 一行一词 / 顿号列表（术语表首选）
2. `auto`: 短行整行 + 长行按标点短语 + 英文术语
3. `sentences`: 标点切短语
4. `poetry`: 整句+节奏组（可选）
- 过滤：长度 2–12、停用虚词、纯标点数字
- 幂等：与现有词库去重后合并

## 项目结构
```
OpenIME/
├── main.py                 # 无参数 → GUI；带参数 → CLI
├── gui.py
├── app_core.py
├── document_loader.py      # txt/md/csv/tsv/log/pdf/docx；.json → 引导词库包流程
├── term_extractor.py
├── poetry_processor.py     # 可选
├── competition_data.py     # 内置古诗文竞赛篇目库
├── udl_core.py
├── paths.py
├── pinyin_table.json
├── ai_refine.py            # 实验性、未接线（云 API 部分勿启用）
├── build_exe.py            # → dist/OpenIME词库管家.exe
├── 词库包_初三*.txt         # 内置学科词库包（build_exe 打进 exe）
├── test_general_flow.py
├── test_logic_expected.py  # 预期逻辑回归（必须过）
├── test_fixes.py           # 原子写/缓存/历史/撤销/改拼音回归
├── test_round3.py          # 第三轮检修回归（拼音对齐/代理对/引导/安全中止）
└── README.md
```

## 规范
- Python 3.10+；pypinyin；pypdf / python-docx（PDF/Word）；可选 pymupdf
- 不依赖云 API
- UI 白话中文
- 写 UDL 必须先备份
- 打包: `--onefile --windowed`

## 测试
```
python test_header_preserve.py
python test_logic_expected.py
python test_general_flow.py
python test_query_page.py
python test_competition_flow.py
python test_fixes.py
python test_round3.py
```
使用临时 APPDATA，不碰真实词库。改 UDL/拼音表/抽词后必须全过。
真机文件头对照与风险见 `docs/检修记录.md`。
