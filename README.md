# 📝 VocabMaster: Intelligent Vocabulary Dictation & Review System
## Final Production Technical Architecture & Operations Report

* **Project Version:** Production Ready (Final Stable Release)
* **Code Scale:** Monolithic Single-file (1,299 lines / 50,938 bytes)
* **Core Architecture:** Python 3.x + Tkinter (ttk) + SQLite3
* **Hardware Dependencies:** Zero (Smart decoupling with native system-level offline TTS fallback)
* **Cross-Platform Compatibility:** Windows / macOS / Linux

---

## 1. Software Architecture & File Manifest

The system implements a **Monolithic Single-file** architecture. State persistence is managed through a local lightweight database, paired with a dedicated batch launcher for seamless background execution.

### 1.1 File Manifest & Responsibility Matrix

| Filename | File Type | Core Responsibility Description |
| :--- | :--- | :--- |
| **`main.py`** | Python Source Code | The core application engine. Houses 35 cohesive business methods driving the UI rendering, SQLite operations, Spaced Repetition algorithms, and offline pronunciation pipelines. |
| **`run.bat`** | Windows Batch Script | Production environment launcher. Explicitly forces the system code page to `UTF-8` (`chcp 65001`) and invokes `pythonw.exe` to suppress the background terminal window completely. |
| **`vocab_data.db`** | SQLite Database | Local single-file database. Automatically initialized upon the first run with zero user configuration required. Stores user vocabularies and detailed review timelines. |

### 1.2 Startup Sequence & Lifecycle Chain

```text
[User double-clicks run.bat] 
       │
       ▼ (Forces UTF-8 Code Page & Invokes pythonw.exe)
[Executes main.py -> main()]
       │
       ▼ (Spawns the Tkinter main event loop)
[Initializes VocabApp(root)]
       ├── 1. Execute _init_db()      --> DB initialization, schema migration & intelligent data clustering
       ├── 2. Execute _setup_style()  --> Global flat-style UI styling injection & micro-margin tailoring
       └── 3. Execute _build_ui()     --> Modular rendering of the 5 functional interaction tabs

```

---

## 2. Database Design (SQLite Schema)

The database layers state management using two core tables bound by a strict **One-to-Many** foreign key constraint, tracking both current learning indices and historical performance trajectories.

### 2.1 The Master Vocabulary Table (`words`)

```sql
CREATE TABLE IF NOT EXISTS words (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    word             TEXT    NOT NULL,
    pos              TEXT    DEFAULT '',
    phonetic         TEXT    DEFAULT '',
    meaning          TEXT    DEFAULT '',
    box_level        INTEGER DEFAULT 1,
    next_review_time INTEGER DEFAULT 0,
    status           INTEGER DEFAULT 0,
    category         TEXT    DEFAULT ''
);

```

#### 🛠️ Live Data Migration & Fault Tolerance

To guarantee seamless backward compatibility, the initialization lifecycle checks for schema updates dynamically without corrupting existing records:

```python
try:
    self.cursor.execute("ALTER TABLE words ADD COLUMN category TEXT DEFAULT ''")
except sqlite3.OperationalError:
    pass # Column already exists, bypass safely

```

### 2.2 The Review Timeline Logs (`review_history`)

```sql
CREATE TABLE IF NOT EXISTS review_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    word_id     INTEGER NOT NULL,
    review_time INTEGER NOT NULL,
    result      INTEGER NOT NULL,
    FOREIGN KEY (word_id) REFERENCES words(id)
);

```

> **📊 Interface Reactive Linkage:** `review_history.word_id` is linked to `words.id`. When a user selects a word in the Control Panel, the system invokes an aggregated `SELECT ... ORDER BY review_time DESC` query to populate the item's historical time-axis panel instantly.

---

## 3. Core Algorithms Deep Dive

### 3.1 Adaptive Multi-Box Spaced Repetition Engine

The engine ditches traditional sequential learning in favor of a 5-Box Leitner-inspired Spaced Repetition scheduler. Each box introduces an expanding cooling-off period tailored to counteract the Ebbinghaus forgetting curve:

```python
BOX_DAYS = {1: 1, 2: 2, 3: 4, 4: 7, 5: 15}
# Epoch Calculation: Current Unix Timestamp + (Target Box Days × 86400 Seconds)
next_review_time = int(time.time()) + BOX_DAYS[new_box] * 86400

```

#### 🔄 Dynamic State Machine Transitions

1. **New Word Dictation Mode (`dictation`):**
* Completing an initial test changes its state (`status=1`) and routes it directly to **Box 1**, scheduling its first forced review for exactly 24 hours later.


2. **Review Mode (`review`):**
* **Flawless Recall (Correct Answer & No Hints Used):** Increments `box_level` by 1. Once a word clears **Box 5** (passing the 15-day retention threshold), it gets marked as Mastered (`status=2`) and exits the active review loop.
* **Hard Reset Penalty (Incorrect Answer):** Triggers a strict reset mechanism. **Regardless of whether a word is in Box 4 or Box 5, it is instantly demoted to Box 1**. Its next review window resets to tomorrow, forcing a re-evaluation within 24 hours.



### 3.2 Cheating Prevention & Hint Penalty Systems

To prevent users from inflating memory scores using hints, the session tracking layer introduces a stealth state flag called `session_hint_used`:

```python
def _show_hint(self):
    if self.session_answered: return
    w = self.session_words[self.session_idx]
    correct_word = w[1]
    # Dynamically map characters to an equivalent string of blank underlines
    hint = " ".join("_" * len(correct_word))
    self.d_fb_var.set(f"Hint: {hint}")
    self.session_hint_used = True

```

> **⚖️ Penalty Enforcement Logic:** If the hint event is triggered during a word's lifecycle, the system flags the current card. Even if the user enters the correct spelling afterward, the upgrade path is blocked: `new_box = current_box`. The level stays locked, and the review period is only given a minor extension, forcing the user to re-evaluate it down the line.

---

## 4. UI Visual Style & Layout Architecture

### 4.1 Flat Modern Palette Design (ttk.Style)

The interface replaces traditional Tkinter styling with a flat, high-contrast, minimalist palette optimized for long study sessions without causing eye strain:

* **🎨 Base Canvas Tint:** `BG = "#F0F2F5"` (Soft, glare-reducing modern gray)
* **⬜ Workspace Cards:** `CARD = "#FFFFFF"` (Crisp, clean paper-white container style)
* **🟦 Focal Anchor:** `ACC = "#0984E3"` (Tech blue used for active tabs, focus, and main actions)
* **🟩 Success Metric:** `SUC = "#00B894"` (Mint green signaling accurate spelling feedback)
* **🟥 Alert Coral:** `DNG = "#D63031"` (Vibrant coral red signaling typo errors or file overrides)

### 4.2 Tab Layout Allocation Matrix

Using a `ttk.Notebook` hub, high-frequency core interaction modules are cleanly separated from low-frequency setup tabs, keeping layout padding uniform across the board:

```text
┌────────────────────────────────────────────────────────────────────────┐
│  【Dictation Hub】  【Analytics Board】  【Manual Ingest】  【Bulk Import】  【Control Panel】 │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  [ Dictation Workspace (High-Frequency Activity Area) ]                │
│  · Reads Context/Meaning -> Process Key Inputs -> Return Key Verifies   │
│  · Phonetics remain hidden, flashing visible immediately on feedback    │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘

```

---

## 5. Advanced Modules & Implementation Details

### 5.1 Native Offline Audio Pipelines (`pyttsx3`)

To block online distractions, the application links directly to the local host operating system speech synthesis server:

* **Graceful Degradation Catch:** The dependency is safely checked during application boot. If `pyttsx3` is missing from the environment, the internal voice variable switches smoothly to `None`. The application ignores the error instead of crashing, keeping core functionalities working.
* **Execution Trigger:** The moment a user submits an answer via the Enter key, the system calls `_TTS.say(word)` and `_TTS.runAndWait()`. This processes the text-to-speech rendering on a synchronous thread before updating the UI, pairing visual feedback with audio instantly.

### 5.2 Low-Overhead Canvas Data Visualization

The system uses native Tkinter drawing tools to build a responsive data analytics workspace, completely removing the need for heavy third-party plotting frameworks (like Matplotlib).

* **Category Progress Gauges:** Gathers the ratio of mastered words (`status=2`) across terms, dynamically altering the pixel boundaries of mint-green rectangles inside a `create_rectangle` hook to draw sleek percentage trackers.
* **Retention Frequency Histograms:** Aggregates current counts for Box 1 through Box 5 alongside unstudied items, drawing 7 gradient-colored columns directly onto a Canvas buffer with tones shifting smoothly from warning reds to deep purples.

### 5.3 Production-Grade Disaster Recovery (Backups & CSV)

* **Hot-State Database Backups:** Wraps around `shutil.copy2` utilities. Triggering a backup clones the runtime `vocab_data.db` asset into an isolated copy named with a precise timestamp format: `vocab_backup_YYYYMMDD_HHMMSS.db`, preserving the original file metadata perfectly.
* **Excel-Friendly CSV Exports:** The export engine executes an aggregated database query using logical `CASE WHEN` state routers, mapping raw status codes (0/1/2) directly into human-readable labels (e.g., *Unstudied*, *In Review*, *Mastered*). The output stream writes using the `utf-8-sig` (with BOM) encoding flag, preventing character encoding issues when opening the resulting spreadsheets inside Microsoft Excel.

---

## 6. Code Deployment Blueprint

The codebase is packaged cleanly as an all-in-one standalone file ready for rapid deployment.

* **Project Structure:** Place `main.py` and `run.bat` in the same root directory.
* **Deployment Vector:** Ensure the local runtime environment handles `pip install pyttsx3`. Once configured, launch the desktop execution process by double-clicking `run.bat` to spin up a fresh, zero-config vocabulary workspace.

```

```
