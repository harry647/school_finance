"""Fee structure CRUD: standard charges per grade/term."""
from db.database import get_connection


def set_fee(grade, term_id, amount, description="Term fee"):
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO fee_structure (grade, term_id, amount, description) "
        "VALUES (?, ?, ?, ?)",
        (grade.strip(), term_id, amount, description),
    )
    conn.commit()


def get_fee(grade, term_id):
    """Get fee for a specific grade and term. Returns None if not set."""
    conn = get_connection()
    return conn.execute(
        "SELECT f.*, t.term_name, t.year FROM fee_structure f "
        "JOIN terms t ON f.term_id = t.id "
        "WHERE f.grade = ? AND f.term_id = ?",
        (grade, term_id),
    ).fetchone()


def get_fee_by_year_term(grade, year, term_name):
    """Get fee for a specific grade, year, and term name."""
    conn = get_connection()
    return conn.execute(
        "SELECT f.*, t.term_name, t.year FROM fee_structure f "
        "JOIN terms t ON f.term_id = t.id "
        "WHERE f.grade = ? AND t.year = ? AND t.term_name = ?",
        (grade, year, term_name),
    ).fetchone()


def list_fees(grade=None, term_id=None):
    conn = get_connection()
    query = "SELECT f.*, t.term_name, t.year FROM fee_structure f " \
            "LEFT JOIN terms t ON f.term_id = t.id WHERE 1=1"
    params = []
    if grade:
        query += " AND f.grade = ?"
        params.append(grade)
    if term_id:
        query += " AND f.term_id = ?"
        params.append(term_id)
    query += " ORDER BY t.year, f.grade"
    return conn.execute(query, params).fetchall()


def delete_fee(grade, term_id):
    conn = get_connection()
    conn.execute(
        "DELETE FROM fee_structure WHERE grade = ? AND term_id = ?",
        (grade, term_id),
    )
    conn.commit()


def get_missing_fee_structures(grade, year):
    """Get list of term names for a grade/year that don't have fees set.

    Returns list of dicts: [{'term_name': 'Term I', 'term_id': 1}, ...]
    """
    conn = get_connection()
    terms = conn.execute(
        "SELECT * FROM terms WHERE year = ? ORDER BY "
        "CASE term_name WHEN 'Term I' THEN 1 WHEN 'Term II' THEN 2 "
        "WHEN 'Term III' THEN 3 ELSE 4 END",
        (year,),
    ).fetchall()

    missing = []
    for term in terms:
        fee = conn.execute(
            "SELECT id FROM fee_structure WHERE grade = ? AND term_id = ?",
            (grade, term["id"]),
        ).fetchone()
        if fee is None:
            missing.append({
                "term_name": term["term_name"],
                "term_id": term["id"],
                "year": year,
            })
    return missing


def validate_fee_for_student_term(student_id, term_id):
    """Check if a fee structure exists for the student's grade in this term.

    Returns (is_valid, missing_info) where missing_info is a string
    describing what's missing, or None if valid.
    """
    conn = get_connection()
    student = conn.execute(
        "SELECT s.grade, t.year, t.term_name FROM students s "
        "JOIN terms t ON t.id = ? WHERE s.id = ?",
        (term_id, student_id),
    ).fetchone()
    if not student:
        return False, "Student not found"

    fee = conn.execute(
        "SELECT id FROM fee_structure WHERE grade = ? AND term_id = ?",
        (student["grade"], term_id),
    ).fetchone()
    if fee is None:
        return False, f"No fee structure set for {student['grade']} - {student['term_name']} {student['year']}"
    return True, None


def has_complete_fee_structure(grade, year):
    """Check if all 3 terms have fees set for a grade in a given year."""
    missing = get_missing_fee_structures(grade, year)
    return len(missing) == 0, missing
