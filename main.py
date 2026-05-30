"""
ハローワーク 求人情報収集ツール - メインGUIアプリケーション
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import os
import queue
import logging
from datetime import datetime
from typing import Optional

from scraper import HelloWorkScraper, PREFECTURE_CODES, EMP_TYPE_CODES
from exporter import ExcelExporter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

APP_TITLE = "ハローワーク 求人情報収集ツール"
APP_BG    = "#003087"
APP_FG    = "#FFFFFF"
BTN_GREEN = "#217346"
BTN_RED   = "#C0392B"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1000x720")
        self.minsize(880, 600)
        self.resizable(True, True)

        self._results = []
        self._scraper: Optional[HelloWorkScraper] = None
        self._thread: Optional[threading.Thread] = None
        self._log_queue: queue.Queue = queue.Queue()
        self._max_total = 100

        self._build_ui()
        self._poll_log()

    def _build_ui(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TLabel", font=("Meiryo UI", 10))
        style.configure("TButton", font=("Meiryo UI", 10))
        style.configure("TLabelframe.Label", font=("Meiryo UI", 10, "bold"))
        style.configure("Green.TButton", background=BTN_GREEN, foreground="white",
                         font=("Meiryo UI", 11, "bold"))
        style.map("Green.TButton", background=[("active", "#1a5c38")])
        style.configure("Red.TButton", background=BTN_RED, foreground="white",
                         font=("Meiryo UI", 11, "bold"))
        style.map("Red.TButton", background=[("active", "#962d22")])

        hdr = tk.Frame(self, bg=APP_BG, pady=8)
        hdr.pack(fill="x")
        tk.Label(hdr, text=APP_TITLE, bg=APP_BG, fg=APP_FG,
                 font=("Meiryo UI", 16, "bold")).pack()

        body = ttk.Frame(self, padding=10)
        body.pack(fill="both", expand=True)

        self._build_left(body)
        self._build_right(body)

        foot = ttk.Frame(self, padding=(10, 4))
        foot.pack(fill="x")
        self._prog_var = tk.DoubleVar()
        self._prog_label = tk.StringVar(value="待機中")
        ttk.Label(foot, textvariable=self._prog_label).pack(side="left")
        self._prog = ttk.Progressbar(foot, variable=self._prog_var, maximum=100, length=600)
        self._prog.pack(side="right", fill="x", expand=True)

    def _build_left(self, parent):
        left = ttk.LabelFrame(parent, text="検索条件・操作", padding=12, width=280)
        left.pack(side="left", fill="y", padx=(0, 8))
        left.pack_propagate(False)

        r = 0

        def row_label(text):
            nonlocal r
            ttk.Label(left, text=text).grid(row=r, column=0, sticky="w", pady=4)

        row_label("都道府県")
        self._pref_var = tk.StringVar(value="指定なし")
        ttk.Combobox(left, textvariable=self._pref_var,
                     values=list(PREFECTURE_CODES.keys()), width=18,
                     state="readonly").grid(row=r, column=1, sticky="w", pady=4)
        r += 1

        row_label("キーワード")
        self._kw_var = tk.StringVar()
        ttk.Entry(left, textvariable=self._kw_var, width=20).grid(
            row=r, column=1, sticky="w", pady=4)
        r += 1

        row_label("雇用形態")
        self._emp_var = tk.StringVar(value="指定なし")
        ttk.Combobox(left, textvariable=self._emp_var,
                     values=list(EMP_TYPE_CODES.keys()), width=18,
                     state="readonly").grid(row=r, column=1, sticky="w", pady=4)
        r += 1

        row_label("最大取得件数")
        self._max_var = tk.StringVar(value="100")
        ttk.Entry(left, textvariable=self._max_var, width=10).grid(
            row=r, column=1, sticky="w", pady=4)
        r += 1

        row_label("リクエスト間隔(秒)")
        self._delay_var = tk.StringVar(value="2.0")
        ttk.Entry(left, textvariable=self._delay_var, width=10).grid(
            row=r, column=1, sticky="w", pady=4)
        r += 1

        row_label("保存先フォルダ")
        default_dir = os.path.expanduser("~/Desktop")
        self._dir_var = tk.StringVar(value=default_dir)
        dir_frame = ttk.Frame(left)
        dir_frame.grid(row=r, column=1, sticky="w", pady=4)
        ttk.Entry(dir_frame, textvariable=self._dir_var, width=14).pack(side="left")
        ttk.Button(dir_frame, text="…", width=3,
                   command=self._browse_dir).pack(side="left", padx=2)
        r += 1

        ttk.Separator(left, orient="horizontal").grid(
            row=r, column=0, columnspan=2, sticky="ew", pady=10)
        r += 1

        self._btn_start = ttk.Button(left, text="▶  収集開始", style="Green.TButton",
                                     command=self._start)
        self._btn_start.grid(row=r, column=0, columnspan=2, sticky="ew", pady=4)
        r += 1

        self._btn_stop = ttk.Button(left, text="■  停  止", style="Red.TButton",
                                    command=self._stop, state="disabled")
        self._btn_stop.grid(row=r, column=0, columnspan=2, sticky="ew", pady=4)
        r += 1

        self._btn_export = ttk.Button(left, text="Excelエクスポート",
                                      command=self._export, state="disabled")
        self._btn_export.grid(row=r, column=0, columnspan=2, sticky="ew", pady=4)
        r += 1

        ttk.Separator(left, orient="horizontal").grid(
            row=r, column=0, columnspan=2, sticky="ew", pady=10)
        r += 1
        self._cnt_var = tk.StringVar(value="取得件数:  0 件")
        ttk.Label(left, textvariable=self._cnt_var,
                  font=("Meiryo UI", 13, "bold")).grid(
            row=r, column=0, columnspan=2, pady=4)
        r += 1

        self._status_var = tk.StringVar(value="待機中")
        ttk.Label(left, textvariable=self._status_var,
                  wraplength=240, foreground="#555555").grid(
            row=r, column=0, columnspan=2, pady=4)

    def _build_right(self, parent):
        right = ttk.LabelFrame(parent, text="実行ログ", padding=8)
        right.pack(side="right", fill="both", expand=True)

        self._log_text = tk.Text(right, wrap="word", font=("Courier New", 9),
                                  bg="#1e1e1e", fg="#d4d4d4",
                                  insertbackground="white")
        sb = ttk.Scrollbar(right, orient="vertical", command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=sb.set)
        self._log_text.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self._log_text.tag_config("error", foreground="#f48771")
        self._log_text.tag_config("ok",    foreground="#4ec9b0")
        self._log_text.tag_config("info",  foreground="#d4d4d4")

    def _browse_dir(self):
        d = filedialog.askdirectory(title="保存先フォルダを選択")
        if d:
            self._dir_var.set(d)

    def _start(self):
        try:
            max_cnt = int(self._max_var.get())
            delay   = float(self._delay_var.get())
            if max_cnt <= 0 or delay < 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("入力エラー", "最大取得件数と間隔に正しい数値を入力してください。")
            return

        self._max_total = max_cnt
        self._results   = []
        self._prog_var.set(0)
        self._cnt_var.set("取得件数:  0 件")
        self._status_var.set("収集中...")
        self._btn_start.config(state="disabled")
        self._btn_stop.config(state="normal")
        self._btn_export.config(state="disabled")
        self._log_clear()

        self._scraper = HelloWorkScraper(delay=delay)
        self._scraper.stop_flag = False

        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def _stop(self):
        if self._scraper:
            self._scraper.stop_flag = True
        self._log_put("--- 停止リクエスト送信 ---", "error")
        self._status_var.set("停止中...")

    def _worker(self):
        def on_progress(n):
            pct = min((n / self._max_total) * 100, 100)
            self._prog_var.set(pct)
            self._prog_label.set(f"{n} / {self._max_total} 件")
            self._cnt_var.set(f"取得件数:  {n} 件")

        def on_log(msg):
            tag = "error" if "[ERROR]" in msg else "ok" if "取得:" in msg else "info"
            self._log_put(msg, tag)

        try:
            self._results = self._scraper.search(
                keyword=self._kw_var.get(),
                prefecture=self._pref_var.get(),
                emp_type=self._emp_var.get(),
                max_count=self._max_total,
                progress_callback=on_progress,
                log_callback=on_log,
            )
            self.after(0, self._done, True)
        except Exception as exc:
            self._log_put(f"[ERROR] {exc}", "error")
            self.after(0, self._done, False)

    def _done(self, success: bool):
        self._btn_start.config(state="normal")
        self._btn_stop.config(state="disabled")
        n = len(self._results)
        self._cnt_var.set(f"取得件数:  {n} 件")
        self._prog_label.set(f"完了: {n} 件")
        if n:
            self._btn_export.config(state="normal")
            self._status_var.set(f"収集完了 ({n} 件)")
        else:
            self._status_var.set("収集完了 (データなし)")

    def _export(self):
        if not self._results:
            messagebox.showwarning("警告", "エクスポートするデータがありません。")
            return
        save_dir = self._dir_var.get()
        os.makedirs(save_dir, exist_ok=True)
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(save_dir, f"ハローワーク求人情報_{ts}.xlsx")
        try:
            ExcelExporter().export(self._results, path)
            self._log_put(f"Excel保存完了: {path}", "ok")
            messagebox.showinfo("保存完了", f"Excelファイルを保存しました。\n\n{path}")
        except Exception as exc:
            self._log_put(f"[ERROR] エクスポート失敗: {exc}", "error")
            messagebox.showerror("エラー", f"エクスポートに失敗しました。\n\n{exc}")

    def _log_put(self, msg: str, tag: str = "info"):
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_queue.put((f"[{ts}] {msg}\n", tag))

    def _log_clear(self):
        self._log_text.config(state="normal")
        self._log_text.delete("1.0", "end")
        self._log_text.config(state="disabled")

    def _poll_log(self):
        self._log_text.config(state="normal")
        while True:
            try:
                msg, tag = self._log_queue.get_nowait()
                self._log_text.insert("end", msg, tag)
                self._log_text.see("end")
            except queue.Empty:
                break
        self._log_text.config(state="disabled")
        self.after(150, self._poll_log)


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
