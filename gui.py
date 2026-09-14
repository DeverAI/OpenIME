"""
OpenIME · 微软拼音词库管家（通用垂域适配）

把任意文档/词表写入微软拼音用户词库；导入前预览；自动备份。
"""

from __future__ import annotations

import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import List, Optional

import app_core
from paths import user_data_dir


BG = "#F3F1EC"
PANEL = "#FBFAF7"
INK = "#222222"
MUTED = "#666666"
ACCENT = "#1F4E79"
BTN_BG = "#1F4E79"
BTN_FG = "#FFFFFF"
BORDER = "#D5D0C6"

FILE_TYPES = [
    ("支持的文档", "*.txt *.md *.csv *.tsv *.log *.pdf *.docx *.json"),
    ("文本", "*.txt *.md *.csv *.tsv *.log"),
    ("PDF", "*.pdf"),
    ("Word", "*.docx"),
    ("所有文件", "*.*"),
]

MODE_LABELS = [
    ("auto", "自动识别（推荐）"),
    ("lines", "一行一个术语 / 顿号列表"),
    ("sentences", "按标点抽短语"),
    ("poetry", "古诗文整句+节奏组（可选）"),
]


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
        self.latin_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            row2, text="同时提取英文术语", variable=self.latin_var,
            bg=PANEL, font=("Microsoft YaHei UI", 10),
        ).pack(side="left", padx=12)

        # 管理区
        box2 = ttk.LabelFrame(self, text=" 管理 ", style="Box.TLabelframe")
        box2.pack(fill="x", padx=18, pady=4)
        row3 = ttk.Frame(box2, style="Card.TFrame")
        row3.pack(fill="x", padx=10, pady=8)
        self._btn(row3, "浏览词库", self.on_view, False).pack(side="left", expand=True, fill="x", padx=(0, 6))
        self._btn(row3, "备份", self.on_backup, False).pack(side="left", expand=True, fill="x", padx=6)
        self._btn(row3, "恢复…", self.on_restore, False).pack(side="left", expand=True, fill="x", padx=6)
        self._btn(row3, "导出词库包", self.on_export, False).pack(side="left", expand=True, fill="x", padx=6)
        self._btn(row3, "导入词库包…", self.on_import_pack, False).pack(side="left", expand=True, fill="x", padx=(6, 0))

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
        self.log = tk.Text(
            lg, wrap="word", bg="#FFFFFF", fg=INK,
            font=("Microsoft YaHei UI", 10), relief="flat", padx=10, pady=8,
        )
        self.log.pack(fill="both", expand=True, padx=8, pady=8)
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

    def _run_async(self, fn, title="完成"):
        if self._busy:
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
                    messagebox.showinfo(title, msg)
                else:
                    self.append_log(f"✗ {result.message}")
                    if result.detail:
                        self.append_log(result.detail)
                    messagebox.showwarning("未能完成", msg)
                self.refresh_status()

            self.after(0, finish)

        threading.Thread(target=work, daemon=True).start()

    def _confirm_preview(self, terms: List[str], source_desc: str) -> Optional[List[str]]:
        preview = app_core.preview_add(terms, source_desc)
        win = tk.Toplevel(self)
        win.title("导入预览")
        win.configure(bg=BG)
        win.geometry("640x480")
        win.transient(self)
        win.grab_set()

        msg = (
            f"{source_desc}\n"
            f"有效候选 {len(terms)} 条 → 新增 {preview.add_count} 条，"
            f"已存在 {len(preview.already)} 条，规则过滤 {len(preview.rejected)} 条。\n"
            f"导入后词库约 {preview.total_after} 条。"
        )
        ttk.Label(win, text="确认导入", style="Title.TLabel").pack(anchor="w", padx=16, pady=(12, 4))
        ttk.Label(win, text=msg, style="TLabel", wraplength=600, justify="left").pack(anchor="w", padx=16)

        box = ttk.Frame(win)
        box.pack(fill="both", expand=True, padx=16, pady=8)
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

        holder = {"ok": False}

        def do_ok():
            holder["ok"] = True
            win.destroy()

        def do_cancel():
            win.destroy()

        btns = ttk.Frame(win)
        btns.pack(pady=10)
        tk.Button(
            btns, text=f"写入 {preview.add_count} 条", command=do_ok,
            bg=BTN_BG, fg=BTN_FG, relief="flat",
            font=("Microsoft YaHei UI", 12, "bold"), padx=16, pady=8, cursor="hand2",
        ).pack(side="left", padx=6)
        tk.Button(
            btns, text="取消", command=do_cancel,
            bg=PANEL, relief="groove", font=("Microsoft YaHei UI", 11), padx=12, pady=8, cursor="hand2",
        ).pack(side="left", padx=6)

        win.wait_window()
        if holder["ok"]:
            return preview.to_add
        return None

    # ---------- actions ----------
    def on_pick_files(self):
        paths = filedialog.askopenfilenames(parent=self, title="选择文档", filetypes=FILE_TYPES)
        if not paths:
            return
        paths = list(paths)
        mode = self._mode_id()
        latin = self.latin_var.get()

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

        def pipeline():
            if self._busy:
                return app_core.OperationResult(False, "忙，请稍候")
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
                        return
                    picked = self._confirm_preview(terms, desc)
                    if not picked:
                        self.append_log("已取消导入")
                        return
                    self._run_async(
                        lambda: app_core.apply_tokens(picked, source_desc=desc),
                        "导入文档",
                    )

                self.after(0, stage2)

            threading.Thread(target=stage1, daemon=True).start()

        pipeline()

    def _fail_busy(self, err: str):
        self.set_busy(False)
        self.append_log(f"✗ {err}")
        messagebox.showerror("出错了", err)
        self.refresh_status()

    def on_paste(self):
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

        def do():
            content = text.get("1.0", "end")
            win.destroy()
            mode = self._mode_id()
            latin = self.latin_var.get()

            def stage():
                from term_extractor import extract
                res = extract(content, mode=mode, include_latin=latin)
                terms = res.get("terms") or []
                return terms, f"粘贴文本 mode={mode}"

            def run():
                try:
                    terms, desc = stage()
                except Exception as e:
                    messagebox.showerror("出错了", str(e))
                    return
                if not terms:
                    messagebox.showwarning("没有词条", "未能抽出有效词条")
                    return
                picked = self._confirm_preview(terms, desc)
                if picked:
                    self._run_async(lambda: app_core.apply_tokens(picked, source_desc=desc), "导入文本")

            self.after(0, run)

        tk.Button(
            win, text="预览导入", command=do, bg=BTN_BG, fg=BTN_FG, relief="flat",
            font=("Microsoft YaHei UI", 12, "bold"), padx=16, pady=8, cursor="hand2",
        ).pack(pady=10)

    def on_add_words(self):
        win = tk.Toplevel(self)
        win.title("添加词条")
        win.configure(bg=BG)
        win.geometry("480x320")
        win.transient(self)
        win.grab_set()
        ttk.Label(win, text="一行一个词条（2–12 字）", style="TLabel").pack(anchor="w", padx=14, pady=10)
        text = tk.Text(win, height=10, font=("Microsoft YaHei UI", 11))
        text.pack(fill="both", expand=True, padx=14, pady=4)

        def do():
            raw = text.get("1.0", "end")
            win.destroy()
            words = [ln.strip() for ln in raw.splitlines() if ln.strip()]
            self._run_async(lambda: app_core.add_words(words), "添加词条")

        tk.Button(
            win, text="写入", command=do, bg=BTN_BG, fg=BTN_FG, relief="flat",
            font=("Microsoft YaHei UI", 12, "bold"), padx=16, pady=8, cursor="hand2",
        ).pack(pady=10)

    def on_view(self):
        win = tk.Toplevel(self)
        win.title("浏览词库")
        win.configure(bg=BG)
        win.geometry("820x580")
        win.minsize(720, 480)
        win.transient(self)

        state = {"page": 0, "page_size": 80}

        top = ttk.Frame(win)
        top.pack(fill="x", padx=12, pady=(10, 4))
        ttk.Label(top, text="搜索：").pack(side="left")
        kw = tk.Entry(top, font=("Microsoft YaHei UI", 11), width=28)
        kw.pack(side="left", padx=6)
        ttk.Label(
            top,
            text="可输入：明月 / mingyue / ming yue / my",
            style="Sub.TLabel",
        ).pack(side="left", padx=8)

        mid = ttk.Frame(win)
        mid.pack(fill="both", expand=True, padx=12, pady=4)
        tree = ttk.Treeview(
            mid,
            columns=("no", "word", "pinyin", "jianpin"),
            show="headings",
            height=16,
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

        def refresh():
            tree.delete(*tree.get_children())
            try:
                r = app_core.query_entries(
                    keyword=kw.get().strip(),
                    page=state["page"],
                    page_size=state["page_size"],
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
                    + (f"｜筛选 {r['total']} 条" if r["keyword"] else "")
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
                r = app_core.delete_entries(words)
                return r

            def after_del():
                # 删除后刷新本窗口
                self.after(300, refresh)
                self.after(400, self.refresh_status)

            self._run_async(work, "删除词条")
            win.after(500, after_del)

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
                r = app_core.query_entries(keyword=kw.get().strip(), page=0, page_size=10**9)
                items = r["items"]
                with open(dest, "w", encoding="utf-8") as f:
                    if dest.lower().endswith(".csv"):
                        f.write("word,pinyin,jianpin\n")
                        for e in items:
                            f.write(
                                f"{e.word},{' '.join(e.pinyin)},{e.jianpin_str.strip()}\n"
                            )
                    else:
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
            btns, text="删除选中", command=do_delete, bg="#F5D6D6", relief="groove",
            font=("Microsoft YaHei UI", 10), padx=10, pady=4, cursor="hand2",
        ).pack(side="right")
        tk.Button(
            btns, text="刷新", command=refresh, bg=PANEL, relief="groove",
            font=("Microsoft YaHei UI", 10), padx=10, pady=4, cursor="hand2",
        ).pack(side="right", padx=6)

        refresh()

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

        tk.Button(
            win, text="恢复", command=do, bg=BTN_BG, fg=BTN_FG, relief="flat",
            font=("Microsoft YaHei UI", 12, "bold"), padx=16, pady=8, cursor="hand2",
        ).pack(pady=10)

    def on_export(self):
        dest = filedialog.asksaveasfilename(
            parent=self, title="导出词库包",
            defaultextension=".json", initialfile="OpenIME_词库包.json",
            filetypes=[("JSON", "*.json")],
        )
        if not dest:
            return
        self._run_async(lambda: app_core.export_pack(dest), "导出")

    def on_import_pack(self):
        p = filedialog.askopenfilename(
            parent=self, title="导入词库包",
            filetypes=[("JSON", "*.json"), ("所有文件", "*.*")],
        )
        if not p:
            return
        merge = messagebox.askyesno(
            "导入方式",
            "是否合并到现有词库？\n\n是 = 合并（推荐）\n否 = 替换现有全部词条",
            parent=self,
        )
        self._run_async(lambda: app_core.import_pack(p, merge=merge), "导入词库包")


def run_gui():
    app_core.ensure_ready()
    App().mainloop()


if __name__ == "__main__":
    run_gui()
