# School Finance System — Agent Configuration

## Project Overview
A Tkinter-based offline desktop finance app for junior schools. Manages student records, fee charges, payments (Cash / M-Pesa / In-Kind), PDF receipt/statement generation, and legacy Excel import. Targets Windows 7 / 8 / 10 / 11.

## Key Files
- `school_finance/main.py` — Entry point; login loop + main window
- `school_finance/db/database.py` — SQLite connection singleton
- `school_finance/db/schema.sql` — DDL for 6 tables + 3 indexes
- `school_finance/models/student.py` — Student CRUD + balance calc
- `school_finance/models/payment.py` — Payment/charge CRUD + receipt numbering
- `school_finance/models/term.py` — Term CRUD
- `school_finance/models/user.py` — Local auth (PBKDF2-SHA256) + audit logging
- `school_finance/services/receipt_service.py` — PDF receipt generation
- `school_finance/services/statement_service.py` — PDF statement generation
- `school_finance/services/import_service.py` — Excel balance-sheet import
- `school_finance/ui/main_window.py` — Main window + menu
- `school_finance/ui/login_dialog.py` — Login / admin creation
- `school_finance/ui/students_tab.py` — Student CRUD UI
- `school_finance/ui/payments_tab.py` — Payment recording + receipt preview
- `school_finance/ui/statements_tab.py` — Statement generation UI
- `school_finance/ui/import_tab.py` — Excel import UI
- `school_finance/build_windows.bat` — PyInstaller build script
- `school_finance/requirements.txt` — openpyxl, reportlab, pyinstaller
- `school_finance/AUDIT.md` — Comprehensive technical audit report

## Build & Test Commands
- Build .exe (Windows): `build_windows.bat` from inside `school_finance/`
- Run from source: `python main.py` from `school_finance/`
- Install deps: `pip install -r requirements.txt`
- Run tests: (none yet — see AUDIT.md for test suite proposal)

## Critical Known Issues
1. **SQL injection** in `models/student.py:29` — f-string in UPDATE statement
2. **No input validation** on any form field
3. **No error handling** in `get_connection()` for DB corruption
4. **No structured logging** — only `print()` in `main.py:58`
5. **Zero test coverage**
6. **No RBAC enforcement** — roles exist in DB but not enforced in UI
7. **No database encryption** — plain SQLite file

## Windows Compatibility Notes
- Python 3.8 is the target for Windows 7/8 builds (last version with Win7 support)
- PyInstaller `--onefile --windowed` produces a single `.exe`
- All features must use only Python 3.8 standard library or existing `requirements.txt` deps
- Optional features (e.g., `pysqlcipher3`, `shcore` DPI awareness) must have fallbacks
- `ctypes` calls to `user32.dll` work on all Windows versions including Win7
- Tkinter 8.5 is bundled with Python 3.8 on Windows

## Architecture Patterns
- Singleton SQLite connection (`_connection` global in `database.py`)
- Model-layer CRUD functions call `get_connection()` directly
- Services use `reportlab.pdfgen.canvas` for PDF generation
- Excel import uses `openpyxl.load_workbook(data_only=True)`
- UI uses `ttk` widgets with `Toplevel` for modal dialogs
- Audit logging via `models.user.log_action()` inserts into `audit_log` table