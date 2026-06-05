"""
ハローワーク 求人情報収集ツール - メインGUIアプリケーション (v1.2.0)
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import os
import json
import queue
import logging
from datetime import datetime
from typing import Optional, List, Dict

from scraper import HelloWorkScraper, PREFECTURE_CODES, EMP_TYPE_CODES
from exporter import ExcelExporter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

APP_TITLE   = "ハローワーク 求人情報収集ツール"
APP_BG      = "#003087"
APP_FG      = "#FFFFFF"
BTN_GREEN   = "#217346"
BTN_RED     = "#C0392B"
BTN_ORANGE  = "#D35400"
BTN_BLUE    = "#2980B9"

SEEN_IDS_FILE   = os.path.join(os.path.expanduser("~"), ".hellowork_seen_ids.json")
CHECKPOINT_FILE = os.path.join(os.path.expanduser("~"), ".hellowork_checkpoint.json")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1000x820")
        self.minsize(880, 680)
        self.resizable(True, True)

        self._results: List[Dict] = []
        self._new_ids: set = set()
        self._scraper: Optional[HelloWorkScraper] = None
        self._thread: Optional[threading.Thread] = None
        self._log_queue: queue.Queue = queue.Queue()
        self._max_total = 100
        self._is_resuming = False

        self._build_ui()
        self._poll_log()
        self._check_checkpoint_on_startup()

    # ------------------------------------------------------------------ UI構築
    def _build_ui(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TLabel",         font=("Meiryo UI", 10))
        style.configure("TButton",        font=("Meiryo UI", 10))
        style.configure("TLabelframe.Label", font=("Meiryo UI", 10, "bold"))
        style.configure("Green.TButton",  background=BTN_GREEN,  foreground="white",
                        font=("Meiryo UI", 11, "bold"))
        style.map("Green.TButton",  background=[("active", "#1a5c38")])
        style.configure("Red.TButton",   background=BTN_RED,    foreground="white",
                        font=("Meiryo UI", 11, "bold"))
        style.map("Red.TButton",    background=[("active", "#962d22")])
        style.configure("Orange.TButton", background=BTN_ORANGE, foreground="white",
                        font=("Meiryo UI", 11, "bold"))
        style.map("Orange.TButton", background=[("active", "#a94300")])
        style.configure("Blue.TButton",  background=BTN_BLUE,   foreground="white",
                        font=("Meiryo UI", 10, "bold"))
        style.map("Blue.TButton",   background=[("active", "#1f6391")])

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
        self._prog_var   = tk.DoubleVar()
        self._prog_label = tk.StringVar(value="待機中")
        ttk.Label(foot, textvariable=self._prog_label).pack(side="left")
        self._prog = ttk.Progressbar(foot, variable=self._prog_var, maximum=100, length=600)
        self._prog.pack(side="right", fill="x", expand=True)

    def _build_left(self, parent):
        left = ttk.LabelFrame(parent, text="検索条件・操作", padding=12, width=290)
        left.pack(side="left", fill="y", padx=(0, 8))
        left.pack_propagate(False)

        r = 0

        def row_label(text):
            nonlocal r
            ttk.Label(left, text=text).grid(row=r, column=0, sticky="w", pady=3)

        row_label("都道府県")
        self._pref_var = tk.StringVar(value="指定なし")
        ttk.Combobox(left, textvariable=self._pref_var,
                     values=list(PREFECTURE_CODES.keys()), width=18,
                     state="readonly").grid(row=r, column=1, sticky="w", pady=3)
        r += 1

        row_label("キーワード")
        self._kw_var = tk.StringVar()
        ttk.Entry(left, textvariable=self._kw_var, width=20).grid(
            row=r, column=1, sticky="w", pady=3)
        r += 1

        row_label("雇用形態")
        self._emp_var = tk.StringVar(value="指定なし")
        ttk.Combobox(left, textvariable=self._emp_var,
                     values=list(EMP_TYPE_CODES.keys()), width=18,
                     state="readonly").grid(row=r, column=1, sticky="w", pady=3)
        r += 1

        row_label("最大取得件数")
        self._max_var = tk.StringVar(value="100")
        ttk.Entry(left, textvariable=self._max_var, width=10).grid(
            row=r, column=1, sticky="w", pady=3)
        r += 1

        row_label("リクエスト間隔(秒)")
        self._delay_var = tk.StringVar(value="2.0")
        ttk.Entry(left, textvariable=self._delay_var, width=10).grid(
            row=r, column=1, sticky="w", pady=3)
        r += 1

        row_label("保存先フォルダ")
        default_dir = os.path.expanduser("~/Desktop")
        self._dir_var = tk.StringVar(value=default_dir)
        dir_frame = ttk.Frame(left)
        dir_frame.grid(row=r, column=1, sticky="w", pady=3)
        ttk.Entry(dir_frame, textvariable=self._dir_var, width=14).pack(side="left")
        ttk.Button(dir_frame, text="…", width=3,
                   command=self._browse_dir).pack(side="left", padx=2)
        r += 1

        ttk.Separator(left, orient="horizontal").grid(
            row=r, column=0, columnspan=2, sticky="ew", pady=5)
        r += 1

        # 差分モード
        diff_lf = ttk.LabelFrame(left, text="差分モード", padding=6)
        diff_lf.grid(row=r, column=0, columnspan=2, sticky="ew", pady=3)
        r += 1

        self._diff_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(diff_lf, text="新規求人のみ取得する",
                        variable=self._diff_var).grid(
            row=0, column=0, columnspan=2, sticky="w")

        self._seen_label = tk.StringVar(value=self._get_seen_count_text())
        ttk.Label(diff_lf, textvariable=self._seen_label,
                  foreground="#555555", font=("Meiryo UI", 9)).grid(
            row=1, column=0, sticky="w", pady=2)

        ttk.Button(diff_lf, text="履歴クリア",
                   command=self._clear_history).grid(
            row=1, column=1, sticky="e", padx=(4, 0))

        ttk.Separator(left, orient="horizontal").grid(
            row=r, column=0, columnspan=2, sticky="ew", pady=5)
        r += 1

        # チェックポイント（再開）エリア
        resume_lf = ttk.LabelFrame(left, text="中断からの再開", padding=6)
        resume_lf.grid(row=r, column=0, columnspan=2, sticky="ew", pady=3)
        r += 1

        self._checkpoint_label = tk.StringVar(value="チェックポイント: なし")
        ttk.Label(resume_lf, textvariable=self._checkpoint_label,
                  foreground="#555555", font=("Meiryo UI", 9),
                  wraplength=240).grid(row=0, column=0, columnspan=2, sticky="w", pady=2)

        self._btn_resume = ttk.Button(resume_lf, text="▶ 前回の続きから再開",
                                      style="Blue.TButton",
                                      command=self._start_resume, state="disabled")
        self._btn_resume.grid(row=1, column=0, sticky="ew", pady=2, padx=(0, 2))

        ttk.Button(resume_lf, text="削除",
                   command=self._delete_checkpoint).grid(
            row=1, column=1, sticky="e")

        ttk.Separator(left, orient="horizontal").grid(
            row=r, column=0, columnspan=2, sticky="ew", pady=5)
        r += 1

        # メインボタン群
        self._btn_start = ttk.Button(left, text="▶  収集開始", style="Green.TButton",
                                     command=self._start)
        self._btn_start.grid(row=r, column=0, columnspan=2, sticky="ew", pady=3)
        r += 1

        self._btn_stop = ttk.Button(left, text="■  停  止", style="Red.TButton",
                                    command=self._stop, state="disabled")
        self._btn_stop.grid(row=r, column=0, columnspan=2, sticky="ew", pady=3)
        r += 1

        self._btn_export = ttk.Button(left, text="Excelエクスポート",
                                      command=self._export, state="disabled")
        self._btn_export.grid(row=r, column=0, columnspan=2, sticky="ew", pady=3)
        r += 1

        ttk.Separator(left, orient="horizontal").grid(
            row=r, column=0, columnspan=2, sticky="ew", pady=5)
        r += 1

        self._cnt_var = tk.StringVar(value="取得件数:  0 件")
        ttk.Label(left, textvariable=self._cnt_var,
                  font=("Meiryo UI", 13, "bold")).grid(
            row=r, column=0, columnspan=2, pady=3)
        r += 1

        self._status_var = tk.StringVar(value="待機中")
        ttk.Label(left, textvariable=self._status_var,
                  wraplength=250, foreground="#555555").grid(
            row=r, column=0, columnspan=2, pady=3)

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

        self._log_text.tag_config("error",  foreground="#f48771")
        self._log_text.tag_config("ok",     foreground="#4ec9b0")
        self._log_text.tag_config("info",   foreground="#d4d4d4")
        self._log_text.tag_config("warn",   foreground="#dcdcaa")

    # ------------------------------------------------------------------ 差分管理
    def _get_seen_count_text(self) -> str:
        ids = self._load_seen_ids()
        return f"取得済み履歴: {len(ids)} 件"

    def _load_seen_ids(self) -> set:
        try:
            if os.path.exists(SEEN_IDS_FILE):
                with open(SEEN_IDS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return set(data.get("seen_ids", []))
        except Exception:
            pass
        return set()

    def _save_seen_ids(self, new_ids: set):
        try:
            existing = self._load_seen_ids()
            all_ids = existing | {i for i in new_ids if i}
            with open(SEEN_IDS_FILE, "w", encoding="utf-8") as f:
                json.dump({"seen_ids": list(all_ids)}, f, ensure_ascii=False)
            self._seen_label.set(self._get_seen_count_text())
        except Exception as exc:
            self._log_put(f"[ERROR] 履歴保存失敗: {exc}", "error")

    def _clear_history(self):
        if not messagebox.askyesno(
            "確認",
            "収集履歴をすべて削除しますか？\n次回収集時はすべての求人が「新規」として扱われます。"
        ):
            return
        try:
            if os.path.exists(SEEN_IDS_FILE):
                os.remove(SEEN_IDS_FILE)
            self._seen_label.set(self._get_seen_count_text())
            self._log_put("履歴をクリアしました。", "ok")
        except Exception as exc:
            messagebox.showerror("エラー", f"履歴クリアに失敗しました: {exc}")

    # ------------------------------------------------------------------ チェックポイント
    def _check_checkpoint_on_startup(self):
        self._refresh_checkpoint_ui()

    def _refresh_checkpoint_ui(self):
        cp = self._load_checkpoint()
        if cp:
            n = cp.get("collected_count", 0)
            ts = cp.get("timestamp", "")[:16].replace("T", " ")
            params = cp.get("search_params", {})
            pref = params.get("prefecture", "?")
            kw   = params.get("keyword", "") or "(キーワードなし)"
            self._checkpoint_label.set(
                f"保存あり ({ts})\n{pref} / {kw}\n収集済: {n} 件"
            )
            self._btn_resume.config(state="normal")
        else:
            self._checkpoint_label.set("チェックポイント: なし")
            self._btn_resume.config(state="disabled")

    def _load_checkpoint(self) -> Optional[dict]:
        try:
            if os.path.exists(CHECKPOINT_FILE):
                with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return None

    def _save_checkpoint(self, results: List[Dict], search_params: dict):
        try:
            seen_ids = [r.get("求人番号", "") for r in results]
            data = {
                "version": 1,
                "timestamp": datetime.now().isoformat(),
                "search_params": search_params,
                "collected_count": len(results),
                "seen_job_numbers": [i for i in seen_ids if i],
                "results": results,
            }
            with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            self.after(0, self._refresh_checkpoint_ui)
        except Exception as exc:
            self._log_put(f"[WARN] チェックポイント保存失敗: {exc}", "warn")

    def _delete_checkpoint(self):
        if os.path.exists(CHECKPOINT_FILE):
            if not messagebox.askyesno("確認", "チェックポイントを削除しますか？"):
                return
            try:
                os.remove(CHECKPOINT_FILE)
            except Exception as exc:
                messagebox.showerror("エラー", f"削除失敗: {exc}")
        self._refresh_checkpoint_ui()

    # ------------------------------------------------------------------ Actions
    def _browse_dir(self):
        d = filedialog.askdirectory(title="保存先フォルダを選択")
        if d:
            self._dir_var.set(d)

    def _validate_inputs(self):
        try:
            max_cnt = int(self._max_var.get())
            delay   = float(self._delay_var.get())
            if max_cnt <= 0 or delay < 0:
                raise ValueError
            return max_cnt, delay
        except ValueError:
            messagebox.showerror("入力エラー", "最大取得件数と間隔に正しい数値を入力してください。")
            return None, None

    def _start(self):
        max_cnt, delay = self._validate_inputs()
        if max_cnt is None:
            return

        self._is_resuming = False
        self._max_total = max_cnt
        self._results   = []
        self._new_ids   = set()
        self._start_worker(delay, checkpoint_results=None)

    def _start_resume(self):
        cp = self._load_checkpoint()
        if not cp:
            messagebox.showinfo("情報", "チェックポイントが見つかりません。")
            self._refresh_checkpoint_ui()
            return

        saved_results   = cp.get("results", [])
        seen_job_numbers = set(cp.get("seen_job_numbers", []))
        params          = cp.get("search_params", {})
        remaining       = params.get("max_count", 100) - len(saved_results)

        if remaining <= 0:
            messagebox.showinfo("情報", "前回の収集で目標件数に達しています。\n新規検索を行ってください。")
            return

        # UIに前回パラメータを反映
        self._pref_var.set(params.get("prefecture", "指定なし"))
        self._kw_var.set(params.get("keyword", ""))
        self._emp_var.set(params.get("emp_type", "指定なし"))
        self._max_var.set(str(params.get("max_count", 100)))
        self._delay_var.set(str(params.get("delay", 2.0)))

        self._is_resuming = True
        self._max_total   = params.get("max_count", 100)
        self._results     = list(saved_results)
        self._new_ids     = seen_job_numbers

        n = len(saved_results)
        self._log_put(
            f"前回チェックポイントから再開: 既存 {n} 件 + 追加 {remaining} 件を収集します",
            "ok"
        )

        self._start_worker(
            float(params.get("delay", 2.0)),
            checkpoint_results=saved_results,
            skip_ids=seen_job_numbers,
            effective_max=remaining,
        )

    def _start_worker(
        self,
        delay: float,
        checkpoint_results: Optional[List[Dict]] = None,
        skip_ids: Optional[set] = None,
        effective_max: Optional[int] = None,
    ):
        self._prog_var.set(0)
        self._cnt_var.set(f"取得件数:  {len(self._results)} 件")
        self._status_var.set("収集中...")
        self._btn_start.config(state="disabled")
        self._btn_resume.config(state="disabled")
        self._btn_stop.config(state="normal")
        self._btn_export.config(state="disabled")
        self._log_clear()

        self._scraper = HelloWorkScraper(delay=delay)
        self._scraper.stop_flag = False

        _skip_ids  = skip_ids or set()
        _eff_max   = effective_max if effective_max is not None else self._max_total

        self._thread = threading.Thread(
            target=self._worker,
            args=(_skip_ids, _eff_max, checkpoint_results),
            daemon=True,
        )
        self._thread.start()

    def _stop(self):
        if self._scraper:
            self._scraper.stop_flag = True
        self._log_put("--- 停止リクエスト送信 ---", "error")
        self._status_var.set("停止中...")

    def _worker(self, skip_ids: set, effective_max: int, checkpoint_results: Optional[List[Dict]]):
        base_count = len(self._results)  # 再開時は既存件数

        def on_progress(n):
            total = base_count + n
            pct = min((total / self._max_total) * 100, 100)
            self._prog_var.set(pct)
            self._prog_label.set(f"{total} / {self._max_total} 件")
            self._cnt_var.set(f"取得件数:  {total} 件")

        def on_log(msg):
            tag = "error" if "[ERROR]" in msg else \
                  "warn"  if "[WARN]"  in msg else \
                  "ok"    if "取得:"  in msg else "info"
            self._log_put(msg, tag)

        search_params = {
            "keyword":    self._kw_var.get(),
            "prefecture": self._pref_var.get(),
            "emp_type":   self._emp_var.get(),
            "max_count":  self._max_total,
            "delay":      float(self._delay_var.get()),
        }

        def on_checkpoint(partial_results):
            merged = list(self._results) + partial_results
            self._save_checkpoint(merged, search_params)
            self._log_put(
                f"  [チェックポイント保存] 計 {len(merged)} 件を保存", "info"
            )

        try:
            new_results = self._scraper.search(
                keyword=search_params["keyword"],
                prefecture=search_params["prefecture"],
                emp_type=search_params["emp_type"],
                max_count=effective_max,
                progress_callback=on_progress,
                log_callback=on_log,
                checkpoint_callback=on_checkpoint,
                skip_ids=skip_ids,
            )

            new_ids = {r.get("求人番号", "") for r in new_results}
            self._new_ids |= new_ids
            self._results.extend(new_results)

            if self._diff_var.get():
                seen = self._load_seen_ids()
                before = len(self._results)
                self._results = [
                    r for r in self._results
                    if r.get("求人番号", "") not in seen
                ]
                skipped = before - len(self._results)
                if skipped:
                    self._log_put(
                        f"差分フィルタ: {skipped} 件は既取得済みのためスキップしました", "info"
                    )

            self.after(0, self._done, True, None)

        except Exception as exc:
            self._log_put(f"[ERROR] {exc}", "error")
            self.after(0, self._done, False, str(exc))

    def _done(self, success: bool, error_msg: Optional[str]):
        self._btn_start.config(state="normal")
        self._btn_stop.config(state="disabled")
        self._refresh_checkpoint_ui()

        n = len(self._results)
        self._cnt_var.set(f"取得件数:  {n} 件")
        self._prog_label.set(f"{'完了' if success else 'エラー停止'}: {n} 件")

        if n > 0:
            self._btn_export.config(state="normal")

        if success:
            diff_note = "（差分）" if self._diff_var.get() else ""
            self._status_var.set(
                f"収集完了{diff_note} ({n} 件)" if n else
                ("収集完了 (新規データなし)" if self._diff_var.get() else "収集完了 (データなし)")
            )
            # 正常完了時はチェックポイントを削除
            if os.path.exists(CHECKPOINT_FILE):
                try:
                    os.remove(CHECKPOINT_FILE)
                except Exception:
                    pass
            self._refresh_checkpoint_ui()
        else:
            if n > 0:
                self._status_var.set(
                    f"エラーにより停止 ({n} 件収集済)\n"
                    "「Excelエクスポート」で収集分を保存できます。\n"
                    "「前回の続きから再開」で続きから収集できます。"
                )
                self._log_put(
                    f"エラーで停止しましたが {n} 件のデータが保存されています。"
                    "エクスポートまたは再開が可能です。", "warn"
                )
            else:
                self._status_var.set("エラーにより停止 (収集データなし)")

        self._save_seen_ids(self._new_ids)

    def _export(self):
        if not self._results:
            messagebox.showwarning("警告", "エクスポートするデータがありません。")
            return
        save_dir = self._dir_var.get()
        os.makedirs(save_dir, exist_ok=True)
        ts     = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = "_差分" if self._diff_var.get() else ""
        if self._is_resuming:
            suffix += "_再開"
        path = os.path.join(save_dir, f"ハローワーク求人情報{suffix}_{ts}.xlsx")
        try:
            ExcelExporter().export(self._results, path)
            self._log_put(f"Excel保存完了: {path}", "ok")
            messagebox.showinfo("保存完了", f"Excelファイルを保存しました。\n\n{path}")
        except Exception as exc:
            self._log_put(f"[ERROR] エクスポート失敗: {exc}", "error")
            messagebox.showerror("エラー", f"エクスポートに失敗しました。\n\n{exc}")

    # ------------------------------------------------------------------ Log
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
