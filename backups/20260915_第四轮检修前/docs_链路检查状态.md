# OpenIME 第四轮检修 · 链式检查状态表
> 方法：BFS 溯源。从入口（main.py / gui.py / build_exe.py）出发，把每个文件所依赖的
> 内容向上溯源到源头；✅ = 已通读并记录结论，🔎 = 检查中，⬜ = 待检查，📦 = 产物/不深查。
> 本表随进度即时更新，最后一条记录即为收尾状态。

## 依赖链（本次实际遍历顺序）

```
main.py ─┬─ app_core.py ─┬─ udl_core.py ─┬─ paths.py
         │                │               └─ pinyin_table.json
         │                ├─ term_extractor.py ── poetry_processor.py
         │                ├─ document_loader.py（pypdf / python-docx / fitz，外部）
         │                ├─ poetry_processor.py
         │                ├─ competition_data.py
         │                └─ paths.py
         └─ gui.py（同 app_core 链）
build_exe.py ── main.py + 资源文件（pinyin_table.json、词库包_初三*.txt、词库包_古诗文比赛.txt）
ai_refine.py ──（无入链，实验性未接线，仅通读）
测试层：test_header_preserve / test_logic_expected / test_general_flow / test_query_page /
        test_competition_flow / test_fixes / test_round3 ── 全部依赖 app_core/udl_core
        test_udl.py ── 游离于规范外的旧工具（见问题 F11）
真机对照：%APPDATA%\Microsoft\InputMethod\Chs\ChsPinyinUDL.dat（只读）
```

## 逐文件状态（2026-09-15 第四轮）

| 文件 | 状态 | 结论 / 发现问题 |
|------|------|----------------|
| main.py | ✅ | 入口分发正常。F8：windowed exe 下 stdin 为 None 会裸崩 |
| gui.py | ✅ | 结构正常。F12：竞赛库无 GUI 入口；预览 0 新增时文案歧义（轻微，记而未改） |
| app_core.py | ✅ | F2 词库包往返丢拼音（from_dict_list 无人用）；F3 replace 分支备份无保护 + restore 无锁非原子；F6 备份同秒撞名 |
| udl_core.py | ✅ | **F1 重复音节写侧索引取末位**（ai/de/ge 错选，真机数据实证）；F7 update_entry_pinyin 不校验音节 |
| paths.py | ✅ | 无新问题（第三轮已修） |
| term_extractor.py | ✅ | F4 纯数字放行（违反 AGENTS 过滤规范）；F5 auto/sentences 不剥列表记号 |
| document_loader.py | ✅ | 无新问题（fitz warn、json 引导均已在二/三轮修复）|
| poetry_processor.py | ✅ | 逻辑正常；split_mixed_text 仍是无调用者旧接口（保留） |
| competition_data.py | ✅ | 116 篇目，数据面正常；F12 无入口 |
| ai_refine.py | ✅ | 维持"实验性未接线"结论，不动 |
| build_exe.py | ✅ | 资源清单齐全；docx 无 lxml 时走 zipfile 兜底成立 |
| pinyin_table.json | ✅ | 429 项，4 组重复（ai 1/80、de 61/62、fu 91/93、ge 99/182）→ 真机对照见 F1 |
| 词库包_初三*.txt ×4 | ✅ | 内容偏薄（F13 增强候选） |
| requirements.txt / AGENTS.md / README.md | ✅ | README 有错字"简拋"；文档随本轮收尾更新 |
| test_header_preserve.py | ✅ | 有效 |
| test_logic_expected.py | ✅ | 有效；§6 往返不验拼音（F2 漏检原因） |
| test_general_flow.py | ✅ | 有效 |
| test_query_page.py | ✅ | 有效 |
| test_competition_flow.py | ✅ | 有效（临时 APPDATA 隔离确认） |
| test_fixes.py | ✅ | 有效 |
| test_round3.py | ✅ | 有效 |
| test_udl.py | 🔎 | **F11：读写真实用户词库目录、把全库导出到项目目录**（隐私），游离规范 |
| AGENT.txt | ✅ | 遗留全局提示词，与 AGENTS.md 冲突，待用户裁决（本轮不动） |
| OpenIME.spec / 古诗文输入助手.spec / *.log / dist / build | 📦 | 构建产物，不深查 |
| .gitignore / LICENSE / 示例*.txt / test_import.txt | ✅ | 无问题 |

## 本轮问题清单（详细验证与修复记录见 docs/检修记录.md 第四轮）

- **F1 严重** `get_index_by_pinyin` 对重复音节取"最后一次出现"：真机高频槽位为 ai→1、de→61、ge→99、
  fu→93，而现逻辑写 ai→80、de→62、ge→182（fu 侥幸正确）。写入的新词会被钉在真机罕见的索引上，
  与 98.6% 校准目标背道。实证：真机 8697 条逐字位投票。
- **F2 严重** 词库包 export→import 往返丢失全部拼音/改音成果（import_pack 只取 word 重新猜音）。
- **F3 高** import_pack 替换分支 `backup_udl` 无 try/except（备份失败=裸 traceback 冒泡，违反写库红线话术）；
  `restore_backup` 不持 `_WRITE_LOCK` 且直接 copy2 覆盖（非原子、可与并发写竞速）。
- **F4 中** `looks_like_term("12345")` = True：纯数字词条放行，违反"过滤纯标点数字"规范。
- **F5 中** `1. 化学变化` 这类带编号行在 auto/sentences 模式产出 `1.化学变化` 脏词条（lines 模式会剥，其它不剥）。
- **F6 中** 同秒两次备份目标文件名相同 → copy2 静默覆盖，丢一份历史。
- **F7 中** 改拼音不校验音节：输入 `zhòng`/`zhong4` 全部静默落 0xFFFF 哨兵，用户以为改好了其实整词失音。
- **F8 低** windowed exe 里 CLI `import` 无 -f/-t 时 `sys.stdin` 为 None 直接崩。
- **F11 中** test_udl.py 旧工具：读真机词库并把全库导出到项目目录（隐私落盘），游离于测试规范之外。
- **F12 功能缺口** 116 首竞赛篇目库 + `import_competition_library`（含幂等）只有测试能调用，GUI/CLI 均无入口；
  GUI"古诗文"按钮实际只导入 19 行样例。对"靠它撑古诗文比赛"的用户等于功能不存在。
- **F13 功能线索** 学科词库包各只有 9–17 词，撑不起"补漏"场景 → 扩充到每科 40+ 核心词条。
