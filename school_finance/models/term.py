"""Term (Term I / II / III per year) CRUD."""
from db.database import get_connection


def get_or_create_term(year, term_name):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM terms WHERE year = ? AND term_name = ?", (year, term_name)
    ).fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        "INSERT INTO terms (year, term_name) VALUES (?, ?)", (year, term_name)
    )
    conn.commit()
    return cur.lastrowid


def list_terms():
    conn = get_connection()
    return conn.execute(
        "SELECT * FROM terms ORDER BY year, "
        "CASE term_name WHEN 'Term I' THEN 1 WHEN 'Term II' THEN 2 "
        "WHEN 'Term III' THEN 3 ELSE 4 END"
    ).fetchall()


def get_term(term_id):
    conn = get_connection()
    return conn.execute("SELECT * FROM terms WHERE id = ?", (term_id,)).fetchone()


def get_current_term():
    conn = get_connection()
    return conn.execute(
        "SELECT * FROM terms ORDER BY year DESC, "
        "CASE term_name WHEN 'Term I' THEN 1 WHEN 'Term II' THEN 2 "
        "WHEN 'Term III' THEN 3 ELSE 4 END DESC LIMIT 1"
    ).fetchone()


def get_terms_for_year(year):
    conn = get_connection()
    return conn.execute(
        "SELECT * FROM terms WHERE year = ? ORDER BY "
        "CASE term_name WHEN 'Term I' THEN 1 WHEN 'Term II' THEN 2 "
        "WHEN 'Term III' THEN 3 ELSE 4 END",
        (year,),
    ).fetchall()
