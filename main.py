#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
英语单词默写与复习软件 - VocabMaster

Version: 1.0.0 - Final Production Build
Date: 2026-07-02

功能概览：
- 多词性多释义支持（JSON definitions）
- 动态词书分类管理（增删改词书）
- Leitner 5-Box 抗遗忘复习算法
- 数据看板（分册通关率 + 记忆分布图）
- 本地语音朗读（pyttsx3）
- 一键备份与 CSV 导出
- 单词 / 词书 CRUD 管理
- 全局同步刷新机制
"""

import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
import time
import os
import datetime
import shutil
import json

try:
    import pyttsx3
    _TTS = pyttsx3.init()
except:
    _TTS = None


DB_FILENAME = "vocab_data.db"

# 5 级口袋算法 —— 各级对应的复习间隔天数
BOX_DAYS = {1: 1, 2: 2, 3: 4, 4: 7, 5: 15}


# ================================================================
#  工具函数
# ================================================================

def _db_path():
    """返回数据库文件的绝对路径"""
    try:
        d = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        d = os.getcwd()
    return os.path.join(d, DB_FILENAME)


# ================================================================
#  主应用类
# ================================================================

class VocabApp:
    """英语单词默写与复习应用程序"""

    def __init__(self, root):
        self.root = root
        self.root.title("英语单词默写与复习")
        self.root.geometry("960x640")
        self.root.minsize(560, 480)
        self.root.configure(bg="#F0F2F5")

        # -------------------------------------------------------- #
        #  数据库初始化
        # -------------------------------------------------------- #
        self.db_path = _db_path()
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        self._init_db()

        # -------------------------------------------------------- #
        #  会话状态
        # -------------------------------------------------------- #
        # 新词默写
        self.dict_words = []
        self.dict_idx = 0
        self.dict_correct = 0
        self.dict_answered = False

        # 复习默写
        self.rev_words = []
        self.rev_idx = 0
        self.rev_correct = 0
        self.rev_answered = False

        # -------------------------------------------------------- #
        #  构建界面
        # -------------------------------------------------------- #
        self._setup_style()
        self.dash_frame = None
        self.categories = []
        self._build_ui()

        # 窗口关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------ #
    #  数据库操作
    # ------------------------------------------------------------ #

    def _init_db(self):
        """创建数据库表（如尚未存在）"""
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS words (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                word             TEXT    NOT NULL,
                pos              TEXT    DEFAULT '',
                phonetic         TEXT    DEFAULT '',
                meaning          TEXT    DEFAULT '',
                box_level        INTEGER DEFAULT 1,
                next_review_time INTEGER DEFAULT 0,
                status           INTEGER DEFAULT 0,
                category         TEXT DEFAULT ''
            )
        """)
        self.conn.commit()
        # 兼容旧数据库：添加 category 列（如已存在则跳过）
        try:
            self.cursor.execute("ALTER TABLE words ADD COLUMN category TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass
        try:
            self.cursor.execute("ALTER TABLE words ADD COLUMN definitions TEXT DEFAULT '[]'")
        except sqlite3.OperationalError:
            pass
        # 迁移旧数据：将 pos + meaning 合并为 JSON definitions
        self.cursor.execute("SELECT id, pos, meaning FROM words WHERE definitions IS NULL OR definitions = '[]'")
        for row_id, old_pos, old_meaning in self.cursor.fetchall():
            d = json.dumps([{"pos": old_pos or "", "meaning": old_meaning or ""}])
            self.cursor.execute("UPDATE words SET definitions=? WHERE id=?", (d, row_id))
        self.conn.commit()
        self.cursor.execute(
            '''CREATE TABLE IF NOT EXISTS review_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                word_id     INTEGER NOT NULL,
                review_time INTEGER NOT NULL,
                result      INTEGER NOT NULL,
                FOREIGN KEY (word_id) REFERENCES words(id)
            )'''
        )
        self.conn.commit()
        self.cursor.execute("""CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )""")
        self.conn.commit()

    def _count_words(self, status=None):
        """统计单词数量，status 为 None 时统计全部"""
        if status is None:
            self.cursor.execute("SELECT COUNT(*) FROM words")
        else:
            self.cursor.execute("SELECT COUNT(*) FROM words WHERE status=?", (status,))
        return self.cursor.fetchone()[0]

    # ------------------------------------------------------------ #
    #  窗口关闭
    # ------------------------------------------------------------ #

    def _on_close(self):
        try:
            self.conn.close()
        except Exception:
            pass
        self.root.destroy()

    # ============================================================ #
    #  UI 构建
    # ============================================================ #


    # ------------------------------------------------------------ #
    #  UI 样式
    # ------------------------------------------------------------ #

    def _setup_style(self):
        """配置现代化扁平化 UI 样式"""
        style = ttk.Style()
        style.theme_use("clam")

        # 柔和现代配色
        BG = "#F0F2F5"
        CARD = "#FFFFFF"
        PRI = "#2D3436"
        ACC = "#0984E3"
        SUC = "#00B894"
        DNG = "#D63031"
        TXT = "#2D3436"
        TX2 = "#636E72"

        # Notebook 标签页
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=CARD, foreground=PRI,
                        font=("Segoe UI", 11), padding=[24, 10])
        style.map("TNotebook.Tab", background=[("selected", ACC)],
                  foreground=[("selected", "#FFFFFF")])

        # Frame
        style.configure("TFrame", background=BG)
        style.configure("TLabelframe", background=BG, foreground=PRI,
                        font=("Segoe UI", 10, "bold"))
        style.configure("TLabelframe.Label", background=BG, foreground=ACC)

        # Label
        style.configure("TLabel", background=BG, foreground=TXT, font=("Segoe UI", 10))

        # Button
        style.configure("TButton", background=ACC, foreground="#FFFFFF",
                        font=("Segoe UI", 10, "bold"), padding=[18, 8], borderwidth=0)
        style.map("TButton", background=[("active", "#0773C5"), ("pressed", "#065EA6")])
        style.configure("Accent.TButton", background=SUC)
        style.map("Accent.TButton", background=[("active", "#00A381")])
        style.configure("Danger.TButton", background=DNG)
        style.map("Danger.TButton", background=[("active", "#B22222")])

        # Entry & Combobox
        style.configure("TEntry", fieldbackground=CARD, foreground=TXT,
                        font=("Segoe UI", 11), padding=[8, 6])
        style.configure("TCombobox", fieldbackground=CARD, foreground=TXT,
                        font=("Segoe UI", 11), padding=[8, 6])

        # Treeview
        style.configure("Treeview", background=CARD, foreground=TXT,
                        fieldbackground=CARD, font=("Segoe UI", 10), rowheight=30)
        style.configure("Treeview.Heading", background=PRI, foreground="#FFFFFF",
                        font=("Segoe UI", 10, "bold"))
        style.map("Treeview", background=[("selected", "#74B9FF")])

        # Progressbar
        style.configure("Horizontal.TProgressbar", background=ACC, troughcolor=CARD,
                        borderwidth=0, thickness=8)

        tk.Label(self.root, text="", bg=BG).pack()  # Trigger style application

    def _build_ui(self):
        """构建标签页界面"""
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        # --- Tab 1: 词库录入 ---
        self.tab_entry = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(self.tab_entry, text="  📝 添加单词  ")
        self._build_tab_entry()

        # --- Tab 2: 新词默写 ---
        tab2 = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(tab2, text="  🎯 拼写挑战  ")
        self._build_tab_dict(tab2)

        # --- Tab 3: 复习默写 ---
        tab3 = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(tab3, text="  🗂️ 闪卡复习  ")
        self._build_tab_review(tab3)

        # --- Tab 5: 词库管理 ---
        tab5 = ttk.Frame(self.notebook, padding=6)
        self.notebook.add(tab5, text="  📊 学习看板  ")
        self._build_tab_manage(tab5)

        # --- 底部状态栏 ---
        self._build_statusbar()

    def _build_statusbar(self):
        """简单的状态栏，显示总词数"""
        bar = ttk.Frame(self.root)
        bar.pack(fill=tk.X, padx=6, pady=(0, 4))

        self.status_var = tk.StringVar()
        lbl = tk.Label(bar, textvariable=self.status_var, anchor="w",
                       font=("微软雅黑", 9), fg="gray")
        lbl.pack(side=tk.LEFT)
        self._refresh_status()

    def _refresh_status(self):
        total = self._count_words()
        unlearned = self._count_words(0)
        learning = self._count_words(1)
        mastered = self._count_words(2)
        self.status_var.set(
            f"词汇总量：{total}  │  未学习：{unlearned}  │  学习中：{learning}  │  已掌握：{mastered}"
        )

    # ======================== Tab 1: 词库录入 ======================= #

    def _build_tab_entry(self):
        parent = self.tab_entry
        top_bar = ttk.Frame(parent)
        top_bar.pack(fill=tk.X, pady=(0, 4))
        ttk.Button(top_bar, text="❓ 录入与导入规范指南", command=self.show_format_help).pack(anchor="e")
        top = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        top.pack(fill=tk.X, pady=(0, 6))
        parent.after(50, lambda: top.sashpos(0, 300))
        left = ttk.LabelFrame(top, text=" 单个录入 ", padding=12)
        top.add(left, weight=1)

        tk.Label(left, text="🔤 英文单词", font=("Segoe UI", 10), bg="#F0F2F5", fg="#2D3436").pack(anchor="w", pady=(2, 2))
        self.e_word_var = tk.StringVar()
        self.ent_word = ttk.Entry(left, textvariable=self.e_word_var, font=("Segoe UI", 12))
        self.ent_word.pack(fill=tk.X, pady=(0, 4))

        self.e_pos_var = tk.StringVar()


        tk.Label(left, text="📢 国际音标", font=("Segoe UI", 10), bg="#F0F2F5", fg="#2D3436").pack(anchor="w", pady=(2, 2))
        self.e_phonetic_var = tk.StringVar()
        ttk.Entry(left, textvariable=self.e_phonetic_var, font=("Segoe UI", 12)).pack(fill=tk.X, pady=(0, 4))

        tk.Label(left, text="📝 词性与释义", font=("Segoe UI", 10), bg="#F0F2F5", fg="#2D3436").pack(anchor="w", pady=(2, 2))
        self.e_meaning_var = tk.StringVar()
        self.e_defs_text = tk.Text(left, height=4, font=("Segoe UI", 11), bg="#FFFFFF", fg="#2D3436",
                                    relief=tk.SUNKEN, bd=1, padx=6, pady=4)
        self.e_defs_text.pack(fill=tk.X, pady=(0, 4))



        tk.Label(left, text="词书分类：", font=("Segoe UI", 10), bg="#F0F2F5", fg="#2D3436").pack(anchor="w", pady=(2, 2))
        cat_row = ttk.Frame(left)
        cat_row.pack(anchor="w", fill=tk.X, pady=(2, 6))
        self.e_cat_var = tk.StringVar(value=self.categories[0] if self.categories else "")
        self.e_cat_cb = ttk.Combobox(cat_row, textvariable=self.e_cat_var, values=self.categories,
                     font=("Segoe UI", 11), width=10, state="readonly")
        self.e_cat_cb.pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(cat_row, text="+", width=3, command=self._add_category).pack(side=tk.LEFT)

        self.ent_word.focus()

        btn_row = ttk.Frame(left)
        btn_row.pack(fill=tk.X, pady=(4, 0))
        ttk.Button(btn_row, text="提交录入", command=self._submit_entry).pack(side=tk.LEFT, padx=(0, 8))
        self.entry_fb = tk.Label(btn_row, text="", font=("Segoe UI", 10), bg="#F0F2F5")
        self.entry_fb.pack(side=tk.LEFT)

        right = ttk.LabelFrame(top, text=" 批量导入 ", padding=12)
        top.add(right, weight=1)

        tk.Label(right, text="导入到词书分类：", font=("Segoe UI", 10), bg="#F0F2F5", fg="#2D3436").pack(anchor="w", pady=(2, 2))
        cat_row2 = ttk.Frame(right)
        cat_row2.pack(anchor="w", fill=tk.X, pady=(2, 4))
        self.b_cat_var = tk.StringVar(value=self.categories[0] if self.categories else "")
        self.b_cat_cb = ttk.Combobox(cat_row2, textvariable=self.b_cat_var, values=self.categories,
                     font=("Segoe UI", 11), width=10, state="readonly")
        self.b_cat_cb.pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(cat_row2, text="+", width=3, command=self._add_category).pack(side=tk.LEFT)



        text_frame = tk.Frame(right)
        text_frame.pack(fill=tk.BOTH, expand=True, pady=(6, 4))
        vbar = tk.Scrollbar(text_frame, orient=tk.VERTICAL)
        vbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.batch_text = tk.Text(text_frame, font=("Segoe UI", 10), wrap=tk.WORD,
                                   yscrollcommand=vbar.set, bg="#FFFFFF", fg="#2D3436",
                                   relief=tk.SUNKEN, bd=1, padx=8, pady=8)
        self.batch_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vbar.config(command=self.batch_text.yview)


        ttk.Button(right, text="开始导入", command=self._do_batch_import).pack(anchor="w", pady=(2, 0))
        self.batch_fb_var = tk.StringVar()
        tk.Label(right, textvariable=self.batch_fb_var, font=("Segoe UI", 10),
                 bg="#F0F2F5").pack(anchor="w", pady=(2, 0))

        ttk.Separator(parent, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(4, 4))
        tk.Label(parent, text="最近录入：", font=("Segoe UI", 9),
                 fg="#636E72", bg="#F0F2F5").pack(anchor="w", pady=(2, 2))

        list_frame = ttk.Frame(parent)
        list_frame.pack(fill=tk.BOTH, expand=True)
        sb = ttk.Scrollbar(list_frame, orient=tk.VERTICAL)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.entry_list = tk.Listbox(list_frame, font=("Segoe UI", 9), yscrollcommand=sb.set,
                                      bg="#FFFFFF", fg="#2D3436", relief=tk.FLAT, bd=0)
        self.entry_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.config(command=self.entry_list.yview)
        self._refresh_entry_list()

    def _submit_entry(self):
        """提交单词录入"""
        word = self.e_word_var.get().strip()
        pos = self.e_pos_var.get().strip()
        phonetic = self.e_phonetic_var.get().strip()
        meaning = self.e_meaning_var.get().strip()

        if not word:
            self.entry_fb.config(text="  单词不能为空！", fg="red")
            self.ent_word.focus()
            return
        if not word:
            self.entry_fb.config(text="  中文意思不能为空！", fg="red")
            self.ent_word.focus()
            return

        try:
            now_ts = int(time.time())
            category = self.e_cat_var.get()
            raw = self.e_defs_text.get("1.0", tk.END).strip()
            defs_list = []
            for line in raw.split("\n"):
                line = line.strip()
                if not line:
                    continue
                parts = line.split("|", 1)
                defs_list.append({"pos": parts[0].strip() if len(parts) > 0 else "",
                                   "meaning": parts[1].strip() if len(parts) > 1 else parts[0].strip()})
            if not defs_list:
                defs_list = [{"pos": "", "meaning": ""}]
            # 提取第一个词性和意思用于向后兼容的 pos/meaning 字段
            first_pos = defs_list[0].get("pos", "")
            first_meaning = defs_list[0].get("meaning", "")
            definitions_json = json.dumps(defs_list, ensure_ascii=False)
            self.cursor.execute(
                "INSERT INTO words (word, pos, phonetic, meaning, category, definitions, box_level, next_review_time, status) "
                "VALUES (?, ?, ?, ?, ?, ?, 1, ?, 0)",
                (word, first_pos, phonetic, first_meaning, category, definitions_json, now_ts),
            )
            self.conn.commit()
            self.entry_fb.config(text=f"  已录入：{word}", fg="#00B894")
            self.e_word_var.set("")
            self.e_pos_var.set("")
            self.e_phonetic_var.set("")
            self.e_meaning_var.set("")
            self.e_defs_text.delete("1.0", tk.END)
            self.e_defs_text.insert("1.0", "v.|预言；预测")
            self.ent_word.focus()
            self._refresh_entry_list()
            self._refresh_status()
        except Exception as e:
            self.entry_fb.config(text=f"  失败：{e}", fg="#D63031")
            self.conn.commit()
            self.entry_fb.config(text=f"  成功录入：{word}", fg="green")
            # 清空输入框
            self.e_word_var.set("")
            self.e_pos_var.set("")
            self.e_phonetic_var.set("")
            self.e_meaning_var.set("")
            self.ent_word.focus()
            self._refresh_entry_list()
            self._refresh_status()
        except Exception as e:
            self.entry_fb.config(text=f"  录入失败：{e}", fg="red")

    def _refresh_entry_list(self):
        """刷新最近录入列表"""
        self.entry_list.delete(0, tk.END)
        try:
            self.cursor.execute(
                "SELECT id, word, meaning FROM words ORDER BY id DESC LIMIT 30"
            )
            for row in self.cursor.fetchall():
                self.entry_list.insert(tk.END, f"  #{row[0]}  {row[1]}  —  {row[2]}")
        except Exception:
            pass

    # ==================== Tab 2: 新词默写 ==================== #

    def _build_tab_dict(self, parent):
        """新词默写界面 —— 设置 + 默写区"""
        # ======== 设置区 ========
        setup = ttk.Frame(parent)
        setup.pack(fill=tk.BOTH, expand=True)
        self._dict_setup = setup

        ttk.Label(setup, text="开始今日新词默写",
                  font=("微软雅黑", 12, "bold")).pack(anchor="w", pady=(0, 6))

        self.d_avail_lbl = ttk.Label(setup, text="", font=("微软雅黑", 9))
        self.d_avail_lbl.pack(anchor="w", pady=(0, 8))
        # ---- 词书分类选择 ----
        ttk.Label(setup, text="选择词书分类：", font=("微软雅黑", 10)).pack(anchor="w")
        self.d_cat_var = tk.StringVar(value=self.categories[0] if self.categories else "")
        self.d_cat_cb = ttk.Combobox(setup, textvariable=self.d_cat_var,
                                      values=self.categories,
                                      font=("微软雅黑", 11), width=10, state="readonly")
        self.d_cat_cb.pack(anchor="w", pady=(2, 6))

        ttk.Label(setup, text="今天想默写的新单词数量 N：",
                  font=("微软雅黑", 10)).pack(anchor="w")
        self.d_num_var = tk.StringVar(value="10")
        ent_n = ttk.Entry(setup, textvariable=self.d_num_var, font=("微软雅黑", 11), width=10)
        ent_n.pack(anchor="w", pady=(4, 8))
        ent_n.bind("<Return>", lambda e: self._start_dictation())

        ttk.Button(setup, text="开始默写", command=self._start_dictation
                   ).pack(anchor="w")

        self._update_dict_avail()

        # ======== 默写区（初始隐藏） ========
        area = ttk.Frame(parent)
        self._dict_area = area

        # 进度条
        self.d_prog_var = tk.StringVar(value="")
        ttk.Label(area, textvariable=self.d_prog_var,
                  font=("微软雅黑", 10)).pack(anchor="w")
        self.d_prog_bar = ttk.Progressbar(area, length=400, mode="determinate")
        self.d_prog_bar.pack(anchor="w", pady=(4, 10))

        # 单词信息框
        info = ttk.LabelFrame(area, text="请默写以下单词", padding=12)
        info.pack(fill=tk.X, pady=(0, 10))

        self.d_meaning_lbl = tk.Label(info, text="", font=("微软雅黑", 16, "bold"),
                                      wraplength=500, fg="#1a1a2e")
        self.d_meaning_lbl.pack(anchor="center", pady=(2, 2))

        self.d_pos_lbl = ttk.Label(info, text="", font=("微软雅黑", 10))
        self.d_pos_lbl.pack(anchor="center", pady=1)

        self.d_phonetic_lbl = ttk.Label(info, text="", font=("微软雅黑", 10))
        self.d_phonetic_lbl.pack(anchor="center", pady=(1, 4))

        ttk.Separator(area, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(0, 8))

        # 输入
        ttk.Label(area, text="请输入对应的英文单词：",
                  font=("微软雅黑", 10)).pack(anchor="w")
        self.d_ans_var = tk.StringVar()
        self.d_ans_ent = ttk.Entry(area, textvariable=self.d_ans_var,
                                    font=("微软雅黑", 13), width=30)
        self.d_ans_ent.pack(anchor="w", pady=(4, 6))
        self.d_ans_ent.bind("<Return>", lambda e: self._check_dict_ans())

        # 按钮行
        btn_row = ttk.Frame(area)
        btn_row.pack(anchor="w", pady=(0, 6))
        self.d_btn_submit = ttk.Button(btn_row, text="提交核对", command=self._check_dict_ans)
        self.d_btn_submit.pack(side=tk.LEFT, padx=(0, 8))
        self.d_btn_next = ttk.Button(btn_row, text="下一个 →", command=self._dict_next,
                                     state="disabled")
        self.d_btn_next.pack(side=tk.LEFT)

        # 反馈
        self.d_fb_var = tk.StringVar(value="")
        self.d_fb_lbl = tk.Label(area, textvariable=self.d_fb_var, font=("微软雅黑", 11))
        self.d_fb_lbl.pack(anchor="w")

    def _update_dict_avail(self):
        """更新可用新词数量显示"""
        current_cat = getattr(self, "d_cat_var", None)
        cat_val = current_cat.get() if current_cat else None
        if cat_val:
            cnt = 0
            try:
                self.cursor.execute(
                    "SELECT COUNT(*) FROM words WHERE status=0 AND category=?",
                    (cat_val,),
                )
                cnt = self.cursor.fetchone()[0]
            except: pass
        else:
            cnt = self._count_words(0)
        self.d_avail_lbl.config(text=f"当前词书分类〔{cat_val}〕有 {cnt} 个未学习的新单词可供默写。")

    def _start_dictation(self):
        """开始新词默写会话"""
        try:
            n = int(self.d_num_var.get().strip())
            if n <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("提示", "请输入一个有效的正整数！")
            return

        self.cursor.execute(
            "SELECT id, word, pos, phonetic, meaning, box_level, next_review_time, status "
            "FROM words WHERE status = 0 AND category=? ORDER BY id ASC LIMIT ?",
            (self.d_cat_var.get(), n,),
        )
        words = self.cursor.fetchall()

        if not words:
            messagebox.showinfo("提示", "词库中没有未学习的单词。\n请先切换到「词库录入」标签页添加单词。")
            return

        if len(words) < n:
            messagebox.showinfo("提示", f"目前只有 {len(words)} 个未学习的单词，已全部加载。")

        self.dict_words = words
        self.dict_idx = 0
        self.dict_correct = 0
        self.dict_answered = False

        # 切换到默写界面
        self._dict_setup.pack_forget()
        self._dict_area.pack(fill=tk.BOTH, expand=True)

        self._show_dict_word()

    def _show_dict_word(self):
        """显示当前默写的单词"""
        if self.dict_idx >= len(self.dict_words):
            self._finish_dictation()
            return

        w = self.dict_words[self.dict_idx]
        wid, word, pos, phonetic, meaning, box, nrt, st = w

        total = len(self.dict_words)
        self.d_prog_var.set(f"第 {self.dict_idx + 1} / {total} 个")
        self.d_prog_bar["maximum"] = total
        self.d_prog_bar["value"] = self.dict_idx + 1

        # 解析 JSON definitions 显示多行
        try:
            defs_list = json.loads(meaning) if meaning and meaning.startswith("[") else []
        except:
            defs_list = []
        if not defs_list:
            defs_text = meaning
        else:
            defs_text = "\n".join([f"  【{d.get(chr(112)+chr(111)+chr(115),chr(39))}】{d.get(chr(109)+chr(101)+chr(97)+chr(110)+chr(105)+chr(110)+chr(103),chr(39))}" for d in defs_list])
        self.d_meaning_lbl.config(text=defs_text)
        self.d_pos_lbl.config(text=f"音标：{phonetic if phonetic else chr(39)}")
        self.d_phonetic_lbl.config(text="")
        self.d_pos_lbl.config(text=f"词性：{pos if pos else '（无）'}")
        self.d_phonetic_lbl.config(text="")  # 默写时隐藏音标

        # 重置
        self.d_ans_var.set("")
        self.d_fb_var.set("")
        self.d_fb_lbl.config(fg="black")
        self.d_btn_submit.config(state="normal")
        self.d_btn_next.config(state="disabled")
        self.d_ans_ent.config(state="normal")
        self.d_ans_ent.focus()
        self.dict_answered = False

    def _check_dict_ans(self):
        """核对新词默写答案"""
        if self.dict_answered:
            return

        inp = self.d_ans_var.get().strip()
        if not inp:
            self.d_fb_var.set("  请输入英文单词！")
            self.d_fb_lbl.config(fg="orange")
            return

        w = self.dict_words[self.dict_idx]
        wid, correct_word, pos, phonetic, meaning, box, nrt, st = w
        # 解析 JSON definitions 获取第一个 meaning 用于反馈显示
        try:
            d_list = json.loads(meaning) if meaning and meaning.startswith("[") else []
        except:
            d_list = []
        if d_list:
            meaning = d_list[0].get("meaning", meaning)

        now_ts = int(time.time())
        if _TTS is not None:
            try:
                _TTS.say(correct_word)
                _TTS.runAndWait()
            except:
                pass

        if inp.lower() == correct_word.lower():
            # 拼写正确 → 设置为学习状态，进入 Box 1，1 天后复习
            self.cursor.execute(
                "UPDATE words SET status=1, box_level=1, next_review_time=? WHERE id=?",
                (now_ts + BOX_DAYS[1] * 86400, wid),
            )
            ph = f" [{phonetic}]" if phonetic else ""
            self.d_fb_var.set(f"  正确！{correct_word}{ph} 已加入复习队列（Box 1，明天复习）")
            self.d_fb_lbl.config(fg="green")
            self.dict_correct += 1
            self._record_review_history(wid, 1)
        else:
            # 拼写错误 → 仍保持 status=0（未学习）
            ph = f" [{phonetic}]" if phonetic else ""
            self.d_fb_var.set(f"  错误！正确答案是：{correct_word}{ph}")
            self._record_review_history(wid, 0)
            self.d_fb_lbl.config(fg="red")

        self.conn.commit()
        self.dict_answered = True
        self.d_btn_submit.config(state="disabled")
        self.d_ans_ent.config(state="disabled")
        self.d_btn_next.config(state="normal")
        self.d_btn_next.focus()

    def _dict_next(self):
        """下一个默写单词"""
        self.dict_idx += 1
        self._show_dict_word()

    def _finish_dictation(self):
        """完成新词默写，切换回设置区"""
        self._dict_area.pack_forget()
        self._dict_setup.pack(fill=tk.BOTH, expand=True)

        total = len(self.dict_words)
        pct = f"（{self.dict_correct / total * 100:.0f}%）" if total else ""
        messagebox.showinfo(
            "默写完成",
            f"今日默写结束！\n正确 {self.dict_correct} / {total} 个  {pct}",
        )
        self._update_dict_avail()
        self._refresh_status()

    # ==================== Tab 3: 复习默写 ==================== #

    def _build_tab_review(self, parent):
        """复习默写界面 —— 设置 + 复习区"""
        # ======== 设置区 ========
        setup = ttk.Frame(parent)
        setup.pack(fill=tk.BOTH, expand=True)
        self._rev_setup = setup

        ttk.Label(setup, text="抗遗忘复习默写",
                  font=("微软雅黑", 12, "bold")).pack(anchor="w", pady=(0, 6))

        self.r_info_lbl = ttk.Label(setup, text="", font=("微软雅黑", 10))
        self.r_info_lbl.pack(anchor="w", pady=(0, 8))
        # ---- 词书分类选择 ----
        ttk.Label(setup, text="选择词书分类：", font=("微软雅黑", 10)).pack(anchor="w")
        self.r_cat_var = tk.StringVar(value=self.categories[0] if self.categories else "")
        self.r_cat_cb = ttk.Combobox(setup, textvariable=self.r_cat_var,
                                      values=self.categories,
                                      font=("微软雅黑", 11), width=10, state="readonly")
        self.r_cat_cb.pack(anchor="w", pady=(2, 6))

        # 算法说明
        algo_frame = ttk.LabelFrame(setup, text="递进式多级口袋算法说明", padding=8)
        algo_frame.pack(anchor="w", fill=tk.X, pady=(0, 10))
        algo_text = (
            "• 记忆共 5 级（Box 1→5），间隔天数依次为：1 → 2 → 4 → 7 → 15\n"
            "• 拼写正确 → 升一级；拼写错误 → 重置回 Box 1\n"
            "• 达到 Box 5 并拼写正确后，单词标记为「已掌握」，不再进入复习池"
        )
        tk.Label(algo_frame, text=algo_text, font=("微软雅黑", 9),
                  fg="#444").pack(anchor="w")

        ttk.Button(setup, text="开始复习", command=self._start_review
                   ).pack(anchor="w")

        self._update_rev_info()

        # ======== 复习区（初始隐藏） ========
        area = ttk.Frame(parent)
        self._rev_area = area

        self.r_prog_var = tk.StringVar(value="")
        ttk.Label(area, textvariable=self.r_prog_var,
                  font=("微软雅黑", 10)).pack(anchor="w")
        self.r_prog_bar = ttk.Progressbar(area, length=400, mode="determinate")
        self.r_prog_bar.pack(anchor="w", pady=(4, 10))

        info = ttk.LabelFrame(area, text="请默写以下单词", padding=12)
        info.pack(fill=tk.X, pady=(0, 10))

        self.r_meaning_lbl = tk.Label(info, text="", font=("微软雅黑", 16, "bold"),
                                      wraplength=500, fg="#1a1a2e")
        self.r_meaning_lbl.pack(anchor="center", pady=(2, 2))

        self.r_pos_lbl = ttk.Label(info, text="", font=("微软雅黑", 10))
        self.r_pos_lbl.pack(anchor="center", pady=1)

        self.r_phonetic_lbl = ttk.Label(info, text="", font=("微软雅黑", 10))
        self.r_phonetic_lbl.pack(anchor="center", pady=(1, 4))

        ttk.Separator(area, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(0, 8))

        ttk.Label(area, text="请输入对应的英文单词：",
                  font=("微软雅黑", 10)).pack(anchor="w")
        self.r_ans_var = tk.StringVar()
        self.r_ans_ent = ttk.Entry(area, textvariable=self.r_ans_var,
                                    font=("微软雅黑", 13), width=30)
        self.r_ans_ent.pack(anchor="w", pady=(4, 6))
        self.r_ans_ent.bind("<Return>", lambda e: self._check_rev_ans())

        btn_row = ttk.Frame(area)
        btn_row.pack(anchor="w", pady=(0, 6))
        self.r_btn_submit = ttk.Button(btn_row, text="提交核对", command=self._check_rev_ans)
        self.r_btn_submit.pack(side=tk.LEFT, padx=(0, 8))
        self.r_btn_next = ttk.Button(btn_row, text="下一个 →", command=self._rev_next,
                                     state="disabled")
        self.r_btn_next.pack(side=tk.LEFT)

        self.r_fb_var = tk.StringVar(value="")
        self.r_fb_lbl = tk.Label(area, textvariable=self.r_fb_var, font=("微软雅黑", 11))
        self.r_fb_lbl.pack(anchor="w")

    def _update_rev_info(self):
        """更新复习提示信息"""
        now_ts = int(time.time())
        self.cursor.execute(
            "SELECT COUNT(*) FROM words WHERE status=1 AND category=? AND next_review_time<=?",
            (self.r_cat_var.get(), now_ts,),
        )
        due = self.cursor.fetchone()[0]
        total = self._count_words(1)
        current_cat = getattr(self, "r_cat_var", None)
        cat_name = current_cat.get() if current_cat else "全部"
        self.r_info_lbl.config(
            text=f"当前词书分类〔{cat_name}〕有 {due} 个单词到期待复习（共 {total} 个单词在学习中）。"
        )

    def _start_review(self):
        """开始复习会话"""
        now_ts = int(time.time())
        self.cursor.execute(
            "SELECT id, word, pos, phonetic, meaning, box_level, next_review_time, status "
            "FROM words WHERE status=1 AND category=? AND next_review_time<=? "
            "ORDER BY box_level ASC, next_review_time ASC",
            (self.r_cat_var.get(), now_ts,),
        )
        words = self.cursor.fetchall()

        if not words:
            messagebox.showinfo("提示", "当前没有需要复习的单词！\n\n"
                                        "请先在「词库录入」添加单词，\n"
                                        "然后在「新词默写」中学习并激活单词。")
            return

        self.rev_words = words
        self.rev_idx = 0
        self.rev_correct = 0
        self.rev_answered = False

        self._rev_setup.pack_forget()
        self._rev_area.pack(fill=tk.BOTH, expand=True)

        self._show_rev_word()

    def _show_rev_word(self):
        """显示当前复习的单词"""
        if self.rev_idx >= len(self.rev_words):
            self._finish_review()
            return

        w = self.rev_words[self.rev_idx]
        wid, word, pos, phonetic, meaning, box, nrt, st = w

        total = len(self.rev_words)
        self.r_prog_var.set(f"第 {self.rev_idx + 1} / {total} 个  （当前 Box {box}）")
        self.r_prog_bar["maximum"] = total
        self.r_prog_bar["value"] = self.rev_idx + 1

        # 解析 JSON definitions 显示多行
        try:
            defs_list = json.loads(meaning) if meaning and meaning.startswith(chr(91)) else []
        except:
            defs_list = []
        if not defs_list:
            defs_text = meaning
        else:
            defs_text = chr(10).join([chr(32)*4 + chr(12304) + d.get(chr(112)+chr(111)+chr(115),chr(39)) + chr(12305) + d.get(chr(109)+chr(101)+chr(97)+chr(110)+chr(105)+chr(110)+chr(103),chr(39)) for d in defs_list])
        self.r_meaning_lbl.config(text=defs_text)
        self.r_pos_lbl.config(text=f"音标：" + (phonetic if phonetic else chr(39)))
        self.r_phonetic_lbl.config(text="")
        self.r_pos_lbl.config(text=f"词性：{pos if pos else '（无）'}")
        self.r_phonetic_lbl.config(text="")  # 复习时隐藏音标

        self.r_ans_var.set("")
        self.r_fb_var.set("")
        self.r_fb_lbl.config(fg="black")
        self.r_btn_submit.config(state="normal")
        self.r_btn_next.config(state="disabled")
        self.r_ans_ent.config(state="normal")
        self.r_ans_ent.focus()
        self.rev_answered = False

    def _check_rev_ans(self):
        """核对复习答案 —— 应用 5 级口袋算法"""
        if self.rev_answered:
            return

        inp = self.r_ans_var.get().strip()
        if not inp:
            self.r_fb_var.set("  请输入英文单词！")
            self.r_fb_lbl.config(fg="orange")
            return

        w = self.rev_words[self.rev_idx]
        wid, correct_word, pos, phonetic, meaning, box, nrt, st = w
        # 解析 JSON definitions 获取第一个 meaning
        try:
            d_list = json.loads(meaning) if meaning and meaning.startswith("[") else []
        except:
            d_list = []
        if d_list:
            meaning = d_list[0].get("meaning", meaning)
        now_ts = int(time.time())
        if _TTS is not None:
            try:
                _TTS.say(correct_word)
                _TTS.runAndWait()
            except:
                pass

        if inp.lower() == correct_word.lower():
            # ---- 拼写正确：升级 ----
            new_box = min(box + 1, 5)

            if new_box >= 5 and box >= 5:
                # 已在 Box 5 且正确 → 彻底掌握
                self.cursor.execute(
                    "UPDATE words SET status=2, box_level=5 WHERE id=?",
                    (wid,),
                )
                ph = f" [{phonetic}]" if phonetic else ""
                self.r_fb_var.set(f"  正确！{correct_word}{ph} 已达到 Box 5，标记为「已掌握」！")
                self.r_fb_lbl.config(fg="green")
                self._record_review_history(wid, 1)
            else:
                days = BOX_DAYS[new_box]
                nrt = now_ts + days * 86400
                self.cursor.execute(
                    "UPDATE words SET box_level=?, next_review_time=? WHERE id=?",
                    (new_box, nrt, wid),
                )
                ph = f" [{phonetic}]" if phonetic else ""
                self.r_fb_var.set(
                    f"  正确！{correct_word}{ph} 升至 Box {new_box}，将在 {days} 天后再次复习。"
                )
                self.r_fb_lbl.config(fg="green")
                self._record_review_history(wid, 1)

            self.rev_correct += 1
        else:
            # ---- 拼写错误：重置为 Box 1 ----
            nrt = now_ts + BOX_DAYS[1] * 86400
            self.cursor.execute(
                "UPDATE words SET box_level=1, next_review_time=? WHERE id=?",
                (nrt, wid),
            )
            ph = f" [{phonetic}]" if phonetic else ""
            self.r_fb_var.set(f"  错误！正确答案是：{correct_word}{ph}  （已重置为 Box 1，明日需重新默写）")
            self.r_fb_lbl.config(fg="red")
            self._record_review_history(wid, 0)

        self.conn.commit()
        self.rev_answered = True
        self.r_btn_submit.config(state="disabled")
        self.r_ans_ent.config(state="disabled")
        self.r_btn_next.config(state="normal")
        self.r_btn_next.focus()

    def _rev_next(self):
        """下一个复习单词"""
        self.rev_idx += 1
        self._show_rev_word()

    def _finish_review(self):
        """完成复习，切换回设置区"""
        self._rev_area.pack_forget()
        self._rev_setup.pack(fill=tk.BOTH, expand=True)

        total = len(self.rev_words)
        pct = f"（{self.rev_correct / total * 100:.0f}%）" if total else ""
        messagebox.showinfo(
            "复习完成",
            f"复习结束！\n正确 {self.rev_correct} / {total} 个  {pct}",
        )
        self._update_rev_info()
        self._refresh_status()


# ==================== Tab 4: 批量导入 ==================== #

    def _record_review_history(self, word_id, result):
        """向 review_history 表中插入一条记录"""
        now_ts = int(time.time())
        self.cursor.execute(
            "INSERT INTO review_history (word_id, review_time, result) VALUES (?, ?, ?)",
            (word_id, now_ts, result),
        )
        self.conn.commit()
                # Old data migration removed (no defaults)\nthon3
# -*- coding: utf-8 -*-
"""
英语单词默写与复习软件

功能：
  1. 词库录入 —— 手动输入单词（英文、词性、音标、中文意思）
  2. 新词默写 —— 每次自选 N 个新词，看中默英，即时校对
  3. 抗遗忘复习 —— 基于 5 级口袋算法，根据拼写对错自动升降级

技术栈：Python + Tkinter + SQLite（零依赖，双击即运行）
"""

import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
import time
import os
import datetime
import shutil
import json

try:
    import pyttsx3
    _TTS = pyttsx3.init()
except:
    _TTS = None


DB_FILENAME = "vocab_data.db"

# 5 级口袋算法 —— 各级对应的复习间隔天数
BOX_DAYS = {1: 1, 2: 2, 3: 4, 4: 7, 5: 15}


# ================================================================
#  工具函数
# ================================================================

def _db_path():
    """返回数据库文件的绝对路径"""
    try:
        d = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        d = os.getcwd()
    return os.path.join(d, DB_FILENAME)


# ================================================================
#  主应用类
# ================================================================

class VocabApp:
    """英语单词默写与复习应用程序"""

    def __init__(self, root):
        self.root = root
        self.root.title("英语单词默写与复习")
        self.root.geometry("960x640")
        self.root.minsize(560, 480)
        self.root.configure(bg="#F0F2F5")

        # -------------------------------------------------------- #
        #  数据库初始化
        # -------------------------------------------------------- #
        self.db_path = _db_path()
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        self._init_db()

        # -------------------------------------------------------- #
        #  会话状态
        # -------------------------------------------------------- #
        # 新词默写
        self.dict_words = []
        self.dict_idx = 0
        self.dict_correct = 0
        self.dict_answered = False

        # 复习默写
        self.rev_words = []
        self.rev_idx = 0
        self.rev_correct = 0
        self.rev_answered = False

        # -------------------------------------------------------- #
        #  构建界面
        # -------------------------------------------------------- #
        self._setup_style()
        self.dash_frame = None
        self.categories = []
        self._build_ui()

        # 窗口关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------ #
    #  数据库操作
    # ------------------------------------------------------------ #

    def _init_db(self):
        """创建数据库表（如尚未存在）"""
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS words (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                word             TEXT    NOT NULL,
                pos              TEXT    DEFAULT '',
                phonetic         TEXT    DEFAULT '',
                meaning          TEXT    DEFAULT '',
                box_level        INTEGER DEFAULT 1,
                next_review_time INTEGER DEFAULT 0,
                status           INTEGER DEFAULT 0,
                category         TEXT DEFAULT ''
            )
        """)
        self.conn.commit()
        # 兼容旧数据库：添加 category 列（如已存在则跳过）
        try:
            self.cursor.execute("ALTER TABLE words ADD COLUMN category TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass
        try:
            self.cursor.execute("ALTER TABLE words ADD COLUMN definitions TEXT DEFAULT '[]'")
        except sqlite3.OperationalError:
            pass
        # 迁移旧数据：将 pos + meaning 合并为 JSON definitions
        self.cursor.execute("SELECT id, pos, meaning FROM words WHERE definitions IS NULL OR definitions = '[]'")
        for row_id, old_pos, old_meaning in self.cursor.fetchall():
            d = json.dumps([{"pos": old_pos or "", "meaning": old_meaning or ""}])
            self.cursor.execute("UPDATE words SET definitions=? WHERE id=?", (d, row_id))
        self.conn.commit()
        self.cursor.execute(
            '''CREATE TABLE IF NOT EXISTS review_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                word_id     INTEGER NOT NULL,
                review_time INTEGER NOT NULL,
                result      INTEGER NOT NULL,
                FOREIGN KEY (word_id) REFERENCES words(id)
            )'''
        )
        self.conn.commit()
        self.cursor.execute("""CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )""")
        self.conn.commit()

    def _count_words(self, status=None):
        """统计单词数量，status 为 None 时统计全部"""
        if status is None:
            self.cursor.execute("SELECT COUNT(*) FROM words")
        else:
            self.cursor.execute("SELECT COUNT(*) FROM words WHERE status=?", (status,))
        return self.cursor.fetchone()[0]

    # ------------------------------------------------------------ #
    #  窗口关闭
    # ------------------------------------------------------------ #

    def _on_close(self):
        try:
            self.conn.close()
        except Exception:
            pass
        self.root.destroy()

    # ============================================================ #
    #  UI 构建
    # ============================================================ #


    # ------------------------------------------------------------ #
    #  UI 样式
    # ------------------------------------------------------------ #

    def _setup_style(self):
        """配置现代化扁平化 UI 样式"""
        style = ttk.Style()
        style.theme_use("clam")

        # 柔和现代配色
        BG = "#F0F2F5"
        CARD = "#FFFFFF"
        PRI = "#2D3436"
        ACC = "#0984E3"
        SUC = "#00B894"
        DNG = "#D63031"
        TXT = "#2D3436"
        TX2 = "#636E72"

        # Notebook 标签页
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=CARD, foreground=PRI,
                        font=("Segoe UI", 11), padding=[24, 10])
        style.map("TNotebook.Tab", background=[("selected", ACC)],
                  foreground=[("selected", "#FFFFFF")])

        # Frame
        style.configure("TFrame", background=BG)
        style.configure("TLabelframe", background=BG, foreground=PRI,
                        font=("Segoe UI", 10, "bold"))
        style.configure("TLabelframe.Label", background=BG, foreground=ACC)

        # Label
        style.configure("TLabel", background=BG, foreground=TXT, font=("Segoe UI", 10))

        # Button
        style.configure("TButton", background=ACC, foreground="#FFFFFF",
                        font=("Segoe UI", 10, "bold"), padding=[18, 8], borderwidth=0)
        style.map("TButton", background=[("active", "#0773C5"), ("pressed", "#065EA6")])
        style.configure("Accent.TButton", background=SUC)
        style.map("Accent.TButton", background=[("active", "#00A381")])
        style.configure("Danger.TButton", background=DNG)
        style.map("Danger.TButton", background=[("active", "#B22222")])

        # Entry & Combobox
        style.configure("TEntry", fieldbackground=CARD, foreground=TXT,
                        font=("Segoe UI", 11), padding=[8, 6])
        style.configure("TCombobox", fieldbackground=CARD, foreground=TXT,
                        font=("Segoe UI", 11), padding=[8, 6])

        # Treeview
        style.configure("Treeview", background=CARD, foreground=TXT,
                        fieldbackground=CARD, font=("Segoe UI", 10), rowheight=30)
        style.configure("Treeview.Heading", background=PRI, foreground="#FFFFFF",
                        font=("Segoe UI", 10, "bold"))
        style.map("Treeview", background=[("selected", "#74B9FF")])

        # Progressbar
        style.configure("Horizontal.TProgressbar", background=ACC, troughcolor=CARD,
                        borderwidth=0, thickness=8)

        tk.Label(self.root, text="", bg=BG).pack()  # Trigger style application

    def _build_ui(self):
        """构建标签页界面"""
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        # --- Tab 1: 词库录入 ---
        self.tab_entry = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(self.tab_entry, text="  📝 添加单词  ")
        self._build_tab_entry()

        # --- Tab 2: 新词默写 ---
        tab2 = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(tab2, text="  🎯 拼写挑战  ")
        self._build_tab_dict(tab2)

        # --- Tab 3: 复习默写 ---
        tab3 = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(tab3, text="  🗂️ 闪卡复习  ")
        self._build_tab_review(tab3)

        # --- Tab 5: 词库管理 ---
        tab5 = ttk.Frame(self.notebook, padding=6)
        self.notebook.add(tab5, text="  📊 学习看板  ")
        self._build_tab_manage(tab5)

        # --- 底部状态栏 ---
        self._build_statusbar()

    def _build_statusbar(self):
        """简单的状态栏，显示总词数"""
        bar = ttk.Frame(self.root)
        bar.pack(fill=tk.X, padx=6, pady=(0, 4))

        self.status_var = tk.StringVar()
        lbl = tk.Label(bar, textvariable=self.status_var, anchor="w",
                       font=("微软雅黑", 9), fg="gray")
        lbl.pack(side=tk.LEFT)
        self._refresh_status()

    def _refresh_status(self):
        total = self._count_words()
        unlearned = self._count_words(0)
        learning = self._count_words(1)
        mastered = self._count_words(2)
        self.status_var.set(
            f"词汇总量：{total}  │  未学习：{unlearned}  │  学习中：{learning}  │  已掌握：{mastered}"
        )

    # ======================== Tab 1: 词库录入 ======================= #

    def _build_tab_entry(self):
        parent = self.tab_entry
        top_bar = ttk.Frame(parent)
        top_bar.pack(fill=tk.X, pady=(0, 4))
        ttk.Button(top_bar, text="❓ 录入与导入规范指南", command=self.show_format_help).pack(anchor="e")
        top = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        top.pack(fill=tk.X, pady=(0, 6))
        parent.after(50, lambda: top.sashpos(0, 300))
        left = ttk.LabelFrame(top, text=" 单个录入 ", padding=12)
        top.add(left, weight=1)

        tk.Label(left, text="🔤 英文单词", font=("Segoe UI", 10), bg="#F0F2F5", fg="#2D3436").pack(anchor="w", pady=(2, 2))
        self.e_word_var = tk.StringVar()
        self.ent_word = ttk.Entry(left, textvariable=self.e_word_var, font=("Segoe UI", 12))
        self.ent_word.pack(fill=tk.X, pady=(0, 4))

        self.e_pos_var = tk.StringVar()


        tk.Label(left, text="📢 国际音标", font=("Segoe UI", 10), bg="#F0F2F5", fg="#2D3436").pack(anchor="w", pady=(2, 2))
        self.e_phonetic_var = tk.StringVar()
        ttk.Entry(left, textvariable=self.e_phonetic_var, font=("Segoe UI", 12)).pack(fill=tk.X, pady=(0, 4))

        tk.Label(left, text="📝 词性与释义", font=("Segoe UI", 10), bg="#F0F2F5", fg="#2D3436").pack(anchor="w", pady=(2, 2))
        self.e_defs_text = tk.Text(left, height=4, font=("Segoe UI", 11), bg="#FFFFFF", fg="#2D3436",
                                    relief=tk.SUNKEN, bd=1, padx=6, pady=4)
        self.e_defs_text.pack(fill=tk.X, pady=(0, 4))



        tk.Label(left, text="词书分类：", font=("Segoe UI", 10), bg="#F0F2F5", fg="#2D3436").pack(anchor="w", pady=(2, 2))
        cat_row = ttk.Frame(left)
        cat_row.pack(anchor="w", fill=tk.X, pady=(2, 6))
        self.e_cat_var = tk.StringVar(value=self.categories[0] if self.categories else "")
        self.e_cat_cb = ttk.Combobox(cat_row, textvariable=self.e_cat_var, values=self.categories,
                     font=("Segoe UI", 11), width=10, state="readonly")
        self.e_cat_cb.pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(cat_row, text="+", width=3, command=self._add_category).pack(side=tk.LEFT)

        self.ent_word.focus()

        btn_row = ttk.Frame(left)
        btn_row.pack(fill=tk.X, pady=(4, 0))
        ttk.Button(btn_row, text="提交录入", command=self._submit_entry).pack(side=tk.LEFT, padx=(0, 8))
        self.entry_fb = tk.Label(btn_row, text="", font=("Segoe UI", 10), bg="#F0F2F5")
        self.entry_fb.pack(side=tk.LEFT)

        right = ttk.LabelFrame(top, text=" 批量导入 ", padding=12)
        top.add(right, weight=1)

        tk.Label(right, text="导入到词书分类：", font=("Segoe UI", 10), bg="#F0F2F5", fg="#2D3436").pack(anchor="w", pady=(2, 2))
        cat_row2 = ttk.Frame(right)
        cat_row2.pack(anchor="w", fill=tk.X, pady=(2, 4))
        self.b_cat_var = tk.StringVar(value=self.categories[0] if self.categories else "")
        self.b_cat_cb = ttk.Combobox(cat_row2, textvariable=self.b_cat_var, values=self.categories,
                     font=("Segoe UI", 11), width=10, state="readonly")
        self.b_cat_cb.pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(cat_row2, text="+", width=3, command=self._add_category).pack(side=tk.LEFT)



        text_frame = tk.Frame(right)
        text_frame.pack(fill=tk.BOTH, expand=True, pady=(6, 4))
        vbar = tk.Scrollbar(text_frame, orient=tk.VERTICAL)
        vbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.batch_text = tk.Text(text_frame, font=("Segoe UI", 10), wrap=tk.WORD,
                                   yscrollcommand=vbar.set, bg="#FFFFFF", fg="#2D3436",
                                   relief=tk.SUNKEN, bd=1, padx=8, pady=8)
        self.batch_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vbar.config(command=self.batch_text.yview)


        ttk.Button(right, text="开始导入", command=self._do_batch_import).pack(anchor="w", pady=(2, 0))
        self.batch_fb_var = tk.StringVar()
        tk.Label(right, textvariable=self.batch_fb_var, font=("Segoe UI", 10),
                 bg="#F0F2F5").pack(anchor="w", pady=(2, 0))

        ttk.Separator(parent, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(4, 4))
        tk.Label(parent, text="最近录入：", font=("Segoe UI", 9),
                 fg="#636E72", bg="#F0F2F5").pack(anchor="w", pady=(2, 2))

        list_frame = ttk.Frame(parent)
        list_frame.pack(fill=tk.BOTH, expand=True)
        sb = ttk.Scrollbar(list_frame, orient=tk.VERTICAL)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.entry_list = tk.Listbox(list_frame, font=("Segoe UI", 9), yscrollcommand=sb.set,
                                      bg="#FFFFFF", fg="#2D3436", relief=tk.FLAT, bd=0)
        self.entry_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.config(command=self.entry_list.yview)
        self._refresh_entry_list()

    def _submit_entry(self):
        """提交单词录入"""
        word = self.e_word_var.get().strip()
        pos = self.e_pos_var.get().strip()
        phonetic = self.e_phonetic_var.get().strip()
        meaning = self.e_meaning_var.get().strip()

        if not word:
            self.entry_fb.config(text="  单词不能为空！", fg="red")
            self.ent_word.focus()
            return
        if not meaning:
            self.entry_fb.config(text="  中文意思不能为空！", fg="red")
            self.ent_meaning.focus()
            return

        try:
            now_ts = int(time.time())
            category = self.e_cat_var.get()
            raw = self.e_defs_text.get("1.0", tk.END).strip()
            defs_list = []
            for line in raw.split("\n"):
                line = line.strip()
                if not line:
                    continue
                parts = line.split("|", 1)
                defs_list.append({"pos": parts[0].strip() if len(parts) > 0 else "",
                                   "meaning": parts[1].strip() if len(parts) > 1 else parts[0].strip()})
            if not defs_list:
                defs_list = [{"pos": "", "meaning": ""}]
            # 提取第一个词性和意思用于向后兼容的 pos/meaning 字段
            first_pos = defs_list[0].get("pos", "")
            first_meaning = defs_list[0].get("meaning", "")
            definitions_json = json.dumps(defs_list, ensure_ascii=False)
            self.cursor.execute(
                "INSERT INTO words (word, pos, phonetic, meaning, category, definitions, box_level, next_review_time, status) "
                "VALUES (?, ?, ?, ?, ?, ?, 1, ?, 0)",
                (word, first_pos, phonetic, first_meaning, category, definitions_json, now_ts),
            )
            self.conn.commit()
            self.entry_fb.config(text=f"  已录入：{word}", fg="#00B894")
            self.e_word_var.set("")
            self.e_pos_var.set("")
            self.e_phonetic_var.set("")
            self.e_meaning_var.set("")
            self.e_defs_text.delete("1.0", tk.END)
            self.e_defs_text.insert("1.0", "v.|预言；预测")
            self.ent_word.focus()
            self._refresh_entry_list()
            self._refresh_status()
        except Exception as e:
            self.entry_fb.config(text=f"  失败：{e}", fg="#D63031")
            self.conn.commit()
            self.entry_fb.config(text=f"  成功录入：{word}", fg="green")
            # 清空输入框
            self.e_word_var.set("")
            self.e_pos_var.set("")
            self.e_phonetic_var.set("")
            self.e_meaning_var.set("")
            self.ent_word.focus()
            self._refresh_entry_list()
            self._refresh_status()
        except Exception as e:
            self.entry_fb.config(text=f"  录入失败：{e}", fg="red")

    def _refresh_entry_list(self):
        """刷新最近录入列表"""
        self.entry_list.delete(0, tk.END)
        try:
            self.cursor.execute(
                "SELECT id, word, meaning FROM words ORDER BY id DESC LIMIT 30"
            )
            for row in self.cursor.fetchall():
                self.entry_list.insert(tk.END, f"  #{row[0]}  {row[1]}  —  {row[2]}")
        except Exception:
            pass

    # ==================== Tab 2: 新词默写 ==================== #

    def _build_tab_dict(self, parent):
        """新词默写界面 —— 设置 + 默写区"""
        # ======== 设置区 ========
        setup = ttk.Frame(parent)
        setup.pack(fill=tk.BOTH, expand=True)
        self._dict_setup = setup

        ttk.Label(setup, text="开始今日新词默写",
                  font=("微软雅黑", 12, "bold")).pack(anchor="w", pady=(0, 6))

        self.d_avail_lbl = ttk.Label(setup, text="", font=("微软雅黑", 9))
        self.d_avail_lbl.pack(anchor="w", pady=(0, 8))
        # ---- 词书分类选择 ----
        ttk.Label(setup, text="选择词书分类：", font=("微软雅黑", 10)).pack(anchor="w")
        self.d_cat_var = tk.StringVar(value=self.categories[0] if self.categories else "")
        self.d_cat_cb = ttk.Combobox(setup, textvariable=self.d_cat_var,
                                      values=self.categories,
                                      font=("微软雅黑", 11), width=10, state="readonly")
        self.d_cat_cb.pack(anchor="w", pady=(2, 6))

        ttk.Label(setup, text="今天想默写的新单词数量 N：",
                  font=("微软雅黑", 10)).pack(anchor="w")
        self.d_num_var = tk.StringVar(value="10")
        ent_n = ttk.Entry(setup, textvariable=self.d_num_var, font=("微软雅黑", 11), width=10)
        ent_n.pack(anchor="w", pady=(4, 8))
        ent_n.bind("<Return>", lambda e: self._start_dictation())

        ttk.Button(setup, text="开始默写", command=self._start_dictation
                   ).pack(anchor="w")

        self._update_dict_avail()

        # ======== 默写区（初始隐藏） ========
        area = ttk.Frame(parent)
        self._dict_area = area

        # 进度条
        self.d_prog_var = tk.StringVar(value="")
        ttk.Label(area, textvariable=self.d_prog_var,
                  font=("微软雅黑", 10)).pack(anchor="w")
        self.d_prog_bar = ttk.Progressbar(area, length=400, mode="determinate")
        self.d_prog_bar.pack(anchor="w", pady=(4, 10))

        # 单词信息框
        info = ttk.LabelFrame(area, text="请默写以下单词", padding=12)
        info.pack(fill=tk.X, pady=(0, 10))

        self.d_meaning_lbl = tk.Label(info, text="", font=("微软雅黑", 16, "bold"),
                                      wraplength=500, fg="#1a1a2e")
        self.d_meaning_lbl.pack(anchor="center", pady=(2, 2))

        self.d_pos_lbl = ttk.Label(info, text="", font=("微软雅黑", 10))
        self.d_pos_lbl.pack(anchor="center", pady=1)

        self.d_phonetic_lbl = ttk.Label(info, text="", font=("微软雅黑", 10))
        self.d_phonetic_lbl.pack(anchor="center", pady=(1, 4))

        ttk.Separator(area, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(0, 8))

        # 输入
        ttk.Label(area, text="请输入对应的英文单词：",
                  font=("微软雅黑", 10)).pack(anchor="w")
        self.d_ans_var = tk.StringVar()
        self.d_ans_ent = ttk.Entry(area, textvariable=self.d_ans_var,
                                    font=("微软雅黑", 13), width=30)
        self.d_ans_ent.pack(anchor="w", pady=(4, 6))
        self.d_ans_ent.bind("<Return>", lambda e: self._check_dict_ans())

        # 按钮行
        btn_row = ttk.Frame(area)
        btn_row.pack(anchor="w", pady=(0, 6))
        self.d_btn_submit = ttk.Button(btn_row, text="提交核对", command=self._check_dict_ans)
        self.d_btn_submit.pack(side=tk.LEFT, padx=(0, 8))
        self.d_btn_next = ttk.Button(btn_row, text="下一个 →", command=self._dict_next,
                                     state="disabled")
        self.d_btn_next.pack(side=tk.LEFT)

        # 反馈
        self.d_fb_var = tk.StringVar(value="")
        self.d_fb_lbl = tk.Label(area, textvariable=self.d_fb_var, font=("微软雅黑", 11))
        self.d_fb_lbl.pack(anchor="w")

    def _update_dict_avail(self):
        """更新可用新词数量显示"""
        current_cat = getattr(self, "d_cat_var", None)
        cat_val = current_cat.get() if current_cat else None
        if cat_val:
            cnt = 0
            try:
                self.cursor.execute(
                    "SELECT COUNT(*) FROM words WHERE status=0 AND category=?",
                    (cat_val,),
                )
                cnt = self.cursor.fetchone()[0]
            except: pass
        else:
            cnt = self._count_words(0)
        self.d_avail_lbl.config(text=f"当前词书分类〔{cat_val}〕有 {cnt} 个未学习的新单词可供默写。")

    def _start_dictation(self):
        """开始新词默写会话"""
        try:
            n = int(self.d_num_var.get().strip())
            if n <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("提示", "请输入一个有效的正整数！")
            return

        self.cursor.execute(
            "SELECT id, word, pos, phonetic, meaning, box_level, next_review_time, status "
            "FROM words WHERE status = 0 AND category=? ORDER BY id ASC LIMIT ?",
            (self.d_cat_var.get(), n,),
        )
        words = self.cursor.fetchall()

        if not words:
            messagebox.showinfo("提示", "词库中没有未学习的单词。\n请先切换到「词库录入」标签页添加单词。")
            return

        if len(words) < n:
            messagebox.showinfo("提示", f"目前只有 {len(words)} 个未学习的单词，已全部加载。")

        self.dict_words = words
        self.dict_idx = 0
        self.dict_correct = 0
        self.dict_answered = False

        # 切换到默写界面
        self._dict_setup.pack_forget()
        self._dict_area.pack(fill=tk.BOTH, expand=True)

        self._show_dict_word()

    def _show_dict_word(self):
        """显示当前默写的单词"""
        if self.dict_idx >= len(self.dict_words):
            self._finish_dictation()
            return

        w = self.dict_words[self.dict_idx]
        wid, word, pos, phonetic, meaning, box, nrt, st = w

        total = len(self.dict_words)
        self.d_prog_var.set(f"第 {self.dict_idx + 1} / {total} 个")
        self.d_prog_bar["maximum"] = total
        self.d_prog_bar["value"] = self.dict_idx + 1

        # 解析 JSON definitions 显示多行
        try:
            defs_list = json.loads(meaning) if meaning and meaning.startswith("[") else []
        except:
            defs_list = []
        if not defs_list:
            defs_text = meaning
        else:
            defs_text = "\n".join([f"  【{d.get(chr(112)+chr(111)+chr(115),chr(39))}】{d.get(chr(109)+chr(101)+chr(97)+chr(110)+chr(105)+chr(110)+chr(103),chr(39))}" for d in defs_list])
        self.d_meaning_lbl.config(text=defs_text)
        self.d_pos_lbl.config(text=f"音标：{phonetic if phonetic else chr(39)}")
        self.d_phonetic_lbl.config(text="")
        self.d_pos_lbl.config(text=f"词性：{pos if pos else '（无）'}")
        self.d_phonetic_lbl.config(text="")  # 默写时隐藏音标

        # 重置
        self.d_ans_var.set("")
        self.d_fb_var.set("")
        self.d_fb_lbl.config(fg="black")
        self.d_btn_submit.config(state="normal")
        self.d_btn_next.config(state="disabled")
        self.d_ans_ent.config(state="normal")
        self.d_ans_ent.focus()
        self.dict_answered = False

    def _check_dict_ans(self):
        """核对新词默写答案"""
        if self.dict_answered:
            return

        inp = self.d_ans_var.get().strip()
        if not inp:
            self.d_fb_var.set("  请输入英文单词！")
            self.d_fb_lbl.config(fg="orange")
            return

        w = self.dict_words[self.dict_idx]
        wid, correct_word, pos, phonetic, meaning, box, nrt, st = w
        # 解析 JSON definitions 获取第一个 meaning 用于反馈显示
        try:
            d_list = json.loads(meaning) if meaning and meaning.startswith("[") else []
        except:
            d_list = []
        if d_list:
            meaning = d_list[0].get("meaning", meaning)

        now_ts = int(time.time())
        if _TTS is not None:
            try:
                _TTS.say(correct_word)
                _TTS.runAndWait()
            except:
                pass

        if inp.lower() == correct_word.lower():
            # 拼写正确 → 设置为学习状态，进入 Box 1，1 天后复习
            self.cursor.execute(
                "UPDATE words SET status=1, box_level=1, next_review_time=? WHERE id=?",
                (now_ts + BOX_DAYS[1] * 86400, wid),
            )
            ph = f" [{phonetic}]" if phonetic else ""
            self.d_fb_var.set(f"  正确！{correct_word}{ph} 已加入复习队列（Box 1，明天复习）")
            self.d_fb_lbl.config(fg="green")
            self.dict_correct += 1
            self._record_review_history(wid, 1)
        else:
            # 拼写错误 → 仍保持 status=0（未学习）
            ph = f" [{phonetic}]" if phonetic else ""
            self.d_fb_var.set(f"  错误！正确答案是：{correct_word}{ph}")
            self._record_review_history(wid, 0)
            self.d_fb_lbl.config(fg="red")

        self.conn.commit()
        self.dict_answered = True
        self.d_btn_submit.config(state="disabled")
        self.d_ans_ent.config(state="disabled")
        self.d_btn_next.config(state="normal")
        self.d_btn_next.focus()

    def _dict_next(self):
        """下一个默写单词"""
        self.dict_idx += 1
        self._show_dict_word()

    def _finish_dictation(self):
        """完成新词默写，切换回设置区"""
        self._dict_area.pack_forget()
        self._dict_setup.pack(fill=tk.BOTH, expand=True)

        total = len(self.dict_words)
        pct = f"（{self.dict_correct / total * 100:.0f}%）" if total else ""
        messagebox.showinfo(
            "默写完成",
            f"今日默写结束！\n正确 {self.dict_correct} / {total} 个  {pct}",
        )
        self._update_dict_avail()
        self._refresh_status()

    # ==================== Tab 3: 复习默写 ==================== #

    def _build_tab_review(self, parent):
        """复习默写界面 —— 设置 + 复习区"""
        # ======== 设置区 ========
        setup = ttk.Frame(parent)
        setup.pack(fill=tk.BOTH, expand=True)
        self._rev_setup = setup

        ttk.Label(setup, text="抗遗忘复习默写",
                  font=("微软雅黑", 12, "bold")).pack(anchor="w", pady=(0, 6))

        self.r_info_lbl = ttk.Label(setup, text="", font=("微软雅黑", 10))
        self.r_info_lbl.pack(anchor="w", pady=(0, 8))
        # ---- 词书分类选择 ----
        ttk.Label(setup, text="选择词书分类：", font=("微软雅黑", 10)).pack(anchor="w")
        self.r_cat_var = tk.StringVar(value=self.categories[0] if self.categories else "")
        self.r_cat_cb = ttk.Combobox(setup, textvariable=self.r_cat_var,
                                      values=self.categories,
                                      font=("微软雅黑", 11), width=10, state="readonly")
        self.r_cat_cb.pack(anchor="w", pady=(2, 6))

        # 算法说明
        algo_frame = ttk.LabelFrame(setup, text="递进式多级口袋算法说明", padding=8)
        algo_frame.pack(anchor="w", fill=tk.X, pady=(0, 10))
        algo_text = (
            "• 记忆共 5 级（Box 1→5），间隔天数依次为：1 → 2 → 4 → 7 → 15\n"
            "• 拼写正确 → 升一级；拼写错误 → 重置回 Box 1\n"
            "• 达到 Box 5 并拼写正确后，单词标记为「已掌握」，不再进入复习池"
        )
        tk.Label(algo_frame, text=algo_text, font=("微软雅黑", 9),
                  fg="#444").pack(anchor="w")

        ttk.Button(setup, text="开始复习", command=self._start_review
                   ).pack(anchor="w")

        self._update_rev_info()

        # ======== 复习区（初始隐藏） ========
        area = ttk.Frame(parent)
        self._rev_area = area

        self.r_prog_var = tk.StringVar(value="")
        ttk.Label(area, textvariable=self.r_prog_var,
                  font=("微软雅黑", 10)).pack(anchor="w")
        self.r_prog_bar = ttk.Progressbar(area, length=400, mode="determinate")
        self.r_prog_bar.pack(anchor="w", pady=(4, 10))

        info = ttk.LabelFrame(area, text="请默写以下单词", padding=12)
        info.pack(fill=tk.X, pady=(0, 10))

        self.r_meaning_lbl = tk.Label(info, text="", font=("微软雅黑", 16, "bold"),
                                      wraplength=500, fg="#1a1a2e")
        self.r_meaning_lbl.pack(anchor="center", pady=(2, 2))

        self.r_pos_lbl = ttk.Label(info, text="", font=("微软雅黑", 10))
        self.r_pos_lbl.pack(anchor="center", pady=1)

        self.r_phonetic_lbl = ttk.Label(info, text="", font=("微软雅黑", 10))
        self.r_phonetic_lbl.pack(anchor="center", pady=(1, 4))

        ttk.Separator(area, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(0, 8))

        ttk.Label(area, text="请输入对应的英文单词：",
                  font=("微软雅黑", 10)).pack(anchor="w")
        self.r_ans_var = tk.StringVar()
        self.r_ans_ent = ttk.Entry(area, textvariable=self.r_ans_var,
                                    font=("微软雅黑", 13), width=30)
        self.r_ans_ent.pack(anchor="w", pady=(4, 6))
        self.r_ans_ent.bind("<Return>", lambda e: self._check_rev_ans())

        btn_row = ttk.Frame(area)
        btn_row.pack(anchor="w", pady=(0, 6))
        self.r_btn_submit = ttk.Button(btn_row, text="提交核对", command=self._check_rev_ans)
        self.r_btn_submit.pack(side=tk.LEFT, padx=(0, 8))
        self.r_btn_next = ttk.Button(btn_row, text="下一个 →", command=self._rev_next,
                                     state="disabled")
        self.r_btn_next.pack(side=tk.LEFT)

        self.r_fb_var = tk.StringVar(value="")
        self.r_fb_lbl = tk.Label(area, textvariable=self.r_fb_var, font=("微软雅黑", 11))
        self.r_fb_lbl.pack(anchor="w")

    def _update_rev_info(self):
        """更新复习提示信息"""
        now_ts = int(time.time())
        self.cursor.execute(
            "SELECT COUNT(*) FROM words WHERE status=1 AND category=? AND next_review_time<=?",
            (self.r_cat_var.get(), now_ts,),
        )
        due = self.cursor.fetchone()[0]
        total = self._count_words(1)
        current_cat = getattr(self, "r_cat_var", None)
        cat_name = current_cat.get() if current_cat else "全部"
        self.r_info_lbl.config(
            text=f"当前词书分类〔{cat_name}〕有 {due} 个单词到期待复习（共 {total} 个单词在学习中）。"
        )

    def _start_review(self):
        """开始复习会话"""
        now_ts = int(time.time())
        self.cursor.execute(
            "SELECT id, word, pos, phonetic, meaning, box_level, next_review_time, status "
            "FROM words WHERE status=1 AND category=? AND next_review_time<=? "
            "ORDER BY box_level ASC, next_review_time ASC",
            (self.r_cat_var.get(), now_ts,),
        )
        words = self.cursor.fetchall()

        if not words:
            messagebox.showinfo("提示", "当前没有需要复习的单词！\n\n"
                                        "请先在「词库录入」添加单词，\n"
                                        "然后在「新词默写」中学习并激活单词。")
            return

        self.rev_words = words
        self.rev_idx = 0
        self.rev_correct = 0
        self.rev_answered = False

        self._rev_setup.pack_forget()
        self._rev_area.pack(fill=tk.BOTH, expand=True)

        self._show_rev_word()

    def _show_rev_word(self):
        """显示当前复习的单词"""
        if self.rev_idx >= len(self.rev_words):
            self._finish_review()
            return

        w = self.rev_words[self.rev_idx]
        wid, word, pos, phonetic, meaning, box, nrt, st = w

        total = len(self.rev_words)
        self.r_prog_var.set(f"第 {self.rev_idx + 1} / {total} 个  （当前 Box {box}）")
        self.r_prog_bar["maximum"] = total
        self.r_prog_bar["value"] = self.rev_idx + 1

        # 解析 JSON definitions 显示多行
        try:
            defs_list = json.loads(meaning) if meaning and meaning.startswith(chr(91)) else []
        except:
            defs_list = []
        if not defs_list:
            defs_text = meaning
        else:
            defs_text = chr(10).join([chr(32)*4 + chr(12304) + d.get(chr(112)+chr(111)+chr(115),chr(39)) + chr(12305) + d.get(chr(109)+chr(101)+chr(97)+chr(110)+chr(105)+chr(110)+chr(103),chr(39)) for d in defs_list])
        self.r_meaning_lbl.config(text=defs_text)
        self.r_pos_lbl.config(text=f"音标：" + (phonetic if phonetic else chr(39)))
        self.r_phonetic_lbl.config(text="")
        self.r_pos_lbl.config(text=f"词性：{pos if pos else '（无）'}")
        self.r_phonetic_lbl.config(text="")  # 复习时隐藏音标

        self.r_ans_var.set("")
        self.r_fb_var.set("")
        self.r_fb_lbl.config(fg="black")
        self.r_btn_submit.config(state="normal")
        self.r_btn_next.config(state="disabled")
        self.r_ans_ent.config(state="normal")
        self.r_ans_ent.focus()
        self.rev_answered = False

    def _check_rev_ans(self):
        """核对复习答案 —— 应用 5 级口袋算法"""
        if self.rev_answered:
            return

        inp = self.r_ans_var.get().strip()
        if not inp:
            self.r_fb_var.set("  请输入英文单词！")
            self.r_fb_lbl.config(fg="orange")
            return

        w = self.rev_words[self.rev_idx]
        wid, correct_word, pos, phonetic, meaning, box, nrt, st = w
        # 解析 JSON definitions 获取第一个 meaning
        try:
            d_list = json.loads(meaning) if meaning and meaning.startswith("[") else []
        except:
            d_list = []
        if d_list:
            meaning = d_list[0].get("meaning", meaning)
        now_ts = int(time.time())
        if _TTS is not None:
            try:
                _TTS.say(correct_word)
                _TTS.runAndWait()
            except:
                pass

        if inp.lower() == correct_word.lower():
            # ---- 拼写正确：升级 ----
            new_box = min(box + 1, 5)

            if new_box >= 5 and box >= 5:
                # 已在 Box 5 且正确 → 彻底掌握
                self.cursor.execute(
                    "UPDATE words SET status=2, box_level=5 WHERE id=?",
                    (wid,),
                )
                ph = f" [{phonetic}]" if phonetic else ""
                self.r_fb_var.set(f"  正确！{correct_word}{ph} 已达到 Box 5，标记为「已掌握」！")
                self.r_fb_lbl.config(fg="green")
                self._record_review_history(wid, 1)
            else:
                days = BOX_DAYS[new_box]
                nrt = now_ts + days * 86400
                self.cursor.execute(
                    "UPDATE words SET box_level=?, next_review_time=? WHERE id=?",
                    (new_box, nrt, wid),
                )
                ph = f" [{phonetic}]" if phonetic else ""
                self.r_fb_var.set(
                    f"  正确！{correct_word}{ph} 升至 Box {new_box}，将在 {days} 天后再次复习。"
                )
                self.r_fb_lbl.config(fg="green")
                self._record_review_history(wid, 1)

            self.rev_correct += 1
        else:
            # ---- 拼写错误：重置为 Box 1 ----
            nrt = now_ts + BOX_DAYS[1] * 86400
            self.cursor.execute(
                "UPDATE words SET box_level=1, next_review_time=? WHERE id=?",
                (nrt, wid),
            )
            ph = f" [{phonetic}]" if phonetic else ""
            self.r_fb_var.set(f"  错误！正确答案是：{correct_word}{ph}  （已重置为 Box 1，明日需重新默写）")
            self.r_fb_lbl.config(fg="red")
            self._record_review_history(wid, 0)

        self.conn.commit()
        self.rev_answered = True
        self.r_btn_submit.config(state="disabled")
        self.r_ans_ent.config(state="disabled")
        self.r_btn_next.config(state="normal")
        self.r_btn_next.focus()

    def _rev_next(self):
        """下一个复习单词"""
        self.rev_idx += 1
        self._show_rev_word()

    def _finish_review(self):
        """完成复习，切换回设置区"""
        self._rev_area.pack_forget()
        self._rev_setup.pack(fill=tk.BOTH, expand=True)

        total = len(self.rev_words)
        pct = f"（{self.rev_correct / total * 100:.0f}%）" if total else ""
        messagebox.showinfo(
            "复习完成",
            f"复习结束！\n正确 {self.rev_correct} / {total} 个  {pct}",
        )
        self._update_rev_info()
        self._refresh_status()


# ==================== Tab 4: 批量导入 ==================== #

    def _record_review_history(self, word_id, result):
        """向 review_history 表中插入一条记录"""
        now_ts = int(time.time())
        self.cursor.execute(
            "INSERT INTO review_history (word_id, review_time, result) VALUES (?, ?, ?)",
            (word_id, now_ts, result),
        )
        self.conn.commit()
        self.conn.commit()

    def _build_tab_manage(self, parent):
        """词库管理界面：左侧表格 + 右侧详情面板"""
        # Dashboard frame
        self.dash_frame = ttk.LabelFrame(parent, text="数据看板", padding=8)
        self.dash_frame.pack(fill=tk.X, pady=(0, 6))

        paned = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # ======== 左栏：TreeView 表格 ========
        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=2)

        tool_bar = ttk.Frame(left_frame)
        tool_bar.pack(fill=tk.X, pady=(0, 4))

        ttk.Button(tool_bar, text="刷新列表", command=self._refresh_tree
                   ).pack(side=tk.LEFT, padx=(0, 6))

        self.mgr_status_var = tk.StringVar(value="")
        tk.Label(tool_bar, textvariable=self.mgr_status_var,
                 font=("微软雅黑", 9), fg="gray").pack(side=tk.LEFT)

        tree_frame = ttk.Frame(left_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("word", "pos", "meaning", "category", "box", "status")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings",
                                 selectmode="browse")

        self.tree.heading("word", text="单词")
        self.tree.heading("pos", text="词性")
        self.tree.heading("meaning", text="释义")
        self.tree.heading("category", text="所属词书")
        self.tree.heading("box", text="记忆阶段")
        self.tree.heading("status", text="掌握状态")

        self.tree.column("word", width=120, minwidth=80)
        self.tree.column("pos", width=60, minwidth=40)
        self.tree.column("meaning", width=130, minwidth=60)
        self.tree.column("category", width=60, minwidth=40)
        self.tree.column("box", width=80, minwidth=50)
        self.tree.column("status", width=80, minwidth=50)

        tree_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL,
                                    command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Double-1>", lambda e: self._edit_word_dialog(int(self.tree.selection()[0])) if self.tree.selection() else None)

        # ======== 右栏：详细信息与历史 ========
        right_frame = ttk.LabelFrame(paned, text="详细信息与默写历史", padding=6)
        paned.add(right_frame, weight=1)

        self.mgr_info_var = tk.StringVar(value="请从左侧选择一个单词")
        tk.Label(right_frame, textvariable=self.mgr_info_var,
                 font=("微软雅黑", 10, "bold"), wraplength=200,
                 justify=tk.LEFT).pack(anchor="w", pady=(0, 6))

        ttk.Label(right_frame, text="默写记录：", font=("微软雅黑", 9)
                  ).pack(anchor="w")

        hist_frame = ttk.Frame(right_frame)
        hist_frame.pack(fill=tk.BOTH, expand=True)

        hist_scroll = ttk.Scrollbar(hist_frame, orient=tk.VERTICAL)
        hist_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.hist_list = tk.Listbox(hist_frame, font=("微软雅黑", 9),
                                    yscrollcommand=hist_scroll.set,
                                    relief=tk.SUNKEN, bd=1)
        self.hist_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        hist_scroll.config(command=self.hist_list.yview)

        self._draw_dashboard()

        # Action buttons

        mgmt_toolbar_frame = ttk.Frame(parent)
        mgmt_toolbar_frame.pack(side=tk.TOP, fill=tk.X, pady=10)

        row1 = ttk.Frame(mgmt_toolbar_frame)
        row1.pack(fill=tk.X, pady=2)
        tk.Label(row1, text="🛠️ 单词管理：", font=("Segoe UI", 9), fg="#636E72", bg="#F0F2F5").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(row1, text="✏️ 修改选中单词", command=self._edit_selected_word).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(row1, text="❌ 删除选中单词", command=self._delete_word).pack(side=tk.LEFT, padx=(4, 0))

        row2 = ttk.Frame(mgmt_toolbar_frame)
        row2.pack(fill=tk.X, pady=2)
        tk.Label(row2, text="📂 词书管理：", font=("Segoe UI", 9), fg="#636E72", bg="#F0F2F5").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(row2, text="📝 重命名所属词书", command=self._rename_category).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(row2, text="🗑️ 删除整本词书", command=self._delete_category).pack(side=tk.LEFT, padx=(4, 0))

        btn_bar = ttk.Frame(parent)
        btn_bar.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(btn_bar, text="备份数据库", style="Accent.TButton",
                   command=self._backup_db).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_bar, text="导出为 CSV", style="Accent.TButton",
                   command=self._export_csv).pack(side=tk.LEFT)
        ttk.Button(btn_bar, text="🚨 彻底销毁所有数据 (不可逆)", style="Danger.TButton", command=self._destroy_all_data).pack(side=tk.LEFT, padx=(8, 0))


        self._refresh_tree()

    def _refresh_tree(self):
        """刷新左侧 TreeView 表格"""
        for item in self.tree.get_children():
            self.tree.delete(item)
        try:
            self.cursor.execute(
                "SELECT id, word, pos, meaning, category, definitions, box_level, status FROM words ORDER BY id"
            )
            rows = self.cursor.fetchall()
            for row in rows:
                wid, word, pos, meaning, category, defs_json, box, status = row
                # 解析 JSON definitions，拼接显示
                try:
                    defs_list = json.loads(defs_json) if defs_json else []
                    meaning_display = " | ".join([f"{d.get('pos','')} {d.get('meaning','')}" for d in defs_list])
                except:
                    meaning_display = meaning
                status_map = {0: "未学习", 1: "复习中", 2: "已掌握"}
                box_label = f"Box {box}"
                self.tree.insert("", tk.END, iid=str(wid),
                                 values=(word, pos, meaning_display, category, box_label,
                                         status_map.get(status, "未知")))
            self.mgr_status_var.set(f"共 {len(rows)} 个单词")
            self._draw_dashboard()
        except Exception as e:
            self.mgr_status_var.set(f"加载失败: {e}")

    def _on_tree_select(self, event):
        """TreeView 选择事件：刷新右侧详情"""
        sel = self.tree.selection()
        if not sel:
            return
        wid = int(sel[0])

        self.cursor.execute(
            "SELECT word, pos, phonetic, meaning, category, definitions, box_level, status FROM words WHERE id=?",
            (wid,),
        )
        row = self.cursor.fetchone()
        if not row:
            return
        word, pos, phonetic, meaning, category, defs_json, box, status = row
        status_map = {0: "未学习", 1: "复习中", 2: "已掌握"}
        info = (
            f"英文：{word}\n"
            f"词性：{pos if pos else '（无）'}\n"
            f"音标：{phonetic if phonetic else '（无）'}\n"
            f"中文：{meaning}\n"
            f"级别：Box {box}\n"
            f"状态：{status_map.get(status, '未知')}"
        )
        self.mgr_info_var.set(info)

        self.hist_list.delete(0, tk.END)
        self.cursor.execute(
            "SELECT review_time, result FROM review_history "
            "WHERE word_id=? ORDER BY review_time DESC",
            (wid,),
        )
        hist_rows = self.cursor.fetchall()
        if not hist_rows:
            self.hist_list.insert(tk.END, "  暂无默写记录")
        else:
            for rt, result in hist_rows:
                from datetime import datetime
                dt_str = datetime.fromtimestamp(rt).strftime("%Y-%m-%d %H:%M")
                res_str = "正确" if result else "错误"
                self.hist_list.insert(tk.END, f"  {dt_str}  {res_str}")


    def _edit_word_dialog(self, word_id):
        """弹出模态对话框编辑单词"""
        self.cursor.execute(
            "SELECT word, pos, phonetic, meaning, category, definitions, box_level, status FROM words WHERE id=?",
            (word_id,),
        )
        row = self.cursor.fetchone()
        if not row:
            return
        old_word, old_pos, old_phonetic, old_meaning, old_cat, old_defs_json, old_box, old_status = row
        try:
            edit_defs_list = json.loads(old_defs_json) if old_defs_json else []
        except:
            edit_defs_list = [{"pos": old_pos, "meaning": old_meaning}]

        dlg = tk.Toplevel(self.root)
        dlg.title("修改单词")
        dlg.geometry("420x350")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()

        f = ttk.Frame(dlg, padding=12)
        f.pack(fill=tk.BOTH, expand=True)

        ttk.Label(f, text="英文：", font=("微软雅黑", 10)).grid(row=0, column=0, sticky="e", padx=(0, 6), pady=3)
        w_v = tk.StringVar(value=old_word)
        ttk.Entry(f, textvariable=w_v, font=("微软雅黑", 11), width=25).grid(row=0, column=1, sticky="w", pady=3)

        ttk.Label(f, text="词性：", font=("微软雅黑", 10)).grid(row=1, column=0, sticky="e", padx=(0, 6), pady=3)
        p_v = tk.StringVar(value=old_pos)
        ttk.Entry(f, textvariable=p_v, font=("微软雅黑", 11), width=25).grid(row=1, column=1, sticky="w", pady=3)

        ttk.Label(f, text="音标：", font=("微软雅黑", 10)).grid(row=2, column=0, sticky="e", padx=(0, 6), pady=3)
        ph_v = tk.StringVar(value=old_phonetic)
        ttk.Entry(f, textvariable=ph_v, font=("微软雅黑", 11), width=25).grid(row=2, column=1, sticky="w", pady=3)

        ttk.Label(f, text="释义（每行: 词性|意思）：", font=("微软雅黑", 10)).grid(row=3, column=0, sticky="ne", padx=(0, 6), pady=3)
        edit_defs_text = tk.Text(f, height=4, width=25, font=("微软雅黑", 11),
                                   bg="#FFFFFF", fg="#2D3436", relief=tk.SUNKEN, bd=1)
        edit_defs_text.grid(row=3, column=1, sticky="w", pady=3)
        # 预填现有释义
        edit_defs_text.delete("1.0", tk.END)
        for ed in edit_defs_list:
            edit_defs_text.insert(tk.END, f"{ed.get('pos','')}|{ed.get('meaning','')}\n")

        ttk.Label(f, text="词书分类：", font=("微软雅黑", 10)).grid(row=4, column=0, sticky="e", padx=(0, 6), pady=3)
        c_v = tk.StringVar(value=old_cat if old_cat else "\u516b\u4e0b")
        ttk.Combobox(f, textvariable=c_v,
                     values=["\u4e03\u4e0a", "\u4e03\u4e0b", "\u516b\u4e0a", "\u516b\u4e0b"],
                     font=("微软雅黑", 11), width=10, state="readonly").grid(row=4, column=1, sticky="w", pady=3)

        def save():
            nw = w_v.get().strip()
            np_ = p_v.get().strip()
            nph = ph_v.get().strip()
            nm = m_v.get().strip()
            nc = c_v.get()
            if not nw or not nm:
                messagebox.showwarning("\u63d0\u793a", "\u82f1\u6587\u548c\u4e2d\u6587\u4e0d\u80fd\u4e3a\u7a7a\uff01", parent=dlg)
                return
            try:
                self.cursor.execute(
                    "UPDATE words SET word=?, pos=?, phonetic=?, meaning=?, category=?, definitions=? WHERE id=?",
                    (nw, first_pos2, nph, first_meaning2, nc, save_defs_json, word_id),
                )
                self.conn.commit()
                self._refresh_tree()
                self._on_tree_select(None)
                dlg.destroy()
            except Exception as e:
                messagebox.showerror("\u9519\u8bef", f"\u4fdd\u5b58\u5931\u8d25\uff1a{e}", parent=dlg)

        bf = ttk.Frame(f)
        bf.grid(row=5, column=0, columnspan=2, pady=(12, 0))
        ttk.Button(bf, text="\u4fdd\u5b58", command=save).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(bf, text="\u53d6\u6d88", command=dlg.destroy).pack(side=tk.LEFT)
        dlg.bind("<Return>", lambda e: save())
        dlg.wait_window()

# ================================================================
#  入口
# ================================================================





    def _backup_db(self):
        """备份数据库"""
        try:
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            dst = self.db_path.replace(".db", f"_backup_{ts}.db")
            shutil.copy2(self.db_path, dst)
            messagebox.showinfo("备份完成", f"已备份至：\n{dst}")
        except Exception as e:
            messagebox.showerror("备份失败", str(e))
    def _do_batch_import(self):
        raw = self.batch_text.get("1.0", tk.END).strip()
        if not raw:
            messagebox.showwarning("提示", "请先粘贴要导入的数据！")
            return
        lines = raw.splitlines()
        if not lines:
            self.batch_fb_var.set("  未检测到有效数据")
            return
        cat = self.b_cat_var.get()
        now_ts = int(time.time())
        success = 0
        errors = []
        for i, line in enumerate(lines, 1):
            line = line.strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 4:
                errors.append("第{}".format(i) + "行字段不足: " + line[:50])
                continue
            word, pos_str, phonetic, meaning_str = parts[0], parts[1], parts[2], parts[3]
            if not word or not meaning_str:
                errors.append("第{}".format(i) + "行: 单词或中文意思为空")
                continue
            # 解析多个词性+意思，支持格式：单词|词性1.意思1 |词性2.意思2|音标|词书分类
            # JSON definitions: [{"pos":"v.","meaning":"预言"},{"pos":"n.","meaning":"预测的能力"}]
            defs_list = []
            for seg in meaning_str.split("/"):
                seg = seg.strip()
                if not seg:
                    continue
                if " " in seg:
                    sp, sm = seg.split(" ", 1)
                    defs_list.append({"pos": sp.strip(), "meaning": sm.strip()})
                else:
                    defs_list.append({"pos": seg, "meaning": ""})
            if not defs_list:
                defs_list = [{"pos": pos_str, "meaning": meaning_str}]
            defs_json = json.dumps(defs_list, ensure_ascii=False)
            first_pos = defs_list[0].get("pos", pos_str)
            first_meaning = defs_list[0].get("meaning", meaning_str)
            try:
                self.cursor.execute(
                    "INSERT INTO words (word,pos,phonetic,meaning,category,definitions,box_level,next_review_time,status) "
                    "VALUES (?,?,?,?,?,?,1,?,0)",
                    (word, first_pos, phonetic, first_meaning, cat, defs_json, now_ts),
                )
                success += 1
            except Exception as e:
                errors.append("第{}".format(i) + "行写入失败: {}".format(i, e))
        self.conn.commit()
        self._refresh_status()
        self._refresh_entry_list()
        msg = "  导入完成：成功{}".format(success) + "个"
        if errors:
            msg += "，失败{}".format(len(errors)) + "个"
            dlines = errors[:10]
            if len(errors) > 10:
                dlines.append("...共{}".format(len(errors)) + "条错误")
            detail = "\n".join(dlines)
            messagebox.showwarning("导入结果",
                "成功{}".format(success) + "个，失败{}".format(len(errors)) + "个．" + "\n\n详情：\n" + detail)
        else:
            messagebox.showinfo("导入完成", "成功导入{}".format(success) + "个单词！")
        self.batch_fb_var.set(msg)
    def _clear_all_data(self):
        if not messagebox.askyesno("确认清空", "确定要清空所有数据吗？\n此操作不可撤销！", icon="warning"):
            return
        try:
            self.cursor.execute("DELETE FROM words")
            self.cursor.execute("DELETE FROM review_history")
            self.conn.commit()
            self._refresh_tree()
            self._refresh_status()
            self._refresh_entry_list()
            messagebox.showinfo("已清空", "所有数据已清除。")
        except Exception as e:
            messagebox.showerror("错误", "清空失败：{}".format(e))

    def _add_category(self):
        from tkinter import simpledialog
        name = simpledialog.askstring("新建词书分类", "请输入新词书分类名称：", parent=self.root)
        if not name:
            return
        name = name.strip()
        if not name:
            messagebox.showwarning("提示", "词书分类名称不能为空！")
            return
        if name in self.categories:
            messagebox.showwarning("提示", f"词书分类「{name}」已存在！")
            return
        self.categories.append(name)
        for cb_attr in ["e_cat_cb", "b_cat_cb", "d_cat_cb", "r_cat_cb"]:
            if hasattr(self, cb_attr):
                try:
                    getattr(self, cb_attr).configure(values=self.categories)
                except:
                    pass
        messagebox.showinfo("完成", f"词书分类「{name}」已创建！")

    def _refresh_categories(self):
        self.cursor.execute("SELECT DISTINCT category FROM words WHERE category != '' ORDER BY category")
        db_cats = [r[0] for r in self.cursor.fetchall()]
        # Merge DB categories into self.categories without duplicates
        for c in db_cats:
            if c not in self.categories:
                self.categories.append(c)
        for cb_attr in ["e_cat_cb", "b_cat_cb", "d_cat_cb", "r_cat_cb"]:
            if hasattr(self, cb_attr):
                try:
                    getattr(self, cb_attr).configure(values=self.categories)
                except:
                    pass

    
    def show_format_help(self):
        msg = ("📌 【单条录入规则】\n"
               "在“词性与释义”框中\n"
               "• 单一意思：直接写（例：n. 苹果）\n"
               "• 多个意思：用斜杠 / 分隔（例：v. 领导 / n. 领先）\n\n"
               "📦 【批量导入格式】（每行一条，必须用竖线 | 分隔）\n"
               "格式：单词|音标|词性与释义\n"
               "• 基础版：predict|/prɪˈdɪkt/|v. 预测\n"
               "• 进阶版：lead|/liːd/|v. 领导 / n. 领先\n\n"
               "注：导入时无需在文本中写分册，直接在右侧下拉框选择即可。")
        from tkinter import messagebox
        messagebox.showinfo("单词录入与导入指南", msg)

    def _delete_word(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请先选择一个单词！")
            return
        wid = int(sel[0])
        self.cursor.execute("SELECT word FROM words WHERE id=?", (wid,))
        row = self.cursor.fetchone()
        if not row:
            return
        word = row[0]
        if messagebox.askyesno("确认删除", f"确定要删除「{word}」吗？\n此操作不可撤销！", icon="warning"):
            self.cursor.execute("DELETE FROM words WHERE id=?", (wid,))
            self.cursor.execute("DELETE FROM review_history WHERE word_id=?", (wid,))
            self.conn.commit()
            self.notify_all_tabs_data_changed()


            messagebox.showinfo("已删除", f"单词「{word}」已删除。")

    def _rename_category(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请先选择一个单词！")
            return
        wid = int(sel[0])
        self.cursor.execute("SELECT category FROM words WHERE id=?", (wid,))
        row = self.cursor.fetchone()
        if not row:
            return
        old_cat = row[0] or ""
        if not old_cat:
            messagebox.showwarning("提示", "该单词没有所属词书！")
            return
        from tkinter import simpledialog
        new_cat = simpledialog.askstring("重命名词书", f"将「{old_cat}」重命名为：", initialvalue=old_cat, parent=self.root)
        if not new_cat:
            return
        new_cat = new_cat.strip()
        if not new_cat:
            messagebox.showwarning("提示", "名称不能为空！")
            return
        if new_cat == old_cat:
            return
        self.cursor.execute("UPDATE words SET category=? WHERE category=?", (new_cat, old_cat))
        self.conn.commit()
        if old_cat in self.categories:
            self.categories.remove(old_cat)
        self.categories.append(new_cat)
        for cb_attr in ["e_cat_cb", "b_cat_cb", "d_cat_cb", "r_cat_cb"]:
            if hasattr(self, cb_attr):
                try:
                    getattr(self, cb_attr).configure(values=self.categories)
                except:
                    pass
        self._refresh_tree()
        self._refresh_status()
        messagebox.showinfo("已完成", f"词书「{old_cat}」已重命名为「{new_cat}」。")

    def _delete_category(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请先选择一个单词！")
            return
        wid = int(sel[0])
        self.cursor.execute("SELECT category FROM words WHERE id=?", (wid,))
        row = self.cursor.fetchone()
        if not row:
            return
        cat = row[0] or ""
        if not cat:
            messagebox.showwarning("提示", "该单词没有所属词书！")
            return
        count = self.cursor.execute("SELECT COUNT(*) FROM words WHERE category=?", (cat,)).fetchone()[0]
        if not messagebox.askyesno("确认删除", f"确定要删除整本词书「{cat}」吗？\n将删除该分类下的全部 {count} 个单词，此操作不可撤销！", icon="warning"):
            return
        self.cursor.execute("DELETE FROM review_history WHERE word_id IN (SELECT id FROM words WHERE category=?)", (cat,))
        self.cursor.execute("DELETE FROM words WHERE category=?", (cat,))
        self.conn.commit()
        if cat in self.categories:
            self.categories.remove(cat)
        for cb_attr in ["e_cat_cb", "b_cat_cb", "d_cat_cb", "r_cat_cb"]:
            if hasattr(self, cb_attr):
                try:
                    getattr(self, cb_attr).configure(values=self.categories)
                except:
                    pass
        self._refresh_tree()
        self._refresh_status()
        self._refresh_entry_list()
        messagebox.showinfo("已删除", f"整本词书「{cat}」及其全部单词已删除。")

    def _destroy_all_data(self):
        if not messagebox.askyesno("确认销毁", "确定要彻底销毁所有数据吗？\n此操作不可逆！", icon="warning"):
            return
        if not messagebox.askyesno("再次确认", "这将删除所有单词和历史记录。\n确定继续吗？", icon="warning"):
            return
        try:
            self.cursor.execute("DELETE FROM words")
            self.cursor.execute("DELETE FROM review_history")
            self.conn.commit()
            self.categories = []
            self.notify_all_tabs_data_changed()
            messagebox.showinfo("已销毁", "所有数据已彻底销毁，词书列表已清空。")
        except Exception as e:
            messagebox.showerror("错误", f"销毁失败：{e}")
    def _edit_selected_word(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请先在上方列表中点击选中一个单词！")
            return
        try:
            self._edit_word_dialog(int(sel[0]))
        except Exception as e:
            import traceback
            messagebox.showerror("错误", f"打开编辑窗口失败：\n{e}")
    def notify_all_tabs_data_changed(self):
        self.cursor.execute("SELECT DISTINCT category FROM words WHERE category != '' ORDER BY category")
        db_cats = [r[0] for r in self.cursor.fetchall()]
        self.categories = db_cats
        for cb_attr, sv_attr in [("e_cat_cb", "e_cat_var"), ("b_cat_cb", "b_cat_var"),
                                   ("d_cat_cb", "d_cat_var"), ("r_cat_cb", "r_cat_var")]:
            if hasattr(self, cb_attr):
                try:
                    getattr(self, cb_attr).configure(values=self.categories)
                except:
                    pass
            if hasattr(self, sv_attr):
                try:
                    sv = getattr(self, sv_attr)
                    if self.categories:
                        if sv.get() not in self.categories:
                            sv.set(self.categories[0])
                    else:
                        sv.set("")
                except:
                    pass
        self._refresh_tree()
        self._refresh_status()
        self._refresh_entry_list()
        self._draw_dashboard()
        self._update_dict_avail()
        self._update_rev_info()


    def _draw_dashboard(self):
        if not hasattr(self, "dash_frame") or self.dash_frame is None:
            return
        for w in self.dash_frame.winfo_children():
            w.destroy()

        box_counts = {}
        for b in range(1, 6):
            self.cursor.execute("SELECT COUNT(*) FROM words WHERE box_level=? AND status=1", (b,))
            box_counts[b] = self.cursor.fetchone()[0]
        self.cursor.execute("SELECT COUNT(*) FROM words WHERE status=0")
        box_counts[0] = self.cursor.fetchone()[0]
        self.cursor.execute("SELECT COUNT(*) FROM words WHERE status=2")
        box_counts["m"] = self.cursor.fetchone()[0]

        self.cursor.execute("SELECT category, COUNT(*), SUM(CASE WHEN status=2 THEN 1 ELSE 0 END) FROM words GROUP BY category ORDER BY category")
        data = self.cursor.fetchall()

        tk.Label(self.dash_frame, text="词书分类通关率",
                 font=("Segoe UI", 10, "bold"), fg="#2D3436", bg="#F0F2F5").pack(anchor="w")
        colors = ["#3498DB", "#2ECC71", "#F39C12", "#E74C3C"]
        for i, (cat, t, m) in enumerate(data):
            pct = (m / t * 100) if t > 0 else 0
            cf = ttk.Frame(self.dash_frame)
            cf.pack(fill=tk.X, pady=1)
            tk.Label(cf, text=f"{cat}:", font=("Segoe UI", 9),
                     fg="#2D3436", bg="#F0F2F5").pack(side=tk.LEFT)
            cv = tk.Canvas(cf, width=260, height=16, bg="#FFFFFF", highlightthickness=0)
            cv.pack(side=tk.LEFT, padx=(0, 6))
            fw = int(260 * pct / 100)
            cv.create_rectangle(0, 0, fw, 16, fill=colors[i % 4], outline="")
            cv.create_rectangle(0, 0, 260, 16, outline="#DDD", width=1)
            cv.create_text(130, 8, text=f"{m}/{t} ({int(pct)}%)",
                           font=("Segoe UI", 8), fill="#FFF" if pct > 30 else "#2D3436")

        ttk.Separator(self.dash_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(4, 4))
        tk.Label(self.dash_frame, text="记忆分布 (Box 1-5 + 未学 + 已掌握)",
                 font=("Segoe UI", 10, "bold"), fg="#2D3436", bg="#F0F2F5").pack(anchor="w")

        mx = max(list(box_counts.values()) + [1])
        bf = ttk.Frame(self.dash_frame)
        bf.pack(fill=tk.X, pady=(2, 0))
        cv2 = tk.Canvas(bf, width=560, height=138, bg="#FFFFFF", highlightthickness=0)
        cv2.pack()
        lm = {0: "未学", 1: "Box1", 2: "Box2", 3: "Box3", 4: "Box4", 5: "Box5", "m": "掌握"}
        bc = {0: "#95A5A6", 1: "#E74C3C", 2: "#E67E22", 3: "#F1C40F",
              4: "#2ECC71", 5: "#3498DB", "m": "#9B59B6"}
        keys = [0, 1, 2, 3, 4, 5, "m"]
        gap = 10
        bw = min(45, (560 - gap * 8) // 7)
        for j, k in enumerate(keys):
            cnt = box_counts.get(k, 0)
            bh = int((cnt / mx) * 110) if mx > 0 else 0
            x = gap + j * (bw + gap)
            cv2.create_rectangle(x, 110 - bh, x + bw, 110, fill=bc.get(k, "#CCC"), outline="")
            cv2.create_text(x + bw // 2, 122, text=lm.get(k, str(k)),
                            font=("Segoe UI", 8), fill="#2D3436")
            if cnt > 0:
                cv2.create_text(x + bw // 2, max(0, 104 - bh), text=str(cnt),
                                font=("Segoe UI", 9, "bold"), fill=bc.get(k, "#000"))

    def _export_csv(self):
        from tkinter import filedialog
        import csv, datetime
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        fp = filedialog.asksaveasfilename(defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialfile="vocab_export_" + ts + ".csv",
            title="\u5bfc\u51fa\u8bcd\u5e93\u4e3a CSV")
        if not fp:
            return
        sql = "SELECT word, pos, phonetic, meaning, category, box_level, "
        sql += "CASE WHEN status=0 THEN '\u672a\u5b66\u4e60' WHEN status=1 THEN '\u590d\u4e60\u4e2d' ELSE '\u5df2\u638c\u63e1' END "
        sql += "FROM words ORDER BY id"
        self.cursor.execute(sql)
        rows = self.cursor.fetchall()
        with open(fp, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["\u82f1\u6587", "\u8bcd\u6027", "\u97f3\u6807", "\u4e2d\u6587", "\u5206\u518c", "Box\u7ea7\u522b", "\u72b6\u6001"])
            w.writerows(rows)
        messagebox.showinfo("\u5bfc\u51fa\u6210\u529f",
            "\u5df2\u5bfc\u51fa " + str(len(rows)) + " \u6761\u8bb0\u5f55")
def main():
    try:
        root = tk.Tk()

        # Windows DPI 适配（让界面在高分屏上不模糊）
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

        app = VocabApp(root)
        root.mainloop()
    except Exception as e:
        import traceback
        err_msg = traceback.format_exc()
        try:
            from tkinter import messagebox
            messagebox.showerror("启动失败", "程序启动时发生错误：\n\n" + err_msg)
        except Exception:
            print("程序启动失败：", err_msg)


if __name__ == "__main__":
    main()
