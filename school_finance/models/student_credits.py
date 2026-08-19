"""Student credit (overpayment) tracking and reimbursement."""
from db.database import get_connection


def add_credit(student_id, amount, reason="Overpayment", notes=None):
    """Record a new credit for a student.

    ``amount`` is the full credit amount.  ``remaining`` starts equal to
    ``amount`` and is reduced as the credit is applied to charges or refunded.
    """
    if amount <= 0:
        raise ValueError("amount must be greater than zero")
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO student_credits (student_id, amount, remaining, reason, notes) "
        "VALUES (?, ?, ?, ?, ?)",
        (student_id, amount, amount, reason, notes),
    )
    conn.commit()
    return cur.lastrowid


def get_credits_for_student(student_id, include_reimbursed=False):
    """Return all credit records for a student, optionally filtering out
    reimbursed ones."""
    conn = get_connection()
    query = "SELECT * FROM student_credits WHERE student_id = ?"
    params = [student_id]
    if not include_reimbursed:
        query += " AND reimbursed = 0"
    query += " ORDER BY created_at ASC"
    return conn.execute(query, params).fetchall()


def get_available_credit(student_id):
    """Total remaining (unreimbursed, unapplied) credit for a student."""
    rows = get_credits_for_student(student_id, include_reimbursed=False)
    return sum(r["remaining"] for r in rows)


def apply_credits_to_charge(conn, student_id, charge_id, needed):
    """Apply available credits to a specific charge up to *needed*.

    Uses the oldest credits first (FIFO on credit creation order).
    Returns the total amount applied.
    """
    if needed <= 0:
        return 0.0
    credits = conn.execute(
        "SELECT * FROM student_credits WHERE student_id = ? AND reimbursed = 0 "
        "AND remaining > 0 ORDER BY created_at ASC, id ASC",
        (student_id,),
    ).fetchall()
    applied = 0.0
    for credit in credits:
        if needed <= 0:
            break
        take = min(credit["remaining"], needed)
        new_remaining = round(credit["remaining"] - take, 2)
        conn.execute(
            "UPDATE student_credits SET remaining = ? WHERE id = ?",
            (new_remaining, credit["id"]),
        )
        conn.execute(
            "INSERT INTO payment_allocations (payment_id, charge_id, amount) "
            "VALUES (NULL, ?, ?)",
            (charge_id, take),
        )
        needed -= take
        applied += take
    return applied


def reimburse_credit(credit_id, reimbursed_by=None, notes=None):
    """Mark a credit as reimbursed and zero out the remaining amount.

    Raises ValueError if the credit is already fully reimbursed or if
    there is still remaining balance that should have been applied first.
    """
    conn = get_connection()
    credit = conn.execute(
        "SELECT * FROM student_credits WHERE id = ?", (credit_id,)
    ).fetchone()
    if credit is None:
        raise ValueError("Credit not found")
    if credit["reimbursed"]:
        raise ValueError("Credit is already reimbursed")
    import datetime
    conn.execute(
        "UPDATE student_credits SET reimbursed = 1, remaining = 0, "
        "reimbursed_at = ?, reimbursed_by = ?, notes = ? WHERE id = ?",
        (
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            reimbursed_by,
            notes,
            credit_id,
        ),
    )
    conn.commit()


def list_reimbursable_credits(grade=None):
    """Return credits for students in *grade* (default highest grade in chain)
    that are not yet reimbursed and have a remaining balance.

    A credit is considered reimbursable when the student's current grade
    is the highest in the chain or the student's status is Left / Graduated.
    """
    from models.student import GRADE_CHAIN
    highest_grade = GRADE_CHAIN[-1]
    conn = get_connection()
    query = (
        "SELECT sc.*, s.full_name, s.grade, s.admission_no, s.status "
        "FROM student_credits sc "
        "JOIN students s ON sc.student_id = s.id "
        "WHERE sc.reimbursed = 0 AND sc.remaining > 0 "
    )
    params = []
    if grade:
        query += " AND s.grade = ?"
        params.append(grade)
    else:
        query += " AND (s.grade = ? OR s.status IN ('Left', 'Graduated'))"
        params.append(highest_grade)
    query += " ORDER BY s.grade, s.full_name, sc.created_at"
    return conn.execute(query, params).fetchall()


def get_student_credit_summary(student_id):
    """Return a summary of credits for a student.

    Returns dict with total_credited, total_remaining, total_reimbursed,
    and count of active (unreimbursed) credit records.
    """
    rows = get_credits_for_student(student_id, include_reimbursed=True)
    total_credited = sum(r["amount"] for r in rows)
    total_remaining = sum(r["remaining"] for r in rows if not r["reimbursed"])
    total_reimbursed = sum(r["amount"] - r["remaining"] for r in rows if r["reimbursed"])
    active_count = sum(1 for r in rows if not r["reimbursed"] and r["remaining"] > 0)
    return {
        "total_credited": round(total_credited, 2),
        "total_remaining": round(total_remaining, 2),
        "total_reimbursed": round(total_reimbursed, 2),
        "active_count": active_count,
    }
