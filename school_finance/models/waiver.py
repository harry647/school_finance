"""Partial fee waiver management.

A waiver reduces the *net* amount a student owes for a specific charge
(typically a term fee) without altering the original gross charge amount.

    gross_fee      = charge.amount           (unchanged, always preserved)
    waiver_total   = SUM(active waivers)     (deductions applied)
    net_amount_due = gross_fee - waiver_total (what the student actually pays)

The waiver is linked to a concrete charge_id, which is already scoped to
(student_id, term_id), making every waiver inherently term-based.
Revocation is recorded in-place (revoked_at / revoked_reason) so the full
audit trail is preserved.
"""
import datetime

from db.database import get_connection


def add_waiver(student_id, amount, charge_id, reason=None, granted_by=None,
               granted_at=None):
    """Record a partial fee waiver against an existing charge.

    Args:
        student_id:  The student whose fee is reduced.
        amount:      Positive waiver amount (must not exceed available gross
                     fee on the charge after existing active waivers).
        charge_id:   The specific charge (term fee) being reduced.  This
                     also determines term_id.
        reason:      Human-readable justification (e.g. "Sibling discount").
        granted_by:  Username of the bursar recording the waiver.
        granted_at:  Optional explicit timestamp (defaults to now).

    Returns:
        waiver_id (int)

    Raises:
        ValueError: If the amount is invalid or exceeds the remaining
                    gross fee on the charge.
    """
    if amount is None or amount <= 0:
        raise ValueError("Waiver amount must be a positive number")

    conn = get_connection()

    charge = conn.execute(
        "SELECT amount, student_id, term_id FROM charges WHERE id = ?",
        (charge_id,),
    ).fetchone()
    if charge is None:
        raise ValueError(f"Charge id={charge_id} not found")
    if charge["student_id"] != student_id:
        raise ValueError(
            f"Charge id={charge_id} does not belong to student id={student_id}")

    existing = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) AS total FROM waivers "
        "WHERE charge_id = ? AND revoked_at IS NULL",
        (charge_id,),
    ).fetchone()["total"]

    gross = charge["amount"]
    remaining = gross - existing
    if amount > remaining:
        raise ValueError(
            f"Waiver amount {amount} exceeds remaining gross fee "
            f"{remaining:.2f} on charge id={charge_id} "
            f"(gross {gross:.2f}, already waived {existing:.2f})")

    ts = granted_at or datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    cur = conn.execute(
        "INSERT INTO waivers "
        "(student_id, term_id, charge_id, amount, reason, granted_by, granted_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (student_id, charge["term_id"], charge_id, amount,
         reason.strip() if reason else None,
         granted_by.strip() if granted_by else None,
         ts),
    )
    conn.commit()
    return cur.lastrowid


def get_waiver(waiver_id):
    conn = get_connection()
    return conn.execute("SELECT * FROM waivers WHERE id = ?", (waiver_id,)).fetchone()


def revoke_waiver(waiver_id, reason=None, revoked_by=None):
    """Revoke an active waiver.  The row is kept (not deleted) for audit."""
    import datetime as dt
    conn = get_connection()
    waiver = conn.execute(
        "SELECT * FROM waivers WHERE id = ?", (waiver_id,)).fetchone()
    if waiver is None:
        raise ValueError(f"Waiver id={waiver_id} not found")
    if waiver["revoked_at"] is not None:
        raise ValueError(f"Waiver id={waiver_id} is already revoked")

    ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    conn.execute(
        "UPDATE waivers SET revoked_at = ?, revoked_reason = ? "
        "WHERE id = ?",
        (ts, reason.strip() if reason else None, waiver_id),
    )
    conn.commit()
    return True


def get_active_waiver_total(charge_id):
    """Sum of *active* (non-revoked) waiver amounts for a single charge."""
    conn = get_connection()
    row = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) AS total FROM waivers "
        "WHERE charge_id = ? AND revoked_at IS NULL",
        (charge_id,),
    ).fetchone()
    return row["total"] if row else 0.0


def get_student_term_waiver_total(student_id, term_id, active_only=True):
    """Total active (or all) waiver amounts for a student in a term."""
    conn = get_connection()
    query = (
        "SELECT COALESCE(SUM(amount), 0) AS total FROM waivers "
        "WHERE student_id = ? AND term_id = ?"
    )
    if active_only:
        query += " AND revoked_at IS NULL"
    return conn.execute(query, (student_id, term_id)).fetchone()["total"]


def get_student_term_waivers(student_id, term_id, active_only=True):
    """Return waiver rows for a student in a term, joined with charge/term info."""
    conn = get_connection()
    query = (
        "SELECT w.*, c.amount AS gross_amount, c.description, "
        "t.term_name, t.year, "
        "COALESCE(SUM(w2.amount), 0) AS active_total "
        "FROM waivers w "
        "JOIN charges c ON w.charge_id = c.id "
        "JOIN terms t ON w.term_id = t.id "
        "LEFT JOIN waivers w2 ON w2.charge_id = w.charge_id AND w2.revoked_at IS NULL "
        "WHERE w.student_id = ? AND w.term_id = ? "
    )
    if active_only:
        query += " AND w.revoked_at IS NULL "
    query += " GROUP BY w.id ORDER BY w.granted_at"
    return conn.execute(query, (student_id, term_id)).fetchall()


def list_all_waivers(student_id=None, active_only=True):
    """List waivers across all students (for reports / management UI)."""
    conn = get_connection()
    query = (
        "SELECT w.*, s.full_name, s.grade, c.amount AS gross_amount, "
        "c.description, t.term_name, t.year "
        "FROM waivers w "
        "JOIN students s ON w.student_id = s.id "
        "JOIN charges c ON w.charge_id = c.id "
        "JOIN terms t ON w.term_id = t.id "
        "WHERE 1=1"
    )
    params = []
    if student_id is not None:
        query += " AND w.student_id = ?"
        params.append(student_id)
    if active_only:
        query += " AND w.revoked_at IS NULL"
    query += " ORDER BY s.grade, s.full_name, t.year, t.term_name, w.granted_at"
    return conn.execute(query, params).fetchall()


def get_student_waiver_summary(student_id):
    """Return a list of dicts summarising each student's partial waivers.

    Each dict contains:
        term_key  — "Term I 2025" (human-readable)
        gross_fee — original charge amount for that term
        waived    — total active waiver amount for that term
        net_fee   — gross_fee - waived
    """
    from models.term import list_terms as _list_terms
    from models.fee_structure import get_fee as _get_fee

    conn = get_connection()
    charges = conn.execute(
        "SELECT id, term_id, amount FROM charges WHERE student_id = ?",
        (student_id,),
    ).fetchall()
    term_ids = {c["term_id"] for c in charges if c["term_id"]}
    terms = {t["id"]: t for t in _list_terms()}

    result = []
    for tid in sorted(term_ids):
        if tid not in terms:
            continue
        term = terms[tid]
        term_charges = [c for c in charges if c["term_id"] == tid]
        gross = round(sum(c["amount"] for c in term_charges), 2)

        charge_ids = [str(c["id"]) for c in term_charges]
        placeholders = ",".join("?" * len(charge_ids))
        waived = conn.execute(
            f"SELECT COALESCE(SUM(amount), 0) AS total FROM waivers "
            f"WHERE charge_id IN ({placeholders}) AND revoked_at IS NULL",
            charge_ids,
        ).fetchone()["total"]
        waived = round(waived or 0.0, 2)

        result.append({
            "term_key": f"{term['term_name']} {term['year']}",
            "term_id": tid,
            "gross_fee": gross,
            "waived": waived,
            "net_fee": round(gross - waived, 2),
        })
    return result
