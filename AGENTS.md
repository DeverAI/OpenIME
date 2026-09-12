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
- 写路径用 `_WRITE_LOCK`；APPDATA 为空必须报错
- 备份目录: 同级 `OpenIME_Backups/`
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
├── main.py                 # 无参数 → GUI
├── gui.py
├── app_core.py
├── document_loader.py      # txt/pdf/docx
├── term_extractor.py
├── poetry_processor.py     # 可选
├── udl_core.py
├── paths.py
├── pinyin_table.json
├── build_exe.py            # → dist/OpenIME词库管家.exe
├── test_general_flow.py
├── test_logic_expected.py  # 预期逻辑回归（必须过）
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
```
使用临时 APPDATA，不碰真实词库。改 UDL/拼音表/抽词后必须全过。
真机文件头对照与风险见 `docs/检修记录.md`。
