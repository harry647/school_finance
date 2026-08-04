-- School Finance System schema
-- Money model: a student owes money via `charges` (fees/opening balances)
-- and pays money via `payments`. Balance = sum(charges) - sum(payments).
-- This cleanly supports importing legacy balance-only spreadsheets
-- (imported as charges) as well as normal day-to-day fee billing later.

CREATE TABLE IF NOT EXISTS students (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    admission_no  TEXT UNIQUE,
    full_name     TEXT NOT NULL,
    grade         TEXT NOT NULL,
    stream        TEXT,
    status        TEXT NOT NULL DEFAULT 'Active',   -- Active / Left / Graduated
    remarks       TEXT,
    date_added    TEXT NOT NULL DEFAULT (datetime('now')),
    fee_waived    INTEGER NOT NULL DEFAULT 0,        -- 0 = fees apply, 1 = full fee waiver
    waiver_reason TEXT,                              -- human-readable reason for the waiver
    waiver_date   TEXT                              -- timestamp when the waiver was granted
);

CREATE TABLE IF NOT EXISTS terms (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    year          INTEGER NOT NULL,
    term_name     TEXT NOT NULL,          -- "Term I", "Term II", "Term III"
    UNIQUE(year, term_name)
);

CREATE TABLE IF NOT EXISTS charges (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id    INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    term_id       INTEGER REFERENCES terms(id),
    amount        REAL NOT NULL,
    description   TEXT,                   -- "Term fee", "Imported opening balance", etc.
    date_added    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS payments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id    INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    term_id       INTEGER REFERENCES terms(id),
    amount        REAL NOT NULL,
    method        TEXT NOT NULL,          -- Cash / M-Pesa / In-Kind
    mpesa_code    TEXT,
    in_kind_desc  TEXT,
    date_paid     TEXT NOT NULL DEFAULT (datetime('now')),
    received_by   TEXT,
    receipt_no    TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS receipts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_id    INTEGER NOT NULL REFERENCES payments(id) ON DELETE CASCADE,
    receipt_no    TEXT UNIQUE NOT NULL,
    file_path     TEXT,
    date_issued   TEXT NOT NULL DEFAULT (datetime('now')),
    print_count   INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name     TEXT,                              -- Display name
    signature_path TEXT,                            -- Path to signature image file
    role          TEXT NOT NULL DEFAULT 'Bursar',  -- Admin / Bursar / Clerk
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT,                             -- Last profile/password change
    last_login    TEXT,                             -- Timestamp of last successful login
    is_active     INTEGER NOT NULL DEFAULT 1,      -- 1 = active, 0 = soft-deleted
    CHECK (role IN ('Admin', 'Bursar', 'Clerk'))
);

CREATE TABLE IF NOT EXISTS audit_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT,
    action        TEXT,
    detail        TEXT,
    timestamp     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS school_info (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    school_name     TEXT,
    address         TEXT,
    phone           TEXT,
    email           TEXT,
    motto           TEXT,
    logo_path       TEXT,
    payment_details TEXT
);

CREATE TABLE IF NOT EXISTS fee_structure (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    grade         TEXT NOT NULL,
    term_id       INTEGER NOT NULL REFERENCES terms(id),
    amount        REAL NOT NULL,
    description   TEXT DEFAULT 'Term fee',
    UNIQUE(grade, term_id)
);

CREATE TABLE IF NOT EXISTS payment_allocations (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_id    INTEGER NOT NULL REFERENCES payments(id) ON DELETE CASCADE,
    charge_id     INTEGER NOT NULL REFERENCES charges(id) ON DELETE CASCADE,
    amount        REAL NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

-- --------------------------------------------------------------------------
-- Partial fee waivers
--
-- A *waiver* reduces the net amount a student owes for a specific charge
-- (typically a term fee) without altering the original gross charge amount.
--
--   gross_fee       = charge.amount        (unchanged, always preserved)
--   waiver_applied  = SUM(waivers.amount)   (sum of active waivers)
--   net_amount_due  = gross_fee - waiver_applied
--
-- Design notes
--   * charge_id is NOT NULL: a waiver always targets a concrete charge record,
--     which is already scoped to (student_id, term_id).  This makes every
--     waiver inherently "term-based" while remaining auditable per charge.
--   * amount must be positive and may never exceed the charge's gross amount
--     (enforced by a CHECK + by application logic).
--   * Revocation is recorded via revoked_at / revoked_reason rather than
--     deleting rows, so the full audit trail is preserved.
--   * granted_by stores the bursar username for traceability.
-- ---------------------------------------------------------------------------
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

CREATE INDEX IF NOT EXISTS idx_charges_student ON charges(student_id);
CREATE INDEX IF NOT EXISTS idx_payments_student ON payments(student_id);
CREATE INDEX IF NOT EXISTS idx_students_grade ON students(grade);
CREATE INDEX IF NOT EXISTS idx_fee_structure_grade_term ON fee_structure(grade, term_id);
CREATE INDEX IF NOT EXISTS idx_payment_allocations_payment ON payment_allocations(payment_id);
CREATE INDEX IF NOT EXISTS idx_payment_allocations_charge ON payment_allocations(charge_id);
CREATE INDEX IF NOT EXISTS idx_waivers_student ON waivers(student_id);
CREATE INDEX IF NOT EXISTS idx_waivers_charge ON waivers(charge_id);
