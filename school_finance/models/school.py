"""Single-row school information settings CRUD.

Since there is one school per install, the school_info table holds exactly
one row (id = 1, enforced by a CHECK constraint). These functions get/set
that row, creating it on first save.
"""
from db.database import get_connection

BLANK_SCHOOL_INFO = {
    "school_name": "",
    "address": "",
    "phone": "",
    "email": "",
    "motto": "",
    "logo_path": "",
    "payment_details": "",
}


def get_school_info():
    """Return the single school_info row as a dict, or blank defaults."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM school_info WHERE id = 1").fetchone()
    if row is None:
        return dict(BLANK_SCHOOL_INFO)
    return dict(row)


def update_school_info(school_name, address, phone, email, motto,
                       logo_path=None, payment_details=None):
    """Insert or replace the single school_info row (id = 1)."""
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO school_info "
        "(id, school_name, address, phone, email, motto, logo_path, "
        " payment_details) "
        "VALUES (1, ?, ?, ?, ?, ?, ?, ?)",
        (
            school_name.strip(),
            address.strip(),
            phone.strip(),
            email.strip(),
            motto.strip(),
            (logo_path or "").strip(),
            (payment_details or "").strip(),
        ),
    )
    conn.commit()