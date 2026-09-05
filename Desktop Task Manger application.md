# Research Findings: Building a Python Desktop Task Manager — Technical Foundation for a Project Design Document

## TL;DR
- **Build the task manager in Python with PySide6 (Qt) as the primary recommendation, or CustomTkinter + tkinterdnd2 as a lighter alternative**, store data in SQLite, use QDateEdit/tkcalendar for deadlines, and package with PyInstaller per-OS.
- **Drag-and-drop reordering is nearly free in Qt** via `setDragDropMode(QAbstractItemView.InternalMove)`, whereas Tkinter requires manual mouse-event handling or the third-party tkinterdnd2 library.
- **A clean MVC/three-layer architecture** (UI / logic / data) plus SQLite persistence and plyer notifications makes the app maintainable, testable, and cross-platform.

## Key Findings

### A. GUI framework recommendation
For a small-to-medium task manager needing polished drag-and-drop, **PySide6 (Qt for Python) is the strongest default**. It is LGPL-licensed (free for closed-source), cross-platform, has native-quality widgets, a Model/View architecture, and near-built-in list reordering. The main cost is a steeper learning curve. The pythonguis.com framework guide notes that "In 2026 the trend for commercial and enterprise software is towards using PySide6 due to the reduced licensing cost and the official support for the Qt company."

If the team prefers minimal setup and Python-only simplicity, **CustomTkinter** (a modern skin over Tkinter) plus **tkinterdnd2** for drag-and-drop is a strong lighter-weight option. **Flet** (Flutter-based) is the best choice if the same codebase must also target web/mobile, and it has a first-class `ReorderableListView`.

### B. Drag-and-drop reordering
- **Qt (PySide6/PyQt6)**: Set `view.setDragDropMode(QAbstractItemView.InternalMove)` on a `QListWidget` (or `QListView` + model). For custom models, override `flags()`, `supportedDropActions()`, and for complex data `mimeData()`/`dropMimeData()`.
- **Tkinter**: No built-in list reordering. Either (1) manually bind `<Button-1>`/`<B1-Motion>` and swap items using `nearest(event.y)`, or (2) use the `tkinterdnd2` package for native OS drag-and-drop.
- **Flet**: `ft.ReorderableListView` with an `on_reorder` handler.

### C. Data persistence
**SQLite (via the standard-library `sqlite3` module) is the recommended choice** for a task manager. It is serverless, zero-config, stored in a single file, supports queries/sorting/filtering, and is built into Python. JSON is fine for tiny apps; TinyDB suits small document-style storage (~10,000 docs ceiling); pickle is discouraged for primary storage.

### D. Deadlines & notifications
Use **`tkcalendar`'s `DateEntry`** widget (Tkinter) or Qt's **`QDateEdit`/`QDateTimeEdit`** for date selection. Store deadlines as ISO 8601 strings or SQLite date columns. Detect overdue tasks by comparing `datetime.now()` to the deadline and highlight rows (e.g., red). For reminders, **`plyer.notification.notify()`** gives cross-platform desktop notifications; `win10toast` (Windows) and `notify-py`/`py-notifier` are alternatives.

### E. Packaging
**PyInstaller** is the recommended default. Note it **cannot cross-compile** — you must build the Windows executable on Windows, macOS app on macOS, etc. Nuitka compiles to C for faster startup and some IP protection; Briefcase produces native installers (MSI/DMG/deb). macOS distribution outside the App Store requires code-signing and notarization.

### F. Task manager UX
Essential features: quick task creation, priority levels, deadlines, mark-complete, edit/delete, sorting, and filtering. Nice-to-have: categories/tags, subtasks, recurring tasks, undo, search, notifications, dark mode.

### G. Architecture
Use **MVC** (or MVP for Qt): separate Model (data + business logic), View (UI widgets), Controller (mediates). This improves testability (logic can be unit-tested without the GUI) and maintainability.

---

## Details

### A. Python desktop GUI framework options (2025/2026)

The following synthesizes multiple 2025/2026 comparison sources (pythonguis.com, unite.ai, pistack.xyz).

| Framework | Ships with Python? | License | Ease of use | Modern look | Cross-platform | DnD list reorder |
|---|---|---|---|---|---|---|
| **Tkinter/ttk** | Yes (stdlib) | PSF (permissive) | Easy | Dated (ttk improves) | Win/mac/Linux | Manual / via tkinterdnd2 |
| **PyQt5/6** | No (pip) | GPL v3 or commercial | Moderate | Excellent (styled) | Win/mac/Linux | Built-in (InternalMove) |
| **PySide6** | No (pip) | LGPL v3 | Moderate | Excellent (styled) | Win/mac/Linux | Built-in (InternalMove) |
| **Kivy** | No (pip) | MIT | Moderate | Custom (non-native) | Win/mac/Linux + mobile | Custom |
| **wxPython** | No (pip) | wxWindows (permissive) | Moderate | Excellent (native) | Win/mac/Linux | Supported |
| **CustomTkinter** | No (pip) | MIT (CC0 per some releases) | Easy | Modern (dark mode, HiDPI) | Win/mac/Linux | Via tkinterdnd2 |
| **Flet** | No (pip) | Apache 2.0 | Easy | Modern (Flutter) | Win/mac/Linux + web/mobile | Built-in (ReorderableListView) |

**Licensing detail that matters:** PyQt6 is GPL v3, or a paid commercial license from Riverbank Computing priced at approximately US$550 per developer per year (which removes GPL obligations for unlimited applications with no royalties). PySide6 is LGPL v3, which permits closed-source distribution as long as the library is dynamically linked and replaceable — avoiding any licensing fee. For a student/portfolio/open-source project either works; for any potential commercial closed-source distribution, PySide6 avoids licensing costs entirely.

**Recommendation & justification:**
- **Primary: PySide6.** Best combination of professional appearance, permissive LGPL license, native-quality widgets, mature Model/View framework, and drag-and-drop that is essentially built-in — directly satisfying requirement #3 (drag to reorder priority). Qt also ships `QDateEdit` for requirement #4 (deadlines).
- **Lightweight alternative: CustomTkinter + tkinterdnd2.** If the team wants the simplest possible Python-only stack and a modern look without Qt's learning curve. Tkinter is bundled with Python, so the base dependency footprint is minimal. CustomTkinter requires Python 3.7+ and auto-installs `darkdetect` and `packaging`; it provides dark/light/system appearance modes and HiDPI scaling for a consistent look across Windows, macOS, and Linux.
- Tkinter alone is acceptable for a purely educational build but looks dated and needs the most manual work for drag-and-drop.

### B. Drag-and-drop reordering implementation

**Qt (PySide6/PyQt6) — the simple path.** For a `QListWidget`, the canonical solution repeatedly confirmed on the Qt forums is a single call: `listWidget.setDragDropMode(QAbstractItemView.InternalMove)`. You should also set `setSelectionMode(QAbstractItemView.SingleSelection)` and `setDefaultDropAction(Qt.MoveAction)` to avoid the common pitfall where dragging selects additional rows or overwrites the target instead of reordering.

**Qt — the Model/View path.** KDAB's "Model/View Drag and Drop" guide gives the checklist: call `setDragDropMode(InternalMove)`; for `QTableView` also `setDragDropOverwriteMode(false)`; in the model, reimplement `flags()` to add `Qt.ItemIsDragEnabled` (and NOT `ItemIsDropEnabled` on items for a flat list), implement `supportedDropActions()` returning `Qt.MoveAction`, and if the underlying data is complex, override `mimeData()`/`dropMimeData()`/`removeRows()`. A common pitfall noted by developers: the default `mimeData`/`dropMimeData` implementations only work if your data is serialized via `setData` on the `EditRole`; otherwise you must implement serialization yourself. A working PyQt5 reference implementation exists (d1vanov/PyQt5-reorderable-list-model).

**Tkinter — manual pattern.** The classic "DDList" recipe (John Fouhy, Python Cookbook) subclasses `Listbox` with `selectmode=SINGLE`, binds `<Button-1>` to record the start index via `self.nearest(event.y)`, and binds `<B1-Motion>` to delete-and-reinsert the item as the mouse crosses row boundaries. This is the most common lightweight approach and requires no third-party dependency. For a `ttk.Treeview`, there is no built-in reorder; developers bind mouse events and use `move()` or reinsert rows.

**Tkinter — tkinterdnd2.** The `tkinterdnd2` package (pip-installable, wraps the native tkDnD Tcl/Tk extension; the maintained fork is Eliav2/tkinterdnd2) adds native OS drag-and-drop for Windows/Unix/macOS. Note: tkinterdnd2 is primarily oriented toward file/text drops (`DND_FILES`), so for pure intra-list reordering the manual mouse-event pattern is often simpler. CustomTkinter can be combined with tkinterdnd2 by multiple-inheriting `TkinterDnD.DnDWrapper`.

**Flet.** `ft.ReorderableListView` handles drag logic internally and fires `on_reorder` with `old_index`/`new_index`; you then reorder your backing list: `controls.insert(e.new_index, controls.pop(e.old_index))`. Custom drag handles are available via `ReorderableDragHandle`.

**Universal pitfall:** persist the new order only when the drag *ends*, not during the drag, and map the visual order back to a stored `priority`/`sort_order` field in your data model.

### C. Data persistence trade-offs

| Option | Format | Query support | Concurrency | Dependencies | Practical ceiling | Best for |
|---|---|---|---|---|---|---|
| **SQLite (`sqlite3`)** | Binary .db | Full SQL, indexes | Safe (locking, WAL) | Built-in | Millions of rows | The recommended default |
| **JSON file** | Human-readable | Manual dict/list code | Not safe | Built-in | A few hundred KB | Tiny/static data |
| **TinyDB** | Human-readable JSON | Python Query objects | Not safe (rewrites file) | pip | ~10,000 documents | Small prototypes |
| **pickle** | Binary | Key lookup only | Not safe | Built-in | Small | Quick object persistence (not primary storage) |

**Recommendation: SQLite.** It is serverless, zero-configuration, cross-platform, stored in a single portable file, and part of the Python standard library. It natively supports the sorting/filtering a task manager needs and scales far beyond a personal task list. The official TinyDB documentation itself advises: "If you need advanced features or high performance, TinyDB is the wrong database for you – consider using databases like SQLite, Buzhug, CodernityDB or MongoDB" (the advanced features it lists as missing include multi-process/thread access, indexes, and ACID guarantees). Best practices: use `with sqlite3.connect(...)` context managers, use parameterized queries (`?` placeholders) to prevent SQL injection, and back up by copying the single .db file. JSON is a reasonable simpler alternative for a purely educational build where a human-readable file is desirable.

### D. Deadline & date handling

**Date pickers:**
- **Tkinter**: `tkcalendar` provides `Calendar` and `DateEntry` widgets (`pip install tkcalendar`). `DateEntry` is a combobox whose dropdown is a calendar; `cal.get_date()` returns a `datetime.date`. It supports locales and custom colors and fires a `<<DateEntrySelected>>` virtual event. Works on Linux, Windows, and Mac (requires tkinter + ttk).
- **Qt**: `QDateEdit`/`QDateTimeEdit` with `setCalendarPopup(True)` provide a native calendar dropdown.

**Storing deadlines:** Store as ISO 8601 text (`YYYY-MM-DD` or full datetime) or a SQLite date column; parse with `datetime`. ISO strings sort lexicographically, which simplifies ordering.

**Overdue detection & highlighting:** Compare the stored deadline against `datetime.now()`; flag tasks where `deadline < now` and not completed. In Qt, color the row via item foreground/background roles; in Tkinter's Treeview, use tags with `tag_configure(..., background='...')`. Common convention: red for overdue, amber for due-soon.

**Notifications/reminders:**
- **plyer** — `from plyer import notification; notification.notify(title=..., message=..., timeout=...)` — cross-platform (Windows/macOS/Linux) with one API.
- **win10toast** — Windows-only toast notifications (`ToastNotifier().show_toast(...)`).
- **notify-py** and **py-notifier (pynotifier)** — cross-platform wrappers; py-notifier uses win10toast on Windows, libnotify (`notify-send`) on Linux, and pync on macOS.
- A background timer (e.g., Qt `QTimer` or Tkinter `after()`) can poll for approaching deadlines and trigger notifications. Note the known caveat that plyer's PyPI release has sometimes lagged behind its GitHub master (some users install from the GitHub zipball to get fixes).

### E. Packaging & distribution

| Tool | Mechanism | Output | Cross-compile? | Notes |
|---|---|---|---|---|
| **PyInstaller** | Bundles CPython + bytecode | One-file or one-folder | No | Fastest/easiest; slow cold start; source recoverable |
| **cx_Freeze** | Bundles interpreter + code | Distribution directory | No | Config-driven; smaller community |
| **Nuitka** | Compiles Python → C | Native binary | No (per-OS) | Fast startup, faster runtime, some IP protection; longer builds |
| **Briefcase (BeeWare)** | Bundles into native installer | MSI / DMG / deb etc. | No | Best when native install experience matters |

- **PyInstaller** (latest 6.x series; 6.22.2 released 2026-08-17) supports Windows, Linux, and macOS but **cannot cross-compile**. Its official FAQ states: "Can I package Windows binaries while running under Linux? No, this is not supported. Please use Wine for this, PyInstaller runs fine in Wine." The manual likewise states "it is not a cross-compiler: to make a Windows app you run PyInstaller in Windows; to make a GNU/Linux app you run it in GNU/Linux, etc." You need a build machine per target OS.
- **Nuitka** (4.x series as of 2026) is a source-to-source compiler that compiles Python code to C, applying compile-time optimizations. Use `--standalone` and `--onefile` (newer syntax `--mode=standalone`/`--mode=onefile`). Performance gains are workload-dependent: Nuitka's own pystone microbenchmark reports roughly 3.3–3.7× CPython with LTO/PGO, while real-world CPU-bound pure-Python gains are more modest (roughly 10–40%), with little change for I/O- or C-extension-heavy code. Startup is faster than PyInstaller because there is no unpacking step.
- **Briefcase** produces, per the official BeeWare docs, macOS as "a .app bundle, DMG archive or PKG installer," Windows as "a .zip, or an MSI installer" (built via the WiX Toolset), and Linux as "a Flatpak, or a .rpm, .deb, or .pkg.zip system native package," plus iOS/Android/web. Briefcase bundles the interpreter and bytecode (it does not compile to native code).
- **macOS caveat:** Apps distributed outside the App Store must be code-signed with a Developer ID and notarized by Apple, or Gatekeeper will block them. Apple's macOS Security Guide states: "Gatekeeper verifies that the software is from an identified developer, is notarized by Apple to be free of known malicious content, and hasn't been altered." Note the 2024/2025 tightening: "In macOS Sequoia, users will no longer be able to Control-click to override Gatekeeper when opening software that isn't signed correctly or notarized. They'll need to visit System Settings > Privacy & Security to review security information for software before allowing it to run." Notarization requires membership in the paid Apple Developer Program.
- **tkinterdnd2 + PyInstaller:** copy the included `hook-tkinterdnd2.py` into your project and build with `--additional-hooks-dir=.` so the tkdnd binaries are bundled. The hook essentially runs `datas = collect_data_files('tkinterdnd2')` to include the tkdnd data files PyInstaller otherwise misses.

**Recommendation:** PyInstaller for the main deliverable (one-folder for reliability, one-file for convenience), building separately on each target OS via CI runners. Consider Nuitka if startup speed matters; Briefcase if you want polished native installers.

### F. Task manager UX / feature best practices

Synthesis of UX sources (task management app guides, to-do app reviews from 2025/2026):

**Essential (MVP):**
- Fast task creation (adding a task should "take seconds, not minutes")
- Priority levels (e.g., High/Medium/Low, or Eisenhower matrix)
- Deadlines / due dates
- Mark complete / incomplete
- Edit and delete
- Sorting (by priority, deadline) and filtering (by status, category)
- Clean, uncluttered, intuitive UI

**Nice-to-have (post-MVP):**
- Categories/projects and tags/labels
- Subtasks and recurring tasks
- Search
- Undo
- Notifications/reminders
- Dark mode / theming
- Calendar view/integration
- Progress tracking, drag-and-drop organization (already core here)

Prioritization frameworks worth referencing in the doc: the **Eisenhower Matrix** (Urgent/Important quadrants) and **Kanban** (To Do / In Progress / Done). UX research repeatedly stresses that "drag-and-drop task organisation, clear navigation, and thoughtful design" are what distinguish a good task app from a great one, and that quick capture plus flexible organization (projects vs. tags/filters) are the highest-value patterns.

### G. Architecture & code organization

**Pattern: MVC (Model-View-Controller)**, or **MVP (Model-View-Presenter)** which is often cited as better suited to Qt GUIs.
- **Model**: task data + business logic (create/edit/delete/reorder, overdue calculation, persistence). Completely UI-unaware.
- **View**: GUI widgets (list, forms, date picker). Presentation only.
- **Controller/Presenter**: handles user input, mediates between View and Model.

Benefits repeatedly cited: separation of concerns, independent unit testing of business logic, UI swappability (e.g., swap Tkinter for Qt without rewriting logic), and easier maintenance/scaling. Tkinter-specific MVC tutorials commonly use a to-do list as the worked example, which maps directly onto this project.

**Suggested project structure:**
```
task_manager/
├── main.py                 # entry point
├── models/
│   ├── task.py             # Task dataclass/entity
│   └── task_repository.py  # SQLite persistence layer (CRUD)
├── views/
│   ├── main_window.py      # main UI
│   ├── task_list.py        # reorderable list widget
│   └── task_dialog.py      # add/edit dialog with date picker
├── controllers/
│   └── task_controller.py  # mediates view<->model
├── services/
│   └── notifier.py         # plyer notification wrapper
├── data/
│   └── tasks.db            # SQLite database
├── tests/
│   └── test_task_logic.py  # pytest unit tests
├── requirements.txt
└── README.md
```

**Suggested data model (SQLite `tasks` table):**
```
id            INTEGER PRIMARY KEY AUTOINCREMENT
title         TEXT NOT NULL
description   TEXT
priority      TEXT        -- e.g. 'High' | 'Medium' | 'Low'
sort_order    INTEGER     -- integer position updated on drag-drop reorder
deadline      TEXT        -- ISO 8601 date/datetime
completed     INTEGER     -- 0/1 boolean
category      TEXT        -- optional tag/project
created_at    TEXT        -- ISO 8601 timestamp
```
The `sort_order` column is the persistence target for the drag-and-drop feature: after a reorder, rewrite `sort_order` for affected rows and query with `ORDER BY sort_order`.

**Testing:** Keep business logic separate so it can be unit-tested with `pytest`/`unittest` without a display. For GUI-level tests, use `pytest-qt`'s `qtbot` (Qt) or Tkinter's event loop with `update()`; run headless in CI via `xvfb-run` on Linux. Mock persistence with in-memory SQLite (`sqlite3.connect(':memory:')`).

---

## Recommendations

**Recommended stack (decision-ready):**
1. **GUI: PySide6** (primary) for built-in drag-and-drop, native look, and LGPL licensing — or **CustomTkinter + tkinterdnd2** if the team wants a simpler Python-only stack with a modern look.
2. **Persistence: SQLite** via `sqlite3`, with a repository/data-access layer.
3. **Dates: `QDateEdit`** (Qt) or **`tkcalendar.DateEntry`** (Tkinter); store ISO 8601; highlight overdue in red.
4. **Notifications: plyer** for cross-platform reminders, driven by a `QTimer`/`after()` poll.
5. **Architecture: MVC/MVP** with the folder structure above.
6. **Packaging: PyInstaller**, built per-OS; sign+notarize on macOS.
7. **Testing: pytest** on the logic layer; `pytest-qt` for UI; headless CI via Xvfb.

**Staged plan:**
- **Phase 1 (MVP):** create/edit/delete tasks, priority field, deadline with date picker, mark complete, SQLite persistence, sort by priority/deadline.
- **Phase 2:** drag-and-drop reordering that writes back a `sort_order` field, overdue highlighting, filtering.
- **Phase 3:** notifications/reminders, categories/tags, search, dark mode, undo.
- **Phase 4:** package and distribute per-OS; add CI tests.

**Thresholds that change the recommendation:**
- If closed-source commercial distribution is ever intended → avoid PyQt (GPL, or ~US$550/developer/year commercial); stay on PySide6 (LGPL) or Tkinter/CustomTkinter.
- If the app must also run on web/mobile → switch to **Flet**.
- If data volume/relationships stay trivial and a human-readable file is a hard requirement → JSON is acceptable instead of SQLite.
- If startup latency becomes a complaint → repackage with **Nuitka**.

## Caveats
- GUI framework "popularity" and star counts cited by comparison blogs are secondary indicators; PySide6/PyQt6 remain the consensus professional choice, but the specific ranking language varies by source and some are SEO/marketing-oriented.
- Several packaging performance claims are directional: Nuitka's high multipliers come from its own microbenchmarks (pystone with LTO/PGO), while independent real-world gains are typically 10–40% for CPU-bound Python and negligible for I/O- or C-extension-heavy code. Treat blog startup-time comparisons as illustrative, not controlled studies.
- tkinterdnd2 is community-maintained (a fork chain of an originally unmaintained wrapper); confirm the active fork (Eliav2/tkinterdnd2) before depending on it, and use the universal build for Apple Silicon.
- Version numbers and notarization rules evolve; the figures here (PyInstaller 6.22.x, Nuitka 4.x, Briefcase 0.3.x, WiX 5.x) reflect 2026 data — verify current versions and Apple's current notarization requirements at build time.
- Drag-and-drop in Qt's Model/View has real edge cases (selection handling after drop, `dragDropOverwriteMode`) that require testing on each target OS.