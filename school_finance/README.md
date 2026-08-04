# School Finance System (v1)

A small, offline, desktop finance app for a junior school: manage students,
record fee payments (Cash / M-Pesa / In-Kind), generate PDF receipts, and
generate PDF fee statements. Works on Windows 7, 8, 10 and 11. No internet
connection required to run it.

---

## 1. Quick Start (running from source, e.g. on Linux/Mac for development)

```bash
pip install -r requirements.txt
python main.py
```

On first launch you'll be asked to create an Admin username and password —
this is a local login only, nothing is sent anywhere.

## 2. Building a Windows .exe (no Python needed by the school)

This step is normally done **once**, on a Windows PC, by whoever is setting
the system up for the school.

1. If any of the school's computers run **Windows 7 or 8**, install
   **Python 3.8** on the Windows build machine (3.8 is the last version
   with official Windows 7 support):
   https://www.python.org/downloads/release/python-3810/
   (grab the "Windows x86-64 executable installer"). During setup you can
   leave "Add to PATH" unchecked — the build script finds it automatically
   either way, so it won't interfere with any other Python already
   installed on that machine.
   If every target PC is Windows 10/11, you can skip this and just use
   whatever Python you already have.
2. Copy this whole `school_finance` folder onto the Windows build PC.
3. Open the folder and double-click **`build_windows.bat`**
   (or run it from a Command Prompt inside the folder). It automatically
   looks for Python 3.8 first, and falls back to your default `python` if
   3.8 isn't installed.
4. When it finishes, your app is at `dist\SchoolFinance.exe`.

Copy `dist\SchoolFinance.exe` to any Windows 7/8/10/11 computer and just
double-click it — no installer, no Python required on that machine. On
first run it will create `data`, `receipts`, `statements` and `backups`
folders right next to the `.exe`.

**Important:** always keep `SchoolFinance.exe` together with its `data`
folder. The `data\school_finance.db` file is the entire database — that
one file is what you back up.

## 3. Everyday Use

- **Students tab** — add/edit/search students, filter by grade, see each
  student's live balance.
- **Payments tab** — pick a student, pick the term, enter the amount and
  payment method (Cash / M-Pesa / In-Kind), click **Save & Print Receipt**.
  A PDF receipt is generated automatically and opens for printing/saving.
- **Fee Statements tab** — pick a student, generate a full PDF statement
  showing every charge and every payment with a running balance.
- **Import Legacy Excel tab** — one-time tool to pull in your existing
  Grade 7/8/9-style balance sheet workbooks. Each non-zero balance column
  becomes an opening "charge" for that student/term, so their outstanding
  balance is preserved exactly. Already-imported students are skipped, not
  duplicated, so it's safe to re-run.

## 4. Backups

Use **File → Backup Database Now** in the app to save a timestamped copy
of `school_finance.db` anywhere you choose (USB stick, cloud-synced
folder, etc.). Do this regularly — weekly, and always after a big posting
day (e.g. start of term).

To restore a backup: close the app, rename/move the current
`data\school_finance.db` aside, then copy your backup file into `data\`
and rename it to `school_finance.db`.

## 5. Project Structure

```
school_finance/
├── main.py                 # entry point
├── db/                     # SQLite connection + schema
├── models/                 # student / payment / term / user data access
├── services/                # PDF receipt/statement generation, Excel import
├── ui/                      # Tkinter screens (login, students, payments, statements, import)
├── data/                    # school_finance.db lives here (created on first run)
├── receipts/                # generated receipt PDFs
├── statements/               # generated fee statement PDFs
├── backups/                  # manual backups land here by default
├── requirements.txt
└── build_windows.bat         # builds the standalone .exe
```

## 6. Data Model (in short)

- A student **owes** money via `charges` (term fees, or imported opening
  balances).
- A student **pays** money via `payments` (Cash / M-Pesa / In-Kind).
- **Balance = total charges − total payments.** Always computed live, so
  it can never silently drift out of sync the way separate spreadsheet
  tabs can.

## 7. Roadmap (not in this version, on purpose — v1 stays small)

- Multi-user roles (Bursar vs Clerk vs Head Teacher)
- Termly income-by-method reports, defaulters list
- Excel export of any report
- Optional cloud backup
- Multi-school support

## 8. Troubleshooting

- **"No module named tkinter"** when running from source on Linux: install
  it with `sudo apt install python3-tk` (Debian/Ubuntu) — not needed on
  Windows, Tkinter ships with the standard Windows Python installer.
- **Antivirus flags the .exe**: this is a common false positive with
  PyInstaller-built executables from unsigned publishers. You can safely
  add an exclusion, or code-sign the exe if your school has a certificate.
- **Lost your password**: there's no "forgot password" flow in v1 (no
  internet/email to send a reset). Ask the person who set up the system
  to open the `data\school_finance.db` file and delete the row from the
  `users` table using any SQLite browser, then restart the app to create
  a fresh Admin account.
