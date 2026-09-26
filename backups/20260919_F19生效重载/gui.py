"""
OpenIME · 微软拼音词库管家（通用垂域适配）

把任意文档/词表写入微软拼音用户词库；导入前预览；自动备份。
"""

from __future__ import annotations

import os
import csv
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import List, Optional

import app_core
from paths import resource_path


BG = "#F3F1EC"
PANEL = "#FBFAF7"
INK = "#222222"
MUTED = "#666666"
ACCENT = "#1F4E79"
BTN_BG = "#1F4E79"
BTN_FG = "#FFFFFF"
BORDER = "#D5D0C6"

FILE_TYPES = [
    ("支持的文档", "*.txt *.md *.csv *.tsv *.log *.pdf *.docx"),
    ("文本", "*.txt *.md *.csv *.tsv *.log"),
    ("PDF", "*.pdf"),
    ("Word", "*.docx"),
    ("词库包 JSON", "*.json"),
    ("所有文件", "*.*"),
]

MODE_LABELS = [
    ("auto", "自动识别（推荐）"),
    ("lines", "一行一个术语 / 顿号列表"),
    ("sentences", "按标点抽短语"),
    ("poetry", "古诗文整句+节奏组（可选）"),
]

BUILTIN_PACKS = [
    ("数学", "词库包_初三数学.txt"),
    ("物理", "词库包_初三物理.txt"),
    ("化学", "词库包_初三化学.txt"),
    ("古诗文", "词库包_古诗文比赛.txt"),
]

LOG_MAX_LINES = 800  # 记录区只留最近若干行，防止长时间运行无限增长


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("OpenIME · 微软拼音词库管家")
        self.geometry("820x640")
        self.minsize(760, 580)
        self.configure(bg=BG)
        self._busy = False
        self._pending_paths: List[str] = []
        self._action_buttons: List[tk.Button] = []

        self._styles()
        self._ui()
        self.after(150, self.refresh_status)

    def _styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use("vista")
        except Exception:
            style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=PANEL)
        style.configure("TLabel", background=BG, foreground=INK, font=("Microsoft YaHei UI", 11))
        style.configure("Title.TLabel", background=BG, foreground=INK, font=("Microsoft YaHei UI", 17, "bold"))
        style.configure("Sub.TLabel", background=BG, foreground=MUTED, font=("Microsoft YaHei UI", 10))
        style.configure("Card.TLabel", background=PANEL, foreground=INK, font=("Microsoft YaHei UI", 10))
        style.configure("Box.TLabelframe", background=PANEL)
        style.configure("Box.TLabelframe.Label", background=PANEL, foreground=ACCENT, font=("Microsoft YaHei UI", 10, "bold"))

    def _ui(self):
        head = ttk.Frame(self)
        head.pack(fill="x", padx=18, pady=(14, 6))
        ttk.Label(head, text="微软拼音词库管家", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            head,
            text="导入 PDF / Word / 文本 → 抽词 → 写入用户词库。用于垂域术语适配，写入前可预览。",
            style="Sub.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        # 导入区
        box = ttk.LabelFrame(self, text=" 导入 ", style="Box.TLabelframe")
        box.pack(fill="x", padx=18, pady=6)

        row1 = ttk.Frame(box, style="Card.TFrame")
        row1.pack(fill="x", padx=10, pady=8)
        self._btn(row1, "选择文档…", self.on_pick_files, primary=True).pack(side="left", padx=(0, 8))
        self._btn(row1, "粘贴文本…", self.on_paste, primary=False).pack(side="left", padx=(0, 8))
        self._btn(row1, "添加词条…", self.on_add_words, primary=False).pack(side="left")

        row2 = ttk.Frame(box, style="Card.TFrame")
        row2.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Label(row2, text="抽取方式", style="Card.TLabel").pack(side="left")
        self.mode_var = tk.StringVar(value="auto")
        cb = ttk.Combobox(
            row2, textvariable=self.mode_var, state="readonly", width=28,
            values=[label for _, label in MODE_LABELS],
        )
        cb.pack(side="left", padx=8)
        cb.current(0)
        self.mode_cb = cb
        self.latin_var = tk.BooleanVar(value=True)
        self.latin_cb = tk.Checkbutton(
            row2, text="同时提取英文术语", variable=self.latin_var,
            bg=PANEL, font=("Microsoft YaHei UI", 10),
        )
        self.latin_cb.pack(side="left", padx=12)

        # 内置词库包
        boxp = ttk.LabelFrame(self, text=" 内置词库包（一键导入） ", style="Box.TLabelframe")
        boxp.pack(fill="x", padx=18, pady=4)
        rowp = ttk.Frame(boxp, style="Card.TFrame")
        rowp.pack(fill="x", padx=10, pady=6)
        ttk.Label(rowp, text="初三样例：", style="Card.TLabel").pack(side="left")
        for label, fname in BUILTIN_PACKS:
            self._btn(
                rowp, label,
                lambda f=fname, lb=label: self.on_quick_pack(f, lb),
            ).pack(side="left", padx=(0, 6))
        self._btn(rowp, "古诗文竞赛库", self.on_import_comp, False).pack(side="left", padx=(6, 0))

        # 管理区
        box2 = ttk.LabelFrame(self, text=" 管理 ", style="Box.TLabelframe")
        box2.pack(fill="x", padx=18, pady=4)
        row3 = ttk.Frame(box2, style="Card.TFrame")
        row3.pack(fill="x", padx=10, pady=8)
        self._btn(row3, "浏览词库", self.on_view, False).pack(side="left", expand=True, fill="x", padx=(0, 6))
        self._btn(row3, "备份", self.on_backup, False).pack(side="left", expand=True, fill="x", padx=6)
        self._btn(row3, "恢复…", self.on_restore, False).pack(side="left", expand=True, fill="x", padx=6)
        self._btn(row3, "导出词库包", self.on_export, False).pack(side="left", expand=True, fill="x", padx=6)
        self._btn(row3, "导入词库包…", self.on_import_pack, False).pack(side="left", expand=True, fill="x", padx=6)
        self._btn(row3, "撤销上次导入", self.on_undo, False).pack(side="left", expand=True, fill="x", padx=(6, 0))
        row4 = ttk.Frame(box2, style="Card.TFrame")
        row4.pack(fill="x", padx=10, pady=(0, 8))
        self._btn(row4, "历史…", self.on_history, False).pack(side="left", padx=(0, 6))
        self._btn(row4, "重载输入法", self.on_reload_ime, False).pack(side="left", padx=(0, 6))
        ttk.Label(
            row4,
            text="查看最近写入记录；「重载输入法」= 让刚写入的新词立即生效（输入法条闪一下，正常）",
            style="Card.TLabel",
        ).pack(side="left")

        # 状态
        st = ttk.LabelFrame(self, text=" 状态 ", style="Box.TLabelframe")
        st.pack(fill="x", padx=18, pady=4)
        self.status_var = tk.StringVar(value="正在检查词库…")
        ttk.Label(st, textvariable=self.status_var, style="Card.TLabel", justify="left").pack(
            fill="x", padx=10, pady=8
        )

        # 日志
        lg = ttk.LabelFrame(self, text=" 记录 ", style="Box.TLabelframe")
        lg.pack(fill="both", expand=True, padx=18, pady=(4, 10))
        lg_inner = ttk.Frame(lg)
        lg_inner.pack(fill="both", expand=True, padx=8, pady=8)
        self.log = tk.Text(
            lg_inner, wrap="word", bg="#FFFFFF", fg=INK,
            font=("Microsoft YaHei UI", 10), relief="flat", padx=10, pady=8,
        )
        log_sb = ttk.Scrollbar(lg_inner, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=log_sb.set)
        self.log.pack(side="left", fill="both", expand=True)
        log_sb.pack(side="right", fill="y")
        self.log.configure(state="disabled")

        ttk.Label(
            self,
            text="写入后请注销重新登录，或中/英切换一次。单条上限约 12 字。初三用法见 README：补漏词表 / 古诗文比赛 / 自招术语。",
            style="Sub.TLabel",
        ).pack(anchor="w", padx=18, pady=(0, 10))

    def _btn(self, parent, text, command, primary=False, register=True):
        if primary:
            b = tk.Button(
                parent, text=text, command=command,
                bg=BTN_BG, fg=BTN_FG, activebackground="#163A5A", activeforeground=BTN_FG,
                relief="flat", font=("Microsoft YaHei UI", 12, "bold"), padx=14, pady=10, cursor="hand2",
            )
        else:
            b = tk.Button(
                parent, text=text, command=command,
                bg=PANEL, fg=INK, activebackground="#E8E4DB", relief="groove",
                font=("Microsoft YaHei UI", 10), padx=10, pady=7, cursor="hand2",
            )
        if register:
            self._action_buttons.append(b)
        return b

    def _mode_id(self) -> str:
        label = self.mode_var.get()
        for mid, lab in MODE_LABELS:
            if lab == label:
                return mid
        return "auto"

    def append_log(self, text: str):
        self.log.configure(state="normal")
        self.log.insert("end", text.rstrip() + "\n")
        # 内容以换行结尾时 "end-1c" 折叠回上一行行尾，行数按 "end - 1 char" 读才准
        line_count = len(self.log.get("1.0", "end - 1 char").splitlines())
        if line_count > LOG_MAX_LINES:
            self.log.delete("1.0", f"{line_count - LOG_MAX_LINES + 1}.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    def set_busy(self, busy: bool, msg: str = ""):
        self._busy = busy
        state = "disabled" if busy else "normal"
        for b in self._action_buttons:
            try:
                b.configure(state=state)
            except Exception:
                pass
        try:
            self.mode_cb.configure(state="disabled" if busy else "readonly")
            self.latin_cb.configure(state=state)
        except Exception:
            pass
        try:
            self.configure(cursor="watch" if busy else "")
        except Exception:
            pass
        if msg:
            self.status_var.set(msg)

    def refresh_status(self):
        def work():
            try:
                s = app_core.status_summary()
            except Exception as e:
                text = f"检查失败：{e}"
            else:
                if s["exists"]:
                    text = (
                        f"词库路径：{s['path']}\n"
                        f"当前词条：{s['count']} 条    备份：{s['backups']} 份\n"
                        f"支持格式：{s['supported']}"
                    )
                else:
                    text = (
                        "尚未找到微软拼音用户词库。\n"
                        "请确认已启用微软拼音；导入时会自动创建。\n"
                        f"路径：{s['path']}"
                    )
            self.after(0, lambda: self.status_var.set(text))

        threading.Thread(target=work, daemon=True).start()

    def _run_async(self, fn, title="完成", on_done=None):
        if self._busy:
            self.status_var.set("已有操作进行中，请稍候…")
            return
        self.set_busy(True, "处理中…")

        def work():
            try:
                result = fn()
            except Exception as e:
                result = app_core.OperationResult(False, f"出错了：{e}")

            def finish():
                self.set_busy(False)
                msg = result.message + (("\n\n" + result.detail) if result.detail else "")
                if result.ok:
                    self.append_log(f"✓ {title}：{result.message}")
                    if result.detail:
                        self.append_log(result.detail)
                else:
                    self.append_log(f"✗ {result.message}")
                    if result.detail:
                        self.append_log(result.detail)
                if on_done:
                    try:
                        on_done(result)
                    except Exception as e:
                        self.append_log(f"回调出错：{e}")
                if result.ok:
                    messagebox.showinfo(title, msg)
                else:
                    messagebox.showwarning("未能完成", msg)
                self.refresh_status()

            self.after(0, finish)

        threading.Thread(target=work, daemon=True).start()

    def _confirm_preview(self, terms: List[str], source_desc: str) -> Optional[List[str]]:
        """返回 None=用户取消；[]=确认但无新增；非空=写入这批。"""
        preview = app_core.preview_add(terms, source_desc)
        win = tk.Toplevel(self)
        win.title("导入预览")
        win.configure(bg=BG)
        win.geometry("640x480")
        win.transient(self)
        win.grab_set()

        msg = "\n".join(preview.describe())
        ttk.Label(win, text="确认导入", style="Title.TLabel").pack(anchor="w", padx=16, pady=(12, 4))
        ttk.Label(win, text=msg, style="TLabel", wraplength=600, justify="left").pack(anchor="w", padx=16)

        box = ttk.Frame(win)
        box.pack(fill="both", expand=True, padx=16, pady=8)
        list_title = "将新增的词条" if preview.add_count else "已在词库中的词条"
        ttk.Label(box, text=list_title, style="Sub.TLabel").pack(anchor="w", pady=(0, 2))
        lb = tk.Listbox(box, font=("Microsoft YaHei UI", 10))
        sb = ttk.Scrollbar(box, orient="vertical", command=lb.yview)
        lb.configure(yscrollcommand=sb.set)
        lb.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        show = preview.to_add[:200] or preview.already[:50]
        for t in show:
            lb.insert("end", t)
        if preview.add_count > 200:
            lb.insert("end", f"… 另有 {preview.add_count - 200} 条未列出")

        holder = {"result": None}

        def do_ok():
            holder["result"] = preview.to_add
            win.destroy()

        def do_nothing():
            holder["result"] = []
            win.destroy()

        def do_cancel():
            win.destroy()

        win.bind("<Escape>", lambda _e: do_cancel())
        btns = ttk.Frame(win)
        btns.pack(pady=10)
        if preview.add_count:
            self._btn(btns, f"写入 {preview.add_count} 条", do_ok, primary=True, register=False).pack(side="left", padx=6)
            self._btn(btns, "取消", do_cancel, primary=False, register=False).pack(side="left", padx=6)
        else:
            self._btn(btns, "知道了（无新增）", do_nothing, primary=True, register=False).pack(side="left", padx=6)
            self._btn(btns, "关闭", do_cancel, primary=False, register=False).pack(side="left", padx=6)

        win.wait_window()
        return holder["result"]

    # ---------- actions ----------
    def on_pick_files(self):
        paths = list(filedialog.askopenfilenames(parent=self, title="选择文档", filetypes=FILE_TYPES))
        if not paths:
            return
        packs = [p for p in paths if p.lower().endswith(".json")]
        docs = [p for p in paths if not p.lower().endswith(".json")]
        if packs and docs:
            messagebox.showinfo(
                "同时选了词库包和文档",
                "JSON 是词库包格式，会按「导入词库包」处理；\n其余文件按文档导入（会弹预览）。\n\n如需分开处理，请分两次选择。",
            )
        if docs and packs:
            self._import_flow(
                docs, self._mode_id(), self.latin_var.get(), "导入文档",
                then=lambda: self._import_packs_flow(packs),
            )
        elif docs:
            self._import_flow(docs, self._mode_id(), self.latin_var.get(), "导入文档")
        elif packs:
            self._import_packs_flow(packs)

    def on_quick_pack(self, fname: str, label: str):
        if self._busy:
            return
        path = resource_path(fname)
        if not os.path.exists(path):
            messagebox.showinfo(
                "没有找到内置词库包",
                f"未找到 {fname}。\n源码目录或打包资源里不存在这个文件。",
            )
            return
        self._import_flow([path], mode="lines", latin=False, title=f"词库包·{label}")

    def on_import_comp(self):
        """内置古诗文竞赛篇目库（116 首，整句+节奏组），幂等合并。"""
        if self._busy:
            return
        self._run_async(app_core.import_competition_library, "古诗文竞赛库")

    def on_undo(self):
        def work():
            return app_core.undo_last_import()

        self._run_async(work, "撤销上次导入")

    def on_reload_ime(self):
        if self._busy:
            self.status_var.set("已有操作进行中，请稍候…")
            return
        if not messagebox.askyesno(
            "重载输入法",
            "结束并重启微软拼音宿主进程，让它重新读取用户词库。\n\n"
            "· 不用注销、不用重启电脑，进程由系统自动拉起\n"
            "· 输入法候选条会闪断一下，正在打字的内容不受影响\n\n现在执行？",
        ):
            return
        self._run_async(app_core.reload_ime, "重载输入法")

    def _import_flow(self, paths: List[str], mode: str, latin: bool, title: str, then=None):
        """读取文档 → 抽词 → 预览确认 → 写入。then：整条流程结束后（含取消/无词条）再执行。"""
        if self._busy:
            return

        def work():
            from document_loader import load_many
            from term_extractor import extract
            docs, errors = load_many(paths)
            terms: List[str] = []
            seen = set()
            for d in docs:
                res = extract(d.text, mode=mode, include_latin=latin)
                for t in res.get("terms") or []:
                    if t not in seen:
                        seen.add(t)
                        terms.append(t)
            desc = "；".join(os.path.basename(d.path) for d in docs[:4])
            if len(docs) > 4:
                desc += f" 等 {len(docs)} 个文件"
            if errors:
                desc += "\n" + "\n".join(errors)
            return terms, desc

        self.set_busy(True, "正在读取文档…")

        def stage1():
            try:
                terms, desc = work()
            except Exception as e:
                self.after(0, lambda: self._fail_busy(str(e)))
                return

            def stage2():
                self.set_busy(False)
                if not terms:
                    messagebox.showwarning("没有词条", "未能从文件抽出有效词条。可试试「一行一个术语」模式。")
                    self.refresh_status()
                    if then:
                        then()
                    return
                picked = self._confirm_preview(terms, desc)
                if picked is None:
                    self.append_log("已取消导入")
                    if then:
                        then()
                    return
                if not picked:
                    self.append_log("预览确认：候选都已在词库中，无词条可写")
                    if then:
                        then()
                    return
                self._run_async(
                    lambda: app_core.apply_tokens(picked, source_desc=desc),
                    title,
                    on_done=(lambda _r: then()) if then else None,
                )

            self.after(0, stage2)

        threading.Thread(target=stage1, daemon=True).start()

    def _fail_busy(self, err: str):
        self.set_busy(False)
        self.append_log(f"✗ {err}")
        messagebox.showerror("出错了", err)
        self.refresh_status()

    def on_paste(self):
        if self._busy:
            self.status_var.set("已有操作进行中，请稍候…")
            return
        win = tk.Toplevel(self)
        win.title("粘贴文本")
        win.configure(bg=BG)
        win.geometry("680x480")
        win.transient(self)
        win.grab_set()
        ttk.Label(win, text="粘贴术语表或正文，关闭前点「预览导入」", style="TLabel").pack(anchor="w", padx=14, pady=10)
        text = tk.Text(win, wrap="word", font=("Microsoft YaHei UI", 11), height=16)
        text.pack(fill="both", expand=True, padx=14, pady=4)
        text.insert("1.0", "产品经理\n需求评审\n技术方案\n发版窗口\n")
        win.bind("<Escape>", lambda _e: win.destroy())

        def do():
            content = text.get("1.0", "end")
            win.destroy()
            mode = self._mode_id()
            latin = self.latin_var.get()
            self.set_busy(True, "正在抽取粘贴文本…")

            def stage1():
                # 抽取是纯 CPU 操作，放 worker 线程，长文不再冻住界面
                try:
                    from term_extractor import extract
                    res = extract(content, mode=mode, include_latin=latin)
                    terms = res.get("terms") or []
                except Exception as e:
                    self.after(0, lambda: self._fail_busy(str(e)))
                    return

                def stage2():
                    self.set_busy(False)
                    if not terms:
                        messagebox.showwarning("没有词条", "未能抽出有效词条")
                        self.refresh_status()
                        return
                    picked = self._confirm_preview(terms, f"粘贴文本 mode={mode}")
                    if picked is None:
                        self.append_log("已取消导入")
                        return
                    if not picked:
                        self.append_log("预览确认：候选都已在词库中，无词条可写")
                        return
                    self._run_async(
                        lambda: app_core.apply_tokens(picked, source_desc=f"粘贴文本 mode={mode}"),
                        "导入文本",
                    )

                self.after(0, stage2)

            threading.Thread(target=stage1, daemon=True).start()

        self._btn(win, "预览导入", do, primary=True, register=False).pack(pady=10)

    def on_add_words(self):
        if self._busy:
            self.status_var.set("已有操作进行中，请稍候…")
            return
        win = tk.Toplevel(self)
        win.title("添加词条")
        win.configure(bg=BG)
        win.geometry("480x320")
        win.transient(self)
        win.grab_set()
        ttk.Label(win, text="一行一个词条（2–12 字）", style="TLabel").pack(anchor="w", padx=14, pady=10)
        text = tk.Text(win, height=10, font=("Microsoft YaHei UI", 11))
        text.pack(fill="both", expand=True, padx=14, pady=4)
        win.bind("<Escape>", lambda _e: win.destroy())

        def do():
            raw = text.get("1.0", "end")
            win.destroy()
            words = [ln.strip() for ln in raw.splitlines() if ln.strip()]
            self._run_async(lambda: app_core.add_words(words), "添加词条")

        self._btn(win, "写入", do, primary=True, register=False).pack(pady=10)

    def on_view(self):
        win = tk.Toplevel(self)
        win.title("浏览词库")
        win.configure(bg=BG)
        win.geometry("820x580")
        win.minsize(720, 480)
        win.transient(self)

        state = {"page": 0, "page_size": 80, "parts": {}}

        top = ttk.Frame(win)
        top.pack(fill="x", padx=12, pady=(10, 4))
        ttk.Label(top, text="搜索：").pack(side="left")
        kw = tk.Entry(top, font=("Microsoft YaHei UI", 11), width=28)
        kw.pack(side="left", padx=6)
        ttk.Label(
            top,
            text="可输入：明月 / mingyue / ming yue / my　　多选：点一条，Shift 连选、Ctrl 加选",
            style="Sub.TLabel",
        ).pack(side="left", padx=8)

        prow = ttk.Frame(win)
        prow.pack(fill="x", padx=12, pady=(0, 4))
        ttk.Label(prow, text="分区：").pack(side="left")
        ALL_PARTS = app_core.PARTITION_ALL_NAME  # 后端同拒此保留名，两处不会漂移
        part_cb = ttk.Combobox(prow, state="readonly", width=52, values=[ALL_PARTS])
        part_cb.pack(side="left", padx=6)
        part_cb.set(ALL_PARTS)
        self._btn(prow, "选中存入分区…",
                  lambda: self._store_partition(tree, part_cb, win, reload_parts, on_part_select),
                  False, register=False).pack(side="left", padx=(6, 0))
        self._btn(prow, "分区清除", lambda: clear_partition(win, part_cb),
                  False, register=False).pack(side="left", padx=(6, 0))
        ttk.Label(prow, text="清除=删除该分区记录的词条（自动先备份）", style="Sub.TLabel").pack(side="left", padx=8)

        mid = ttk.Frame(win)
        mid.pack(fill="both", expand=True, padx=12, pady=4)
        tree = ttk.Treeview(
            mid,
            columns=("no", "word", "pinyin", "jianpin"),
            show="headings",
            height=16,
            selectmode="extended",
        )
        tree.heading("no", text="#")
        tree.heading("word", text="词条")
        tree.heading("pinyin", text="拼音")
        tree.heading("jianpin", text="简拼")
        tree.column("no", width=56, anchor="e")
        tree.column("word", width=220)
        tree.column("pinyin", width=360)
        tree.column("jianpin", width=70, anchor="center")
        vsb = ttk.Scrollbar(mid, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        bottom = ttk.Frame(win)
        bottom.pack(fill="x", padx=12, pady=(2, 8))
        info = ttk.Label(bottom, text="", style="Sub.TLabel")
        info.pack(side="left")

        def reload_parts(keep_selection: bool = True):
            try:
                state["parts"] = {p["name"]: p for p in app_core.list_partitions()}
            except Exception as e:
                messagebox.showerror("错误", f"读取分区失败：{e}", parent=win)
                return
            cur = part_cb.get() if keep_selection else ALL_PARTS
            names = [ALL_PARTS] + list(state["parts"].keys())
            part_cb["values"] = names
            part_cb.set(cur if cur in names else ALL_PARTS)

        def refresh():
            tree.delete(*tree.get_children())
            pname = part_cb.get()
            part = state["parts"].get(pname)
            try:
                r = app_core.query_entries(
                    keyword=kw.get().strip(),
                    page=state["page"],
                    page_size=state["page_size"],
                    only_words=part["words"] if part else None,
                )
            except Exception as e:
                messagebox.showerror("错误", str(e), parent=win)
                return
            state["page"] = r["page"]
            for i, e in enumerate(r["items"]):
                abs_i = r["page"] * r["page_size"] + i + 1
                tree.insert(
                    "",
                    "end",
                    values=(abs_i, e.word, " ".join(e.pinyin), e.jianpin_str.strip()),
                )
            dist = r["stats"].get("length_dist") or {}
            dist_s = " ".join(f"{k}字:{v}" for k, v in sorted(dist.items()))
            info.configure(
                text=(
                    f"词库 {r['total_all']} 条"
                    + (f"｜分区「{pname}」{r['total']} 条" if part else "")
                    + (f"｜筛选 {r['total']} 条" if (r["keyword"] and not part) else "")
                    + f"｜第 {r['page']+1}/{r['pages']} 页"
                    + (f"｜{dist_s}" if dist_s else "")
                )
            )

        def go_page(delta):
            state["page"] = max(0, state["page"] + delta)
            refresh()

        def do_search(*_):
            state["page"] = 0
            refresh()

        def on_part_select(*_):
            state["page"] = 0
            refresh()

        part_cb.bind("<<ComboboxSelected>>", on_part_select)

        def clear_partition(_win, _cb):
            pname = _cb.get()
            part = state["parts"].get(pname)
            if not part:
                messagebox.showinfo("提示", "请先在「分区」下拉里选中一个分区，再做分区清除。", parent=_win)
                return
            n = len(part["words"])
            extra = (
                "\n注意：这是导入批次自动分区，清除后该批的导入历史一并移除，\n"
                "「撤销上次导入」将指向更早的批次。"
                if part["kind"] == "auto" else ""
            )
            ok = messagebox.askyesno(
                "确认分区清除",
                f"清除分区「{pname}」？\n\n"
                f"该分区记录 {n} 条词条，会先自动备份词库，再把其中仍在词库的词条删掉，\n"
                "并移除这条分区记录。其它词、其它分区不受影响。\n\n"
                "（词库文件本体不会清空，只删这批词。）" + extra,
                parent=_win,
            )
            if not ok:
                return

            def work():
                return app_core.remove_partition(pname, delete_words=True)

            def after_done(_r):
                reload_parts()
                refresh()
                self.refresh_status()

            self._run_async(work, "分区清除", on_done=after_done)

        reload_parts(keep_selection=False)

        def do_delete():
            sel = tree.selection()
            if not sel:
                messagebox.showinfo("提示", "请先选中要删除的词条", parent=win)
                return
            words = [tree.item(i, "values")[1] for i in sel]
            if not messagebox.askyesno(
                "确认", f"删除 {len(words)} 条？会先自动备份。", parent=win
            ):
                return

            def work():
                return app_core.delete_entries(words)

            def after_done(_r):
                # 删除真正写完后才刷新，避免固定延时和写入竞速
                try:
                    refresh()
                except Exception:
                    pass
                self.refresh_status()

            self._run_async(work, "删除词条", on_done=after_done)

        def do_export_txt():
            from tkinter import filedialog
            dest = filedialog.asksaveasfilename(
                parent=win,
                title="导出当前筛选结果",
                defaultextension=".txt",
                initialfile="词库清单.txt",
                filetypes=[("文本", "*.txt"), ("CSV", "*.csv"), ("所有文件", "*.*")],
            )
            if not dest:
                return
            try:
                pname = part_cb.get()
                part = state["parts"].get(pname)
                r = app_core.query_entries(
                    keyword=kw.get().strip(), page=0, page_size=10**9,
                    only_words=part["words"] if part else None,
                )
                items = r["items"]
                if dest.lower().endswith(".csv"):
                    with open(dest, "w", encoding="utf-8-sig", newline="") as f:
                        w = csv.writer(f)
                        w.writerow(["词条", "拼音", "简拼"])
                        for e in items:
                            w.writerow([e.word, " ".join(e.pinyin), e.jianpin_str.strip()])
                else:
                    with open(dest, "w", encoding="utf-8") as f:
                        for e in items:
                            f.write(f"{e.word}\t{' '.join(e.pinyin)}\n")
                messagebox.showinfo("已导出", f"{len(items)} 条\n{dest}", parent=win)
            except Exception as e:
                messagebox.showerror("导出失败", str(e), parent=win)

        btns = ttk.Frame(win)
        btns.pack(fill="x", padx=12, pady=(0, 10))
        tk.Button(
            btns, text="搜索", command=do_search, bg=PANEL, relief="groove",
            font=("Microsoft YaHei UI", 10), padx=10, pady=4, cursor="hand2",
        ).pack(side="left")
        kw.bind("<Return>", do_search)
        tk.Button(
            btns, text="上一页", command=lambda: go_page(-1), bg=PANEL, relief="groove",
            font=("Microsoft YaHei UI", 10), padx=10, pady=4, cursor="hand2",
        ).pack(side="left", padx=6)
        tk.Button(
            btns, text="下一页", command=lambda: go_page(1), bg=PANEL, relief="groove",
            font=("Microsoft YaHei UI", 10), padx=10, pady=4, cursor="hand2",
        ).pack(side="left")
        tk.Button(
            btns, text="导出清单…", command=do_export_txt, bg=PANEL, relief="groove",
            font=("Microsoft YaHei UI", 10), padx=10, pady=4, cursor="hand2",
        ).pack(side="left", padx=6)
        tk.Button(
            btns, text="改拼音", command=lambda: self._edit_pinyin_dialog(tree, win, refresh),
            bg=PANEL, relief="groove",
            font=("Microsoft YaHei UI", 10), padx=10, pady=4, cursor="hand2",
        ).pack(side="left")
        tk.Button(
            btns, text="删除选中", command=do_delete, bg="#F5D6D6", relief="groove",
            font=("Microsoft YaHei UI", 10), padx=10, pady=4, cursor="hand2",
        ).pack(side="right")
        tk.Button(
            btns, text="刷新", command=refresh, bg=PANEL, relief="groove",
            font=("Microsoft YaHei UI", 10), padx=10, pady=4, cursor="hand2",
        ).pack(side="right", padx=6)

        refresh()

    def _edit_pinyin_dialog(self, tree, parent_win, refresh):
        sel = tree.selection()
        if len(sel) != 1:
            messagebox.showinfo("提示", "请先选中一条词条（一次只改一条）", parent=parent_win)
            return
        values = tree.item(sel[0], "values")
        word = values[1]
        current = values[2] if len(values) > 2 else ""

        win = tk.Toplevel(parent_win)
        win.title(f"修改拼音：{word}")
        win.configure(bg=BG)
        win.geometry("440x210")
        win.transient(parent_win)
        win.grab_set()
        ttk.Label(win, text=f"词条「{word}」", style="TLabel").pack(anchor="w", padx=14, pady=(12, 2))
        ttk.Label(
            win,
            text="按字给音节，空格分隔。不够的字留空，该字不参与拼音联想。",
            style="Sub.TLabel",
        ).pack(anchor="w", padx=14)
        entry = tk.Entry(win, font=("Microsoft YaHei UI", 12), width=34)
        entry.pack(fill="x", padx=14, pady=8)
        entry.insert(0, " ".join(current.split()))
        entry.focus_set()

        def do_ok(*_):
            val = entry.get().strip()
            win.destroy()
            self._run_async(
                lambda: app_core.update_entry_pinyin(word, val),
                "修改拼音",
                on_done=lambda _r: refresh(),
            )

        win.bind("<Return>", do_ok)
        win.bind("<Escape>", lambda _e: win.destroy())
        self._btn(win, "保存", do_ok, primary=True, register=False).pack(pady=6)

    def _store_partition(self, tree, part_cb, parent_win, reload_parts, refresh):
        if self._busy:
            self.status_var.set("已有操作进行中，请稍候…")
            return
        sel = tree.selection()
        if not sel:
            messagebox.showinfo(
                "提示", "先在列表里选中词条（点一条，Shift 连选、Ctrl 加选），再存入分区。",
                parent=parent_win,
            )
            return
        words = [tree.item(i, "values")[1] for i in sel]
        name = simpledialog.askstring(
            "存入分区", f"把选中的 {len(words)} 条词条存入分区（重名则合并）：",
            parent=parent_win,
        )
        if not name:
            return
        r = app_core.create_partition(name, words)
        if not r.ok:
            messagebox.showwarning("分区", r.message, parent=parent_win)
            return
        reload_parts()
        final = r.data.get("name") or name
        if final in part_cb["values"]:
            part_cb.set(final)
        # 程序化 set() 不触发 <<ComboboxSelected>>，切视图回调必须显式刷新
        refresh()
        self.append_log(f"✓ {r.message}")
        messagebox.showinfo("分区", r.message, parent=parent_win)

    def on_backup(self):
        def work():
            path = app_core.backup_udl("manual")
            if not path:
                return app_core.OperationResult(False, "还没有词库文件可备份")
            return app_core.OperationResult(True, "备份完成", detail=path)
        self._run_async(work, "备份")

    def on_restore(self):
        backups = app_core.list_backups()
        if not backups:
            messagebox.showinfo("提示", "还没有备份。导入前会自动创建。")
            return
        win = tk.Toplevel(self)
        win.title("恢复备份")
        win.configure(bg=BG)
        win.geometry("680x400")
        win.transient(self)
        win.grab_set()
        ttk.Label(win, text="选择备份（会先备份当前词库）", style="TLabel").pack(anchor="w", padx=14, pady=10)
        lb = tk.Listbox(win, font=("Consolas", 10), height=12)
        lb.pack(fill="both", expand=True, padx=14, pady=4)
        for b in backups:
            lb.insert("end", b)
        win.bind("<Escape>", lambda _e: win.destroy())

        def do():
            sel = lb.curselection()
            if not sel:
                messagebox.showinfo("提示", "请选中一条", parent=win)
                return
            path = backups[sel[0]]
            if not messagebox.askyesno("确认", f"用备份覆盖当前词库？\n{path}", parent=win):
                return
            win.destroy()
            self._run_async(lambda: app_core.restore_backup(path), "恢复")

        self._btn(win, "恢复", do, primary=True, register=False).pack(pady=10)

    def on_export(self):
        dest = filedialog.asksaveasfilename(
            parent=self, title="导出词库包",
            defaultextension=".json", initialfile="OpenIME_词库包.json",
            filetypes=[("JSON", "*.json")],
        )
        if not dest:
            return
        self._run_async(lambda: app_core.export_pack(dest), "导出")

    def _import_packs_flow(self, packs: List[str]):
        merge = messagebox.askyesno(
            "导入方式",
            "是否合并到现有词库？\n\n是 = 合并（推荐）\n否 = 替换现有全部词条",
            parent=self,
        )
        self._run_async(lambda: self._import_packs(packs, merge), "导入词库包")

    def _import_packs(self, packs: List[str], merge: bool) -> app_core.OperationResult:
        ok = True
        lines: List[str] = []
        for p in packs:
            r = app_core.import_pack(p, merge=merge)
            ok = ok and r.ok
            lines.append(f"{os.path.basename(p)}：{r.message}" + (f"\n{r.detail}" if r.detail else ""))
        return app_core.OperationResult(
            ok,
            f"已处理 {len(packs)} 个词库包" + ("" if ok else "（部分失败，见详情）"),
            detail="\n\n".join(lines),
        )

    def on_import_pack(self):
        p = filedialog.askopenfilename(
            parent=self, title="导入词库包",
            filetypes=[("JSON", "*.json"), ("所有文件", "*.*")],
        )
        if not p:
            return
        self._import_packs_flow([p])

    def on_history(self):
        recs = app_core.list_history()
        win = tk.Toplevel(self)
        win.title("操作历史")
        win.configure(bg=BG)
        win.geometry("720x420")
        win.minsize(620, 360)
        win.transient(self)
        win.grab_set()
        ttk.Label(
            win,
            text="最近 200 条写入记录（新的在前）。「撤销上次导入」只删最近一次导入新增的词。",
            style="Sub.TLabel",
        ).pack(anchor="w", padx=14, pady=(10, 4))

        mid = ttk.Frame(win)
        mid.pack(fill="both", expand=True, padx=12, pady=4)
        tree = ttk.Treeview(
            mid, columns=("time", "action", "what", "source"), show="headings", height=14,
        )
        tree.heading("time", text="时间")
        tree.heading("action", text="操作")
        tree.heading("what", text="内容")
        tree.heading("source", text="来源")
        tree.column("time", width=145)
        tree.column("action", width=70, anchor="center")
        tree.column("what", width=270)
        tree.column("source", width=185)
        vsb = ttk.Scrollbar(mid, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        action_names = {"import": "导入", "delete": "删除", "replace": "替换", "edit": "改拼音", "restore": "恢复"}

        def fill():
            tree.delete(*tree.get_children())
            for rec in recs:
                action = rec.get("action", "?")
                if action == "import":
                    words = rec.get("added") or []
                    what = f"+{len(words)} 条 " + "、".join(words[:3]) + ("…" if len(words) > 3 else "")
                elif action == "delete":
                    words = rec.get("removed") or []
                    what = f"-{len(words)} 条 " + "、".join(words[:3]) + ("…" if len(words) > 3 else "")
                elif action == "replace":
                    words = rec.get("added") or []
                    what = f"替换为 {len(words)} 条"
                else:
                    what = ""
                src_lines = (rec.get("source") or "").splitlines()
                src = src_lines[0] if src_lines else ""
                tree.insert(
                    "", "end",
                    values=(rec.get("time", "?"), action_names.get(action, action), what, src),
                )

        def do_refresh():
            nonlocal recs
            recs = app_core.list_history()
            fill()

        win.bind("<Escape>", lambda _e: win.destroy())
        bottom = ttk.Frame(win)
        bottom.pack(fill="x", padx=12, pady=(0, 10))
        self._btn(bottom, "刷新", do_refresh, primary=False, register=False).pack(side="left")
        self._btn(bottom, "关闭", win.destroy, primary=False, register=False).pack(side="right")
        fill()


def run_gui():
    app_core.ensure_ready()
    App().mainloop()


if __name__ == "__main__":
    run_gui()
