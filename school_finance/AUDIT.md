# School Finance System — Technical Audit Report

**Date:** 2026-08-01
**Scope:** Full codebase review of `school_finance/` (v1)
**Target Platforms:** Windows 7 / 8 / 10 / 11 (offline, no internet required)
**Build Toolchain:** Python 3.8 (Win7/8 target) or newer, PyInstaller `--onefile --windowed`

---

## 1. Executive Summary

The School Finance System is a functional, single-user Tkinter desktop application that manages student records, fee charges, payments (Cash / M-Pesa / In-Kind), PDF receipt/statement generation, and legacy Excel import. The codebase is small (~1,200 lines across 16 Python files) and well-structured for its scope. However, the audit reveals several categories of concern: **security vulnerabilities**, **missing robustness mechanisms**, **scalability limits**, and **UX gaps** — all of which can be addressed while maintaining strict backward compatibility with Windows 7 and 8.

---

## 2. Architecture Overview

```
school_finance/
├── main.py                  # Entry point; Tkinter root + login loop
├── db/
│   ├── database.py          # SQLite connection singleton
│   ├── schema.sql           # DDL for 6 tables + 3 indexes
│   └── __init__.py          # (empty)
├── models/
│   ├── student.py           # CRUD + balance computation
│   ├── payment.py           # CRUD for charges/payments + receipt numbering
│   ├── term.py              # Term CRUD
│   └── user.py              # Local auth (PBKDF2-SHA256) + audit logging
├── services/
│   ├── receipt_service.py   # PDF receipt generation (reportlab)
│   ├── statement_service.py # PDF statement generation (reportlab)
│   └── import_service.py    # Excel balance-sheet import (openpyxl)
├── ui/
│   ├── main_window.py       # Main application window + menu
│   ├── login_dialog.py      # Login / first-run admin creation
│   ├── students_tab.py      # Student CRUD UI
│   ├── payments_tab.py      # Payment recording + receipt preview
│   ├── statements_tab.py    # Statement generation UI
│   └── import_tab.py        # Excel import UI
├── data/                    # school_finance.db (SQLite)
├── receipts/                # Generated PDF receipts
├── statements/              # Generated PDF statements
├── backups/                 # Manual backup destination
├── build_windows.bat        # PyInstaller build script
├── requirements.txt         # openpyxl, reportlab, pyinstaller
└── README.md
```

**Data Flow:**
```
UI (Tkinter) → Models (SQLite CRUD) → DB (SQLite file)
UI → Services (reportlab/openpyxl) → Files (PDF/XLSX)
```

---

## 3. Identified Issues

### 3.1 Security

| # | Severity | Issue | Location |
|---|----------|-------|----------|
| S1 | **Critical** | SQL injection via f-string in `student.py:29` — `UPDATE students SET {', '.join(fields)} WHERE id = ?` | `models/student.py:29` |
| S2 | **High** | No password complexity enforcement — 4-character minimum only, no uppercase/digit/symbol requirements | `ui/login_dialog.py:75-77` |
| S3 | **High** | Password stored with PBKDF2-HMAC-SHA256 at 100k iterations — acceptable but no salt is persisted separately (it is embedded in the hash string, which is fine) | `models/user.py:11` |
| S4 | **Medium** | No database encryption — `school_finance.db` is a plain SQLite file containing all financial data | `db/database.py:34` |
| S5 | **Medium** | No input sanitization on file paths passed to `os.startfile()` | `ui/payments_tab.py:18` |
| S6 | **Low** | Audit log entries are written but never exposed in the UI — no way for admins to review them | `models/user.py:48-54` |

### 3.2 Robustness & Error Handling

| # | Severity | Issue | Location |
|---|----------|-------|----------|
| R1 | **High** | `get_connection()` does not handle SQLite corruption, file-lock conflicts, or I/O errors — the app crashes with a raw traceback | `db/database.py:28-42` |
| R2 | **High** | No transaction rollback on partial failures — e.g., if `add_payment()` succeeds but `generate_receipt()` fails, the payment is committed but no receipt is linked | `services/receipt_service.py:84-88` |
| R3 | **Medium** | `_open_file()` silently swallows all exceptions — users get no feedback when a PDF fails to open | `ui/payments_tab.py:23` |
| R4 | **Medium** | No database integrity check on startup — a corrupted DB is only detected when a query fails mid-operation | `db/database.py:37-41` |
| R5 | **Low** | `next_receipt_no()` uses `COUNT(*)` which is not safe under concurrent access (acceptable for single-user but fragile by design) | `models/payment.py:9-12` |

### 3.3 Scalability & Data Management

| # | Severity | Issue | Location |
|---|----------|-------|----------|
| S1 | **Medium** | `list_students_with_balance()` runs N+1 queries (one per student for balance) — degrades linearly with student count | `models/student.py:78-86` |
| S2 | **Medium** | No pagination on Treeview tables — loading 10,000+ students will freeze the UI | `ui/students_tab.py:61-73` |
| S3 | **Medium** | No indexing on `payments.date_paid` or `charges.date_added` — slow reporting on large datasets | `db/schema.sql:69-71` |
| S4 | **Low** | No data export beyond PDF — cannot export reports to CSV/Excel for offline analysis | `README.md:107` (roadmap) |
| S5 | **Low** | No database vacuum or maintenance — SQLite file grows indefinitely | — |

### 3.4 User Experience

| # | Severity | Issue | Location |
|---|----------|-------|----------|
| U1 | **Medium** | No progress indicator during Excel import — UI freezes until import completes | `ui/import_tab.py:47-71` |
| U2 | **Medium** | No keyboard shortcuts / accelerator keys for common actions (Save, Delete, Refresh) | — |
| U3 | **Medium** | Hardcoded window size `980x620` — does not adapt to screen resolution or DPI scaling | `ui/main_window.py:24` |
| U4 | **Low** | No "recent files" or history for imported Excel files | `ui/import_tab.py` |
| U5 | **Low** | No confirmation dialog before printing/opening receipts — accidental double-clicks open PDFs repeatedly | `ui/payments_tab.py:151-154` |
| U6 | **Low** | No dark mode / high-contrast theme — hard on eyes for extended use | — |

### 3.5 Maintainability & Testing

| # | Severity | Issue | Location |
|---|----------|-------|----------|
| M1 | **High** | Zero unit tests — no test suite exists anywhere in the project | — |
| M2 | **Medium** | No structured logging — only `print()` in `main.py:58` and `messagebox` for user-facing errors | `main.py:58` |
| M3 | **Medium** | No configuration file — school name comes from env var only; no way to configure defaults without code changes | `services/receipt_service.py:16` |
| M4 | **Low** | `__init__.py` files are all empty — no package-level exports or documentation | — |
| M5 | **Low** | No version metadata in code — `README.md` says v1 but no `__version__` constant exists | — |

---

## 4. Proposed Advanced Features

Each feature below includes a **backward compatibility strategy** ensuring it works on Windows 7/8/10/11 without requiring modern APIs that are unavailable on older systems.

### 4.1 Role-Based Access Control (RBAC)

**Problem:** Roles exist in the DB (`Admin`, `Bursar`, `Clerk`) but the UI grants all users identical access to every action.

**Feature:** Enforce permissions per role. For example:
- **Admin:** Full access (create users, delete students, view audit log)
- **Bursar:** Record payments, generate statements, import Excel, create backups
- **Clerk:** View students, record payments, generate receipts — no deletion or user management

**Implementation Strategy:**
1. Add a `permissions` JSON column to the `users` table (or a separate `permissions` table) — both approaches use only SQLite features available on all Windows versions.
2. Create a `check_permission(user, action)` decorator/utility in `models/user.py`.
3. In each UI tab, check `app.current_role` before enabling destructive actions (delete, import, user management).
4. **Windows 7/8 Compatibility:** Uses only Tkinter and SQLite — no modern Windows APIs. The `json` module is in the Python 3.8 standard library.

**Backward Compatibility:** The schema change (`ALTER TABLE users ADD COLUMN permissions TEXT`) is executed in `init_db()` on existing databases. SQLite 3 (bundled with Python 3.8) supports `ALTER TABLE ADD COLUMN` on Windows 7. No new dependencies.

---

### 4.2 Automated Backup & Recovery

**Problem:** Backups are entirely manual. Users must remember to back up before major posting days. No automatic or scheduled backup exists.

**Feature:**
- **Auto-backup on exit:** On clean application shutdown, copy `school_finance.db` to `backups/` with a timestamp.
- **Auto-backup on schedule:** Offer a configurable interval (e.g., every 30 minutes) that writes a timestamped copy to `backups/`.
- **Backup retention policy:** Keep the last N backups (configurable, default 10) and prune older ones.
- **Backup integrity verification:** After each backup, run `PRAGMA integrity_check` on the copy and log the result.

**Implementation Strategy:**
1. Add a `backup_service.py` in `services/` using only `shutil.copy2` and `sqlite3` — both in the standard library.
2. Schedule auto-backups using `threading.Timer` (cross-platform, no Windows-specific APIs).
3. Store the backup interval in a small JSON config file (`data/config.json`) using `json` module — works on all Windows versions.
4. On startup, scan `backups/` and verify integrity of the most recent backup.
5. Add a "Backup Settings" section in the File menu.

**Windows 7/8 Compatibility:** `shutil`, `threading`, `json`, and `sqlite3` are all in Python 3.8's standard library. No modern Windows APIs required. File system operations use only `os` and `shutil` which are fully supported on Windows 7.

---

### 4.3 Database Encryption (SQLCipher Compatibility)

**Problem:** The SQLite database file is unencrypted — anyone with file access can read all financial data, including student names and payment amounts.

**Feature:** Encrypt the database at rest using SQLCipher, with a fallback to plain SQLite for legacy deployments.

**Implementation Strategy:**
1. **Primary path:** Use `pysqlcipher3` (a Python wrapper for SQLCipher) if available — it provides AES-256 encryption transparently.
2. **Fallback path:** If `pysqlcipher3` is not installed (e.g., on a build machine without the C compiler), fall back to plain SQLite and log a warning. This ensures the app still runs on Windows 7/8 where compiling C extensions may be problematic.
3. Detect encryption support at startup in `db/database.py`:
   ```python
   try:
       import pysqlcipher3.dbapi2 as sqlite3
       ENCRYPTED = True
   except ImportError:
       import sqlite3
       ENCRYPTED = False
   ```
4. When encrypted, execute `PRAGMA key = 'passphrase'` after connection. The passphrase can be stored in `data/config.json` (same file as backup settings) or prompted on first run.
5. **Windows 7/8 Compatibility:** `pysqlcipher3` provides pre-built wheels for Windows on PyPI. If no wheel is available for the target Python version, the fallback to plain SQLite ensures the app still works. The `json` module for config storage is standard library.

**Backward Compatibility:** Existing deployments continue using plain SQLite. The `init_db()` function checks `ENCRYPTED` and applies the appropriate PRAGMA. The schema is identical — encryption is transparent at the SQLite driver level.

---

### 4.4 Structured Logging with File Rotation

**Problem:** The app has no structured logging. Errors are either shown in `messagebox` (ephemeral) or printed to stdout (lost on frozen builds). There is no audit trail for troubleshooting.

**Feature:** Add a file-based rotating log that records all user actions, errors, and system events.

**Implementation Strategy:**
1. Use Python's standard `logging` module with `RotatingFileHandler` — both available in Python 3.8.
2. Configure in `db/database.py` (or a new `config.py`) to write to `data/app.log` with:
   - Max file size: 5 MB
   - Backup count: 5 (total ~25 MB disk usage)
   - Format: `%(asctime)s [%(levelname)s] %(message)s`
3. Replace `print()` in `main.py:58` with `logging.error()`.
4. Log all audit actions (already in DB) to the file log as well for correlation.
5. Add a "View Log" option in the Help menu that opens `data/app.log` with the system default text editor (using `os.startfile` on Windows, which works on Win7+).

**Windows 7/8 Compatibility:** `logging` and `logging.handlers.RotatingFileHandler` are in the Python 3.8 standard library. No modern Windows APIs required. File I/O uses only `os` and `pathlib`-equivalent operations.

---

### 4.5 Data Export (CSV & Excel)

**Problem:** Reports can only be viewed as PDF within the app. There is no way to export data for offline analysis, accounting software, or archival.

**Feature:** Add export buttons to each tab:
- **Students tab:** Export student list + balances to CSV and Excel
- **Payments tab:** Export payment history to CSV and Excel
- **Statements tab:** Export statement data to CSV (the PDF is already generated)

**Implementation Strategy:**
1. Use Python's built-in `csv` module for CSV export — zero dependencies, works on all Windows versions.
2. Use `openpyxl` (already a dependency in `requirements.txt`) for Excel export.
3. Add export buttons next to existing action buttons in each tab's UI.
4. Use `filedialog.asksaveasfilename` (already used in the app) for save location selection.
5. **Windows 7/8 Compatibility:** `csv` is in the standard library. `openpyxl` is already a dependency. No new packages needed.

---

### 4.6 Configurable Application Settings

**Problem:** School name is read from an environment variable (`SCHOOL_NAME`) with a hardcoded fallback. No other configurable options exist. Settings cannot be changed without editing code or environment variables.

**Feature:** Add a settings dialog (accessible via `File → Settings`) that persists configuration to `data/config.json`.

**Settings to expose:**
- School name
- Currency symbol (default: KES)
- Backup interval (minutes, default: off)
- Auto-backup on exit (default: enabled)
- Backup retention count (default: 10)
- Database encryption passphrase (masked input)
- Default grade for new students
- Receipt footer text

**Implementation Strategy:**
1. Create `services/config.py` that reads/writes `data/config.json` using the `json` module.
2. Provide sensible defaults for all settings so the app works out of the box.
3. On first run, auto-detect the school name from the Windows computer name (`os.environ.get("COMPUTERNAME", "SCHOOL")`) as a fallback — this API is available on all Windows versions including Win7.
4. Use `tkinter.simpledialog` or a custom `Toplevel` dialog for the settings UI — no modern widget APIs required.
5. **Windows 7/8 Compatibility:** `json`, `os`, and `tkinter` are all standard library / bundled. `os.environ.get("COMPUTERNAME")` works on all Windows versions.

---

### 4.7 Audit Log Viewer

**Problem:** The `audit_log` table exists and is populated, but no UI exposes it. Admins cannot review who did what and when.

**Feature:** Add an "Audit Log" tab or a dialog accessible from the Help menu that displays filtered audit log entries.

**Implementation Strategy:**
1. Add a new tab "Audit Log" to the `MainWindow` notebook (or a modal dialog triggered from `Help → View Audit Log`).
2. Display columns: Timestamp, Username, Action, Detail.
3. Add filtering by date range, username, and action type.
4. Add an "Export to CSV" button for the audit log.
5. Use only existing `tkinter` widgets (`Treeview`, `DateEntry` from `tkcalendar` is optional — can use plain `Entry` with date format `YYYY-MM-DD`).
6. **Windows 7/8 Compatibility:** Uses only standard Tkinter widgets and SQLite queries. No modern APIs.

---

### 4.8 Database Integrity Check & Repair

**Problem:** No startup check for database integrity. If the DB is corrupted (e.g., due to a crash or disk error), the app crashes with an unhelpful error.

**Feature:** On startup, run `PRAGMA integrity_check` and offer a repair path if corruption is detected.

**Implementation Strategy:**
1. In `db/database.py:get_connection()`, after opening the connection, run:
   ```python
   result = conn.execute("PRAGMA integrity_check").fetchone()[0]
   if result != "ok":
       # Log the error, offer repair
   ```
2. If corruption is detected, attempt `PRAGMA wal_checkpoint(TRUNCATE)` and `PRAGMA quick_check` as lightweight repairs.
3. If repair fails, offer to restore from the most recent backup in `backups/`.
4. Display a clear error message using `messagebox` — no crash, no silent data loss.
5. **Windows 7/8 Compatibility:** `PRAGMA integrity_check` is a core SQLite feature available in all versions. File operations use only `os` and `shutil`.

---

### 4.9 Input Validation & Sanitization Layer

**Problem:** SQL injection vulnerability in `student.py:29` (f-string in UPDATE). No input validation on any form fields. No sanitization on file paths.

**Feature:** Add a validation and sanitization utility module.

**Implementation Strategy:**
1. Fix the critical SQL injection in `models/student.py:29` — replace f-string with parameterized query using a safe column-name allowlist:
   ```python
   ALLOWED_COLUMNS = {"full_name", "grade", "admission_no", "remarks", "status"}
   fields = [f"{col} = ?" for col in fields if col in ALLOWED_COLUMNS]
   ```
2. Create a `utils/validation.py` module with:
   - `sanitize_text(input_str, max_length=200)` — strips dangerous characters, truncates
   - `validate_amount(value)` — ensures positive numeric value
   - `validate_file_path(path)` — ensures path is within the app's data directory (path traversal prevention)
3. Apply validation in all UI input handlers before passing to models.
4. **Windows 7/8 Compatibility:** All validation uses pure Python string/regex operations — no OS-specific APIs. Path traversal prevention uses `os.path.normpath` and prefix checking, which work identically on all Windows versions.

---

### 4.10 Unit Test Suite

**Problem:** Zero test coverage. Every change risks introducing regressions with no way to detect them.

**Feature:** Add a test suite using Python's built-in `unittest` framework (no external test dependencies).

**Test Plan:**
1. **Database layer:** Test connection creation, schema initialization, connection cleanup.
2. **Model layer:** Test student CRUD, payment CRUD, balance calculation, receipt numbering.
3. **Service layer:** Test receipt generation (verify PDF is created, check file size > 0), test statement generation, test Excel import with a sample `.xlsx` file.
4. **Validation layer:** Test input sanitization, amount validation, path traversal prevention.
5. Use `tempfile.mkdtemp()` for isolated test databases — no persistent state between test runs.
6. Add a `test/run_tests.py` entry point and a `test` target in any future build script.

**Windows 7/8 Compatibility:** `unittest` is in the Python 3.8 standard library. `tempfile` is also standard library. No modern APIs required.

---

### 4.11 Progress & Feedback for Long-Running Operations

**Problem:** Excel import and large report generation block the Tkinter main thread, freezing the UI with no indication of progress.

**Feature:** Add a progress bar and status messages for operations that may take >1 second.

**Implementation Strategy:**
1. Use `tkinter.ttk.Progressbar` — available in Tkinter on all Windows versions including Win7.
2. For Excel import, process rows in batches and update the progress bar after each batch using `root.update_idletasks()`.
3. For PDF generation of large statements, show a "Generating..." dialog with an animated spinner (using `ttk.Progressbar` in indeterminate mode).
4. **Windows 7/8 Compatibility:** `ttk.Progressbar` has been available since Tk 8.5 (bundled with Python 3.8 on Windows). No modern APIs required.

---

### 4.12 Keyboard Shortcuts & Accessibility

**Feature:** Add keyboard accelerator keys for common actions:
- `Ctrl+S` — Save (in forms)
- `Ctrl+D` — Delete (with confirmation)
- `Ctrl+R` — Refresh
- `Ctrl+B` — Backup
- `Ctrl+Q` — Quit
- `F5` — Refresh current tab
- `Escape` — Close dialog

**Implementation Strategy:**
1. Use Tkinter's built-in `bind_all` or per-widget `bind` with `<Control-s>`, etc.
2. These are core Tkinter features available on all platforms and Windows versions.
3. Add a tooltip or status-bar hint showing available shortcuts.

**Windows 7/8 Compatibility:** Tkinter keyboard binding uses the X11/Windows event system — fully supported on all versions.

---

### 4.13 DPI-Aware Window Scaling

**Problem:** Hardcoded window size `980x620` and fixed font sizes do not adapt to different screen DPIs. On high-DPI displays (common on modern Windows), the UI may appear tiny or clipped.

**Feature:** Make the window DPI-aware and responsive.

**Implementation Strategy:**
1. On Windows, call `ctypes.windll.shcore.SetProcessDpiAwareness(1)` before creating any Tkinter windows — this API is available on Windows 8.1+ and is a no-op on Windows 7 (where DPI awareness is set differently or not needed).
2. For Windows 7 fallback, use `ctypes.windll.user32.SetProcessDPIAware()` — available on all Windows versions.
3. Use `winfo_screenwidth()` and `winfo_screenheight()` to compute a reasonable window size as a percentage of screen dimensions, rather than hardcoding `980x620`.
4. Use relative font sizes (`tkFont.Font` with scalable points) or let the system default font handle scaling.

**Windows 7/8 Compatibility:** The `ctypes` approach uses `user32.dll` and `shcore.dll` which exist on Windows 7 (with `SetProcessDPIAware` available via `user32`). The fallback chain ensures the app works on all target OS versions.

---

### 4.14 CSV Import (Complement to Excel Import)

**Problem:** The import feature only supports `.xlsx`/`.xlsm` files. Many schools may have data in simpler CSV format.

**Feature:** Add CSV import alongside the existing Excel import.

**Implementation Strategy:**
1. Use Python's built-in `csv` module — zero dependencies, works on all Windows versions.
2. Add a file filter for CSV in the `filedialog.askopenfilename` call.
3. Parse CSV rows using the same column-classification logic as the Excel importer (name, remarks, charge columns).
4. **Windows 7/8 Compatibility:** `csv` is in the Python 3.8 standard library. No new dependencies.

---

## 5. Backward Compatibility Strategy Summary

All proposed features use only APIs and libraries available in Python 3.8's standard library or already listed in `requirements.txt`. The specific compatibility guarantees are:

| Concern | Mitigation |
|---------|-----------|
| **Windows 7 API gaps** | No feature uses APIs introduced after Windows 7. `ctypes` calls use `user32.dll` (available on Win7). Tkinter 8.5 is bundled with Python 3.8 on Windows. |
| **Python 3.8 dependency** | All features use `json`, `csv`, `logging`, `unittest`, `threading`, `shutil`, `os`, `sqlite3`, `hashlib`, `tempfile` — all in Python 3.8 standard library. |
| **PyInstaller compatibility** | No new native C extensions required. `pysqlcipher3` is optional and falls back to plain SQLite. All other features are pure Python. |
| **SQLite version** | SQLite 3.x (bundled with Python 3.8) supports all PRAGMAs used (`integrity_check`, `foreign_keys`, `wal_checkpoint`). |
| **File system** | All file operations use `os` and `shutil` — identical behavior on Win7 through Win11. |
| **UI framework** | Tkinter 8.5 (Python 3.8) is identical across Windows 7–11. `ttk` widgets are available via `tkinter.ttk`. |
| **Optional features** | Encryption (`pysqlcipher3`) and DPI awareness (`shcore`) are guarded with try/except and have fallbacks — the app always works even if these are unavailable. |

---

## 6. Prioritized Implementation Roadmap

| Priority | Feature | Effort | Risk | Windows 7 Safe? |
|----------|---------|--------|------|-----------------|
| P0 | Fix SQL injection (S1) | Low | Critical | Yes |
| P0 | Database integrity check on startup (R4) | Low | High | Yes |
| P0 | Structured logging (M2) | Low | Medium | Yes |
| P1 | Input validation layer (S1 fix + U6) | Medium | Medium | Yes |
| P1 | RBAC enforcement (U1) | Medium | Low | Yes |
| P1 | Automated backup (R2) | Medium | Low | Yes |
| P2 | Data export CSV/Excel (S4) | Low | Low | Yes |
| P2 | Configurable settings (M3) | Medium | Low | Yes |
| P2 | Audit log viewer (S6) | Medium | Low | Yes |
| P3 | Database encryption (S4) | High | Medium | Yes (with fallback) |
| P3 | Unit test suite (M1) | High | Low | Yes |
| P3 | Progress indicators (U1) | Medium | Low | Yes |
| P3 | DPI-aware scaling (U3) | Medium | Low | Yes (with fallback) |
| P3 | Keyboard shortcuts (U2) | Low | Low | Yes |
| P4 | CSV import (S4 complement) | Low | Low | Yes |
| P4 | Backup integrity verification (R2) | Low | Low | Yes |

---

## 7. Critical Fix: SQL Injection Vulnerability

The most urgent issue is the SQL injection in `models/student.py:29`:

```python
# VULNERABLE — do not ship in this form
conn.execute(f"UPDATE students SET {', '.join(fields)} WHERE id = ?", values)
```

**Fix:** Use a column name allowlist:

```python
ALLOWED_COLUMNS = {"full_name", "grade", "admission_no", "remarks", "status"}
safe_fields = [(col, val) for col, val in fields if col in ALLOWED_COLUMNS]
set_clause = ", ".join(f"{col} = ?" for col, _ in safe_fields)
values = [val for _, val in safe_fields] + [student_id]
conn.execute(f"UPDATE students SET {set_clause} WHERE id = ?", values)
```

This is the highest-priority fix and should be applied before any other changes.
