"""
OpenIME - 微软拼音用户词库管家

无参数 / gui → 图形界面
带参数 → 命令行
"""

from __future__ import annotations

import argparse
import sys


def _wants_gui(argv) -> bool:
    if len(argv) <= 1:
        return True
    if argv[1] in ("gui", "--gui", "/gui"):
        return True
    return False


def run_cli(argv) -> int:
    import app_core

    parser = argparse.ArgumentParser(
        prog="OpenIME",
        description="微软拼音用户词库管家（垂域术语导入 / 增删查改 / 备份）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  OpenIME.exe                           # 图形界面
  OpenIME.exe import -f 术语.txt        # 文档导入
  OpenIME.exe import -f 手册.pdf --mode lines
  OpenIME.exe import -f 规范.docx
  OpenIME.exe add 产品经理 需求评审
  OpenIME.exe status
  OpenIME.exe query -k 产品
  OpenIME.exe export -o pack.json
  OpenIME.exe import-pack -c pack.json
        """,
    )
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("import", help="从文档/文本导入并抽词")
    p.add_argument("-f", "--file", action="append", help="文件路径，可重复")
    p.add_argument("-t", "--text", help="直接文本")
    p.add_argument("--mode", default="auto", choices=["auto", "lines", "sentences", "poetry"])
    p.add_argument("--no-latin", action="store_true", help="不提取英文术语")
    p.add_argument("--yes", "-y", action="store_true", help="不预览直接写入")

    p = sub.add_parser("add", help="按字面添加词条")
    p.add_argument("words", nargs="+")

    p = sub.add_parser("delete", help="删除词条")
    p.add_argument("words", nargs="+")

    p = sub.add_parser("query", help="搜索")
    p.add_argument("-k", "--keyword", default="")
    p.add_argument("-l", "--limit", type=int, default=30)

    sub.add_parser("status", help="状态")
    sub.add_parser("backup", help="备份")

    p = sub.add_parser("restore", help="恢复备份")
    p.add_argument("path")

    p = sub.add_parser("export", help="导出词库包 JSON")
    p.add_argument("-o", "--output")
    p.add_argument("--name", default="OpenIME 词库包")

    p = sub.add_parser("import-pack", help="导入词库包 JSON")
    p.add_argument("-c", "--config", required=True)
    p.add_argument("--replace", action="store_true", help="替换而非合并")

    args = parser.parse_args(argv[1:])
    if not args.command:
        parser.print_help()
        return 0

    app_core.ensure_ready()
    latin = not getattr(args, "no_latin", False)
    mode = getattr(args, "mode", "auto")

    if args.command == "import":
        texts = []
        if args.file:
            from document_loader import load_many
            docs, errors = load_many(args.file)
            for e in errors:
                print(f"[警告] {e}")
            texts = [d.text for d in docs]
            if not texts:
                print("没有读到可用文本")
                return 1
        if args.text:
            texts.append(args.text)
        if not texts:
            print("请粘贴内容，Windows 结束: Ctrl+Z 回车")
            texts.append(sys.stdin.read())
        from term_extractor import extract
        terms = []
        seen = set()
        for t in texts:
            for w in extract(t, mode=mode, include_latin=latin).get("terms") or []:
                if w not in seen:
                    seen.add(w)
                    terms.append(w)
        preview = app_core.preview_add(terms, source_desc="CLI 导入")
        print(f"候选 {len(terms)}，新增 {preview.add_count}，已存在 {len(preview.already)}")
        if not args.yes:
            for w in preview.to_add[:30]:
                print("  +", w)
            if preview.add_count > 30:
                print(f"  … 共 {preview.add_count} 条")
            ans = input(f"写入 {preview.add_count} 条? [y/N] ").strip().lower()
            if ans not in ("y", "yes"):
                print("已取消")
                return 0
        r = app_core.apply_tokens(preview.to_add, source_desc="CLI 导入")
    elif args.command == "add":
        r = app_core.add_words(args.words)
    elif args.command == "delete":
        r = app_core.delete_entries(args.words)
    elif args.command == "query":
        hits = app_core.search_entries(args.keyword, limit=args.limit)
        print(f"共 {len(hits)} 条")
        for e in hits:
            print(f"  {e.word}  {' '.join(e.pinyin)}")
        return 0
    elif args.command == "status":
        s = app_core.status_summary()
        print(f"词库路径: {s['path']}")
        print(f"文件存在: {'是' if s['exists'] else '否'}")
        print(f"当前词条: {s['count']}")
        print(f"备份份数: {s['backups']}")
        print(f"支持格式: {s['supported']}")
        return 0
    elif args.command == "backup":
        path = app_core.backup_udl("cli")
        if path:
            print(f"已备份到: {path}")
            return 0
        print("没有可备份的词库文件")
        return 1
    elif args.command == "restore":
        r = app_core.restore_backup(args.path)
    elif args.command == "export":
        r = app_core.export_pack(args.output, name=args.name)
    elif args.command == "import-pack":
        r = app_core.import_pack(args.config, merge=not args.replace)
    else:
        parser.print_help()
        return 0

    print(("成功" if r.ok else "失败") + f"：{r.message}")
    if r.detail:
        print(r.detail)
    return 0 if r.ok else 1


def main():
    argv = sys.argv
    if _wants_gui(argv):
        try:
            from gui import run_gui
            run_gui()
            return 0
        except Exception as e:
            sys.stderr.write(f"无法启动图形界面：{e}\n")
            sys.stderr.write("可使用命令行：OpenIME.exe --help\n")
            return 1
    return run_cli(argv)


if __name__ == "__main__":
    raise SystemExit(main())
