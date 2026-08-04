# School Finance System

A Tkinter-based offline desktop finance application for junior schools. Manages student records,
fee charges, payments (Cash / M-Pesa / In-Kind), PDF receipt and statement generation, legacy
Excel import, bulk payments, partial fee waivers, and role-based access control. Works on
Windows 7 SP1, 8, 10, and 11 — no internet connection required.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Quick Start — Running from Source](#2-quick-start--running-from-source)
3. [Building a Windows .exe](#3-building-a-windows-exe)
4. [Everyday Use](#4-everyday-use)
5. [User Roles & Permissions](#5-user-roles--permissions)
6. [Backups](#6-backups)
7. [Data Model](#7-data-model)
8. [Project Structure](#8-project-structure)
9. [Configuration](#9-configuration)
10. [Running the Tests](#10-running-the-tests)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. Overview

School Finance System is a single-user (with multi-role support) desktop application designed
for junior school bursar offices. All data is stored locally in a single SQLite database file.

**Core capabilities:**

| Feature | Description |
|---|---|
| **Student management** | Add, edit, search, and deactivate students. Track grade, stream, admission number, and status. |
| **Fee charging** | Record term fees, opening balances (via Excel import), and ad-hoc charges. |
| **Payment processing** | Record payments by Cash, M-Pesa (with code), or In-Kind (with description). |
| **PDF receipts** | Auto-generate and print receipts with configurable footer and signature. |
| **PDF statements** | Generate comprehensive statements showing all charges, payments, waivers, and running balances. |
| **Fee structure** | Define per-grade, per-term fee amounts that auto-apply to new charges. |
| **Bulk payments** | Record a single payment that covers multiple students (e.g., bursary disbursement). |
| **Partial waivers** | Grant, track, and revoke partial fee waivers with full audit trail. |
| **Arrears report** | List students with outstanding balances, filterable by grade/term. |
| **Income reports** | Summarise income by payment method, term, or date range. |
| **Legacy Excel import** | One-time import of existing balance sheets — each non-zero balance column becomes an opening charge. Safe to re-run (skips already-imported students). |
| **CSV/Excel export** | Export student lists, balances, and payment history to CSV or Excel. |
| **Audit log** | Every user action (login, payment, waiver, etc.) is recorded with timestamp and user. |
| **Backups** | Manual backups anytime; automatic timestamped backup on exit. Integrity-verified. |
| **Window geometry** | Remembers window size and position between sessions. |
| **Keyboard shortcuts** | Ctrl+S, Ctrl+R, Ctrl+B, F5, Esc — see [below](#4-everyday-use). |

---

## 2. Quick Start — Running from Source

> **On Windows**, double-clicking `SchoolFinance.exe` (from the [build step](#3-building-a-windows-exe))
> is the intended distribution method. Running from source is for development on Linux/Mac/Windows.

### Prerequisites

- Python 3.8 or newer
- pip

### Steps

```bash
cd school_finance
pip install -r requirements.txt
python main.py
```

On first launch you'll be prompted to create an **Admin** username and password (local only,
nothing is sent over the network). After that, subsequent launches go straight to the login
screen.

---

## 3. Building a Windows .exe

This is done **once** on a Windows PC by whoever sets up the system for the school.

### 3.1 Build the standalone executable

```bat
cd school_finance
build_windows.bat
```

The script:
1. Looks for **Python 3.8** first (via `py -3.8` or common install paths) — 3.8 is the last
   Python with Windows 7 support. Falls back to whatever `python` is on your PATH (fine if all
   target PCs are Windows 10/11).
2. Installs dependencies from `requirements.txt`.
3. Runs PyInstaller with `--onefile --windowed --name SchoolFinance`.

After it finishes, the executable is at `dist\SchoolFinance.exe`.

> **Python 3.8 download (for Windows 7/8 builds):**
> https://www.python.org/downloads/release/python-3810/
> Download the "Windows x86-64 executable installer". Install **without** adding to PATH
> to avoid interfering with any other Python already on that machine.

### 3.2 Create an installer (optional)

An optional [Inno Setup](https://jrsoftware.org/isinfo.php) script is provided:

```bat
cd school_finance
build_windows.bat         REM — step 3.1, first
REM Then open SchoolFinanceSetup.iss in Inno Setup Compiler and press Ctrl+F9
```

The installer:
- Targets Windows 7 SP1 through Windows 11 (`MinVersion=6.1`).
- Installs to the user's local AppData folder (no admin rights required).
- Pre-creates `data`, `receipts`, `statements`, `backups` folders with write permissions.
- Installs the Visual C++ Redistributable (required for Python 3.8 builds on Win7/8).
- Preserves user data on uninstall (the database and PDFs are kept).

### 3.3 Deploying to school computers

Copy `dist\SchoolFinance.exe` to any Windows 7/8/10/11 machine and double-click — no installer,
no Python required. On first run it creates `data`, `receipts`, `statements`, and `backups`
folders right next to the `.exe`.

**Always keep `SchoolFinance.exe` together with its `data` folder.** The
`data\school_finance.db` file is the entire database — that single file is what you back up.

---

## 4. Everyday Use

The main window is organised into tabs. Which tabs you see depends on your role (see
[Section 5](#5-user-roles--permissions)).

| Tab | What it does |
|---|---|
| **Dashboard** | At-a-glance summary: today's collections, total outstanding balance, total receivables, count of waived students. |
| **Students** | CRUD students, filter by grade, view live balances. Add streams and fee-waiver flags. |
| **Payments** | Pick a student + term, enter amount and method (Cash/M-Pesa/In-Kind), click Save & Print Receipt. |
| **Fee Statements** | Generate full PDF statements per student showing every charge, payment, and running balance. |
| **Arrears** | List all students with outstanding balances. Filter by grade and term. Export to CSV/Excel. |
| **Income Reports** | View income by payment method, term, or custom date range. Export to CSV/Excel. |
| **Fee Structure** | Define per-grade term fees. These auto-apply when charging students. |
| **Bulk Payments** | Record one payment covering multiple students (e.g., bursary disbursement). |
| **Partial Waivers** | Grant, view, or revoke partial fee waivers. |
| **Import Legacy Excel** | Import an existing balance-sheet workbook. Non-zero balance columns become opening charges. Safe to re-run. |
| **Settings** | Configure school name, currency symbol, backup retention, receipt footer, etc. |
| **Users** *(Admin only)* | Create, edit, deactivate users. Assign roles. |

### Keyboard shortcuts (global)

| Shortcut | Action |
|---|---|
| `Ctrl + S` | Save current form |
| `Ctrl + R` | Refresh all tabs |
| `Ctrl + B` | Backup database now |
| `F5` | Refresh all tabs |
| `Esc` | Close current dialog |

### Menu bar

- **File** → Backup Database Now (manual, integrity-verified), Logout, Exit
- **Settings** → App Settings…, Manage Users… *(Admin only)*, Change My Username/Password…
- **Help** → View Audit Log…

---

## 5. User Roles & Permissions

The system supports three roles, each with a tailored permission set:

| Permission | Admin | Bursar | Clerk |
|---|---|---|---|
| Record payments | ✓ | ✓ | ✓ |
| Generate statements | ✓ | ✓ | ✓ |
| Manage students (add/edit/delete) | ✓ | ✓ | View only |
| Fee structure | ✓ | ✓ | ✗ |
| Import legacy Excel | ✓ | ✓ | ✗ |
| Bulk payments | ✓ | ✓ | ✓ |
| Partial waivers | ✓ | ✓ | ✗ |
| Manage users | ✓ | ✗ | ✗ |
| Backups | ✓ | ✓ | ✗ |
| Audit log viewer | ✓ | ✓ | ✓ |
| Settings | ✓ | ✓ | ✓ |

Passwords are hashed with **PBKDF2-HMAC-SHA256** (100,000 iterations, per-password random salt)
using only the Python 3.8 standard library — no external dependencies.

Authentication happens locally — there is no server, no network, and no cloud sync. The audit
log records every significant action with a timestamp and username.

---

## 6. Backups

**Manual backup (recommended weekly and after major posting days):**

`File → Backup Database Now…` — saves a timestamped copy of `school_finance.db` to a
location you choose. Each backup is automatically verified with `PRAGMA integrity_check`.

**Automatic backup on exit:**

Every time you close the app, a timestamped backup is created in `backups/` and
integrity-verified. On startup, the most recent backup is also verified.

**Backup retention:**

Configurable in `Settings → Backup Retention Count` (default: keep the last 10 backups).

**Restoring a backup:**

1. Close the app.
2. Rename or move the current `data\school_finance.db` aside.
3. Copy your backup file into `data\` and rename it to `school_finance.db`.
4. Restart the app.

---

## 7. Data Model

All data lives in a single SQLite database (`data/school_finance.db`). The money model is:

> **A student owes money via `charges`** (term fees, opening balances from Excel import,
> ad-hoc charges) and **pays money via `payments`** (Cash / M-Pesa / In-Kind).
> **Balance = total charges − total payments − total waivers.**

This is always computed live, so it can never silently drift out of sync.

### Tables

| Table | Purpose |
|---|---|
| `students` | Student records (name, grade, stream, admission number, status, fee-waiver flag) |
| `terms` | Academic terms (year + term name, e.g. "2026 Term I") |
| `charges` | Fee charges linked to students and terms |
| `payments` | Payment records (amount, method, receipt number, can be voided) |
| `receipts` | PDF receipt metadata (file path, print count) linked to payments |
| `users` | Local user accounts (username, password hash, role, signature) |
| `audit_log` | Action log (username, action, detail, timestamp) |
| `school_info` | School name, address, contact, logo, payment details |
| `fee_structure` | Per-grade, per-term fee amounts |
| `payment_allocations` | Links payments to specific charges (for partial allocations) |
| `waivers` | Partial fee waivers (amount, reason, granted by, revocation support) |
| `statement_counter` | Per-year statement numbering |
| `bulk_payments` | Group payment records (total amount, reference, term) |
| `bulk_payment_items` | Individual student allocations within a bulk payment |

The schema is defined in `db/schema.sql` with **11 base tables** and migrations are
applied automatically in `db/database.py` (`_run_migrations()`) for backward compatibility
with older databases.

### Indexes

There are 8 indexes across the major query columns (student_id, charge_id, payment_id,
grade, term_id, waiver lookups) to keep the UI responsive.

---

## 8. Project Structure

```
school_finance/
├── main.py                    # Entry point: login loop + main window
├── db/
│   ├── __init__.py
│   ├── database.py            # SQLite connection singleton + schema init + migrations
│   └── schema.sql              # DDL for all tables + indexes
├── models/
│   ├── __init__.py
│   ├── student.py              # Student CRUD + balance calculation
│   ├── payment.py              # Charge/payment CRUD + receipt numbering
│   ├── term.py                 # Term CRUD
│   ├── user.py                 # Local auth (PBKDF2) + RBAC + audit logging
│   ├── fee_structure.py        # Per-grade fee definitions
│   ├── waiver.py               # Partial fee waiver management
│   ├── bulk_payment.py         # Bulk/group payment CRUD
│   └── school.py               # School info CRUD
├── services/
│   ├── __init__.py
│   ├── receipt_service.py      # PDF receipt generation (reportlab)
│   ├── statement_service.py    # PDF statement generation (reportlab)
│   ├── import_service.py       # Excel balance-sheet import (openpyxl)
│   ├── pdf_report_service.py   # Combined PDF report generation
│   ├── report_service.py       # Dashboard/income data queries
│   ├── export_service.py       # CSV/Excel export
│   └── config.py               # JSON settings management (school_finance/data/config.json)
├── ui/
│   ├── __init__.py
│   ├── constants.py            # Colours, fonts, theme
│   ├── main_window.py          # Main window, menu, tabs, dialogs
│   ├── login_dialog.py         # Login / first-run admin creation
│   ├── students_tab.py         # Student CRUD UI
│   ├── payments_tab.py         # Payment recording + receipt
│   ├── statements_tab.py       # Statement generation UI
│   ├── dashboard_tab.py        # Dashboard summary
│   ├── arrears_tab.py          # Outstanding balances report
│   ├── income_tab.py           # Income report
│   ├── fees_tab.py             # Fee structure management
│   ├── bulk_payments_tab.py    # Bulk payment UI
│   ├── waivers_tab.py          # Partial waiver UI
│   ├── users_tab.py            # User management (Admin only)
│   ├── import_tab.py           # Excel import UI
│   ├── settings_tab.py         # App settings UI
│   └── login_dialog.py         # Login / admin creation dialog
├── utils/
│   └── validation.py           # Input validation & sanitization
├── test/
│   ├── run_tests.py            # Test runner entry point
│   ├── test_receipt_service.py # Receipt generation tests
│   └── test_statement_service.py # Statement generation tests
├── data/                       # school_finance.db, config.json, app.log
├── receipts/                   # Generated PDF receipts
├── statements/                 # Generated PDF statements
├── backups/                    # Manual + auto backups
├── requirements.txt            # openpyxl, reportlab, pyinstaller
├── build_windows.bat           # Builds SchoolFinance.exe (Windows)
├── SchoolFinanceSetup.iss      # Inno Setup installer script
└── AUDIT.md                    # Technical audit report
```

---

## 9. Configuration

Application settings are stored in `data/config.json` (auto-created on first run with
defaults). Configurable options:

| Setting | Default | Description |
|---|---|---|
| `school_name` | *(empty)* | School name shown on receipts and statements |
| `currency_symbol` | `KES` | Currency symbol for monetary display |
| `backup_interval_minutes` | `0` | Auto-backup interval in minutes (0 = disabled) |
| `auto_backup_on_exit` | `true` | Create a backup when the app closes |
| `backup_retention_count` | `10` | Number of old backups to keep |
| `encryption_passphrase` | *(empty)* | Reserved for future SQLCipher encryption |
| `default_grade` | *(empty)* | Default grade for new students |
| `receipt_footer` | `School Finance System` | Footer text on PDF receipts |

Access via `Settings → App Settings…` in the menu bar or the **Settings** tab.

---

## 10. Running the Tests

A test suite (using Python's built-in `unittest` — no extra dependencies) covers receipt
generation, statement generation, input validation, and model operations.

```bash
cd school_finance
python -m unittest discover -s test -v
# or:
python test/run_tests.py
```

Tests use isolated temporary databases (`tempfile.mkdtemp()`) so they never touch your
real data.

---

## 11. Troubleshooting

- **"No module named tkinter"** when running from source on Linux:
  `sudo apt install python3-tk` (Debian/Ubuntu). Not needed on Windows — Tkinter ships
  with the standard Windows Python installer.

- **Antivirus flags the .exe**: Common false positive with PyInstaller-built executables
  from unsigned publishers. Add an exclusion, or code-sign the exe if your school has a
  certificate.

- **Lost your password**: No "forgot password" flow (offline, no email). Ask the person who
  set up the system to open `data\school_finance.db` with any SQLite browser and delete the
  row from the `users` table, then restart the app to create a fresh Admin account.

- **Window appears tiny/too large on high-DPI screens**: The app sets DPI awareness on
  Windows 8.1+ via `ctypes.windll.shcore.SetProcessDpiAwareness(1)`. On Windows 7 it
  falls back to `ctypes.windll.user32.SetProcessDPIAware()`.

- **Database corruption on startup**: The app runs `PRAGMA integrity_check` on every launch.
  If it fails, you'll see an error and the app won't proceed — restore from your most recent
  backup in `backups/`.

- **Import Legacy Excel doesn't recognise columns**: The import expects the first column to
  be a student identifier (full name or admission number), and balance columns to contain
  numeric values. See `AUDIT.md` for the column-classification logic.
