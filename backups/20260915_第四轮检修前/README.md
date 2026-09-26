# OpenIME · 微软拼音词库管家

[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](LICENSE)

把 **PDF / Word / 文本** 里的术语写进微软拼音用户词库，用来做**垂域输入法适配**（教材补漏、竞赛、自招、公司黑话……都行）。

双击打开图形界面，不需要懂命令行。

---

## 初三怎么用（知识补漏 / 自招 / 古诗文比赛）

| 场景 | 做法 |
|------|------|
| 数理化补漏 | 仓库里有 `词库包_初三数学.txt` 等，选文档 → **一行一个术语** → 导入 |
| 古诗文线上比赛 | 用 `词库包_古诗文比赛.txt`，或粘贴篇目；可选「古诗文整句+节奏组」 |
| 自招/拓展 | 把讲义 Word/PDF 导入，自动抽短语；预览里删掉废话再写入 |
| 打错了/导入乱了 | 点 **恢复…**，选导入前自动备份 |

导入成功后：**注销重新登录**（或中英切一次），记事本里打拼音/简拋试一试。

---

## 一、你需要什么

- Windows 10 / 11
- 已启用 **微软拼音**
- `dist/OpenIME词库管家.exe`（或源码运行 `python main.py`）

---

## 二、三步上手

### 1. 打开程序
双击 `OpenIME词库管家.exe`。

### 2. 导入文档
点 **「选择文档…」**，可多选：

| 格式 | 说明 |
|------|------|
| `.txt` `.md` `.csv` | 推荐，一行一个术语最稳 |
| `.docx` | Word 2007+；旧版 `.doc` 请先另存为 docx |
| `.pdf` | 文本型 PDF；扫描版需先 OCR |
| `.json` | OpenIME 词库包：会自动转走「导入词库包」流程（也可直接点「导入词库包…」） |

抽取方式可选：

- **自动识别（推荐）**
- **一行一个术语 / 顿号列表** —— 术语表用这个
- **按标点抽短语**
- **古诗文整句+节奏组** —— 临时垂域可选，默认不用

导入前会弹出**预览**：新增几条、已存在几条，确认后才写入。

### 3. 生效
写入后：

- 注销 Windows 再登录，或
- 中 / 英输入法切换一次

然后打拼音，候选里应出现你的术语。

---

## 三、日常管理

| 按钮 | 作用 |
|------|------|
| 浏览词库 | **分页看全部词条**；支持词条/拼音/简拼搜索（如 `明月`、`mingyue`、`my`，英文不区分大小写）；可导出 txt/csv；选中一条可**改拼音**（修多音字） |
| 撤销上次导入 | 一键删掉最近一次导入的那批词条，其余不动 |
| 历史… | 查看最近 200 条写入记录（导入 / 删除 / 替换 / 改拼音 / 恢复） |
| 粘贴文本… | 直接贴术语表 |
| 添加词条… | 手动补几条 |
| 搜索 / 删除 | 查、删误导入的词 |
| 备份 / 恢复… | 全量备份与回滚（恢复前会先验证备份文件有效） |
| 导出词库包 | 导出 JSON，换机器或分发给队员 |
| 导入词库包… | 合并或替换 |

主界面还有**内置词库包**一键导入：数学 / 物理 / 化学 / 古诗文。

**每次写入前自动备份**，目录：

```text
%APPDATA%\Microsoft\InputMethod\Chs\OpenIME_Backups\
```

---

## 四、建议的材料怎么准备

**最好用（准确率高）：**

```text
产品经理
需求评审
技术方案
发版窗口
灰度发布
```

**也可以：**

```text
数据库索引、查询执行计划、慢查询优化
```

**Word/PDF 说明书**也能导入，但会多抽出一些句子碎片，请用预览确认，再在「搜索 / 删除」里微调。

---

## 五、命令行（脚本 / 老师）

```bat
OpenIME词库管家.exe import -f 术语.txt --mode lines -y
OpenIME词库管家.exe import -f 手册.docx --mode auto
OpenIME词库管家.exe add 机器学习 特征工程
OpenIME词库管家.exe query -k 索引
OpenIME词库管家.exe export -o 医学术语.json --name 医学术语
OpenIME词库管家.exe import-pack -c 医学术语.json
OpenIME词库管家.exe status
OpenIME词库管家.exe history   # 查看导入/删除/替换历史
OpenIME词库管家.exe undo      # 撤销最近一次导入
```

源码：

```bat
python main.py --help
python main.py import -f 示例术语.txt --mode lines -y
```

---

## 六、常见问题

**Q：导入了但打不出来？**  
A：注销重新登录。输入法不会热加载用户词库。

**Q：一条词最多几个字？**  
A：微软拼音用户词库单条约 **12 字**。更长会被过滤或需拆分。

**Q：会弄坏系统输入法吗？**  
A：写入前自动备份，界面可恢复。异常时把 `ChsPinyinUDL.dat.bak_openime` 复制回 `ChsPinyinUDL.dat`。

**Q：旧版 .doc？**  
A：请在 Word 里另存为 `.docx`，或导出 `.txt`。

**Q：选了 .json 却抽出一堆乱码短语？**  
A：`.json` 是词库包格式，不是普通文档——请用「导入词库包…」按钮（现在选文档时也会自动转过去）。

**Q：扫描版 PDF？**  
A：先用 OCR 转成文字版 PDF 或 txt。

**Q：需要联网 / API Key？**  
A：不需要。

---

## 七、开发

```text
OpenIME/
├── main.py                  # 入口：无参数 → GUI；带参数 → CLI
├── gui.py                   # 图形界面（tkinter）
├── app_core.py              # 业务：导入/删改查/备份恢复/历史撤销/词库包
├── document_loader.py       # txt/md/csv/tsv/log/pdf/docx（.json 引导到词库包流程）
├── term_extractor.py        # 通用抽词（auto/lines/sentences）
├── poetry_processor.py      # 可选：古诗文整句+节奏组
├── competition_data.py      # 内置古诗文竞赛篇目库
├── udl_core.py              # UDL 二进制读写（原子写、头保留）
├── paths.py                 # 资源路径（源码/打包兼容）
├── pinyin_table.json        # 拼音索引表（与真机对齐，勿手改）
├── ai_refine.py             # 实验性，未接入主流程（勿默认启用云 API）
├── build_exe.py             # → dist/OpenIME词库管家.exe
├── 词库包_初三*.txt 等        # 内置学科词库包（打进 exe）
├── test_header_preserve.py  # 头保留回归
├── test_logic_expected.py   # 预期逻辑回归（必须过）
├── test_general_flow.py     # 通用导入链路
├── test_query_page.py       # 分页/搜索
├── test_competition_flow.py # 竞赛库端到端
├── test_fixes.py            # 原子写/缓存/历史/撤销/改拼音回归
├── test_round3.py           # 第三轮检修回归（拼音对齐/代理对/引导/安全中止）
├── docs/检修记录.md          # 历轮检修记录
└── backups/                 # 每轮检修前的源码快照
```

```bat
pip install pypinyin pypdf python-docx
pip install pymupdf    # 可选，PDF 质量更好
python build_exe.py
```

输出：`dist/OpenIME词库管家.exe`

测试：

```bat
python test_header_preserve.py
python test_logic_expected.py
python test_general_flow.py
python test_query_page.py
python test_competition_flow.py
python test_fixes.py
python test_round3.py
```

---

## 许可证

本项目以 [GNU Affero General Public License v3.0](LICENSE)（AGPL-3.0）发布。

使用、修改或分发本软件时，请遵守 AGPL-3.0 条款；若通过网络向用户提供服务，须按 AGPL 提供对应源代码。

