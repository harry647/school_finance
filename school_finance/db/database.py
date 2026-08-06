"""Database connection helper.

Everything lives in one SQLite file: data/school_finance.db
Copying that one file IS the backup.
"""
import logging
import os
import sys
import sqlite3

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
    SCHEMA_PATH = os.path.join(getattr(sys, "_MEIPASS", BASE_DIR), "db", "schema.sql")
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")

DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "school_finance.db")
LOG_PATH = os.path.join(DATA_DIR, "app.log")

_connection = None

logger = logging.getLogger("school_finance")
logger.setLevel(logging.DEBUG)
try:
    _handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    _handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(_handler)
except Exception:
    pass


def get_connection():
    """Return a single shared SQLite connection, creating the DB on first use."""
    global _connection
    if _connection is None:
        os.makedirs(DATA_DIR, exist_ok=True)
        first_run = not os.path.exists(DB_PATH)
        try:
            _connection = sqlite3.connect(DB_PATH)
        except sqlite3.Error as e:
            logger.error("Failed to open database: %s", e)
            raise
        _connection.row_factory = sqlite3.Row
        _connection.execute("PRAGMA foreign_keys = ON")
        if first_run:
            init_db(_connection)
            _run_migrations(_connection)
        else:
            _run_migrations(_connection)
        integrity = _connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            logger.error("Database integrity check failed: %s", integrity)
            raise RuntimeError(
                f"Database integrity check failed: {integrity}. "
                "Please restore from a backup."
            )
        logger.info("Database connection established successfully")
    return _connection


def init_db(conn):
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()


def _run_migrations(conn):
    tables = [r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    if "fee_structure" not in tables:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS fee_structure (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                grade         TEXT NOT NULL,
                term_id       INTEGER NOT NULL REFERENCES terms(id),
                amount        REAL NOT NULL,
                description   TEXT DEFAULT 'Term fee',
                UNIQUE(grade, term_id)
            );
            CREATE INDEX IF NOT EXISTS idx_fee_structure_grade_term
                ON fee_structure(grade, term_id);
        """)
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(payments)").fetchall()]
    if "voided" not in cols:
        conn.execute("ALTER TABLE payments ADD COLUMN voided INTEGER DEFAULT 0")
    if "void_reason" not in cols:
        conn.execute("ALTER TABLE payments ADD COLUMN void_reason TEXT")
    student_cols = [r["name"] for r in conn.execute("PRAGMA table_info(students)").fetchall()]
    if "stream" not in student_cols:
        conn.execute("ALTER TABLE students ADD COLUMN stream TEXT")
    if "fee_waived" not in student_cols:
        conn.execute("ALTER TABLE students ADD COLUMN fee_waived INTEGER NOT NULL DEFAULT 0")
    if "waiver_reason" not in student_cols:
        conn.execute("ALTER TABLE students ADD COLUMN waiver_reason TEXT")
    if "waiver_date" not in student_cols:
        conn.execute("ALTER TABLE students ADD COLUMN waiver_date TEXT")
    receipt_cols = [r["name"] for r in conn.execute("PRAGMA table_info(receipts)").fetchall()]
    if "print_count" not in receipt_cols:
        conn.execute("ALTER TABLE receipts ADD COLUMN print_count INTEGER DEFAULT 1")
    receipt_not_null = conn.execute("PRAGMA table_info(receipts)").fetchall()
    for col in receipt_not_null:
        if col["name"] == "payment_id" and col["notnull"] == 1:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS receipts_new (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    payment_id    INTEGER REFERENCES payments(id) ON DELETE CASCADE,
                    receipt_no    TEXT UNIQUE NOT NULL,
                    file_path     TEXT,
                    date_issued   TEXT NOT NULL DEFAULT (datetime('now')),
                    print_count   INTEGER NOT NULL DEFAULT 1
                )
            """)
            conn.execute("""
                INSERT INTO receipts_new (id, payment_id, receipt_no, file_path, date_issued, print_count)
                SELECT id, payment_id, receipt_no, file_path, date_issued, print_count FROM receipts
            """)
            conn.execute("DROP TABLE receipts")
            conn.execute("ALTER TABLE receipts_new RENAME TO receipts")
            break
    if "payment_allocations" not in tables:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS payment_allocations (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                payment_id    INTEGER NOT NULL REFERENCES payments(id) ON DELETE CASCADE,
                charge_id     INTEGER NOT NULL REFERENCES charges(id) ON DELETE CASCADE,
                amount        REAL NOT NULL,
                created_at    TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_payment_allocations_payment
                ON payment_allocations(payment_id);
            CREATE INDEX IF NOT EXISTS idx_payment_allocations_charge
                ON payment_allocations(charge_id);
        """)
    if "waivers" not in tables:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS waivers (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id      INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                term_id         INTEGER NOT NULL REFERENCES terms(id),
                charge_id       INTEGER NOT NULL REFERENCES charges(id) ON DELETE CASCADE,
                amount          REAL NOT NULL CHECK (amount > 0),
                reason          TEXT,
                granted_by      TEXT,
                granted_at      TEXT NOT NULL DEFAULT (datetime('now')),
                revoked_at      TEXT,
                revoked_reason  TEXT,
                CHECK (revoked_at IS NULL OR revoked_reason IS NOT NULL)
            );
            CREATE INDEX IF NOT EXISTS idx_waivers_student ON waivers(student_id);
            CREATE INDEX IF NOT EXISTS idx_waivers_charge ON waivers(charge_id);
        """)
    user_cols = [r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
    if "full_name" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN full_name TEXT")
    if "signature_path" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN signature_path TEXT")
    if "created_at" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN created_at TEXT")
        conn.execute("UPDATE users SET created_at = datetime('now') WHERE created_at IS NULL")
    if "updated_at" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN updated_at TEXT")
    if "last_login" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN last_login TEXT")
    if "is_active" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
    if "statement_counter" not in tables:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS statement_counter (
                year         INTEGER PRIMARY KEY,
                last_number  INTEGER NOT NULL DEFAULT 0
            );
        """)
    if "bulk_payments" not in tables:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS bulk_payments (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                payer_name    TEXT NOT NULL,
                payer_contact TEXT,
                method        TEXT NOT NULL,
                reference_no  TEXT,
                receipt_no    TEXT UNIQUE,
                term_id       INTEGER REFERENCES terms(id),
                total_amount  REAL NOT NULL,
                date_paid     TEXT NOT NULL DEFAULT (datetime('now')),
                notes         TEXT,
                created_at    TEXT NOT NULL DEFAULT (datetime('now')),
                created_by    TEXT
            );
            CREATE TABLE IF NOT EXISTS bulk_payment_items (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                bulk_payment_id INTEGER NOT NULL REFERENCES bulk_payments(id) ON DELETE CASCADE,
                student_id      INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                amount          REAL NOT NULL,
                payment_id      INTEGER REFERENCES payments(id) ON DELETE SET NULL,
                notes           TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_bulk_payments_term
                ON bulk_payments(term_id);
            CREATE INDEX IF NOT EXISTS idx_bulk_payment_items_bulk
                ON bulk_payment_items(bulk_payment_id);
        """)
    bulk_cols = [r["name"] for r in conn.execute("PRAGMA table_info(bulk_payments)").fetchall()]
    if "receipt_no" not in bulk_cols:
        conn.execute("ALTER TABLE bulk_payments ADD COLUMN receipt_no TEXT")
    conn.commit()


def close_connection():
    global _connection
    if _connection is not None:
        _connection.close()
        _connection = None
        logger.info("Database connection closed")