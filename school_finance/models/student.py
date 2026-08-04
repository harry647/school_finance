"""Student CRUD + balance calculation with FIFO debt prioritization."""
from db.database import get_connection


def _get_charge_waiver_totals(student_id):
    """Return {charge_id: active_waiver_total} for a student.

    Only non-revoked waivers are counted.  This is used to reduce the
    effective (net) amount of each charge when calculating balances.
    """
    conn = get_connection()
    rows = conn.execute(
        "SELECT charge_id, COALESCE(SUM(amount), 0) AS total "
        "FROM waivers "
        "WHERE student_id = ? AND revoked_at IS NULL "
        "GROUP BY charge_id",
        (student_id,),
    ).fetchall()
    return {r["charge_id"]: r["total"] for r in rows}


def add_student(full_name, grade, admission_no=None, stream=None, remarks=None,
                status="Active", fee_waived=0, waiver_reason=None, waiver_date=None):
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO students (admission_no, full_name, grade, stream, status, remarks, "
        "fee_waived, waiver_reason, waiver_date) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (admission_no, full_name.strip(), grade.strip(), stream, status, remarks,
         fee_waived, waiver_reason, waiver_date),
    )
    conn.commit()
    return cur.lastrowid


ALLOWED_COLUMNS = {"full_name", "grade", "admission_no", "stream", "remarks", "status",
                   "fee_waived", "waiver_reason", "waiver_date"}


def update_student(student_id, full_name=None, grade=None, admission_no=None,
                   stream=None, remarks=None, status=None,
                   fee_waived=None, waiver_reason=None, waiver_date=None, **kwargs):
    conn = get_connection()
    fields, values = [], []
    updates = {
        "full_name": full_name, "grade": grade, "admission_no": admission_no,
        "stream": stream, "remarks": remarks, "status": status,
        "fee_waived": fee_waived, "waiver_reason": waiver_reason,
        "waiver_date": waiver_date
    }
    updates.update(kwargs)
    for col, val in updates.items():
        if val is not None:
            if col not in ALLOWED_COLUMNS:
                raise ValueError(f"Invalid column name: {col}")
            fields.append(f"{col} = ?")
            values.append(val)
    if not fields:
        return
    values.append(student_id)
    conn.execute("UPDATE students SET " + ", ".join(fields) + " WHERE id = ?", values)
    conn.commit()


def delete_student(student_id):
    conn = get_connection()
    conn.execute("DELETE FROM students WHERE id = ?", (student_id,))
    conn.commit()


def get_student(student_id):
    conn = get_connection()
    return conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()


def list_students(grade=None, stream=None, search=None):
    conn = get_connection()
    query = "SELECT * FROM students WHERE 1=1"
    params = []
    if grade:
        query += " AND grade = ?"
        params.append(grade)
    if stream:
        query += " AND stream = ?"
        params.append(stream)
    if search:
        query += " AND (full_name LIKE ? OR admission_no LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])
    query += " ORDER BY grade, stream, full_name"
    return conn.execute(query, params).fetchall()


def list_grades():
    conn = get_connection()
    rows = conn.execute("SELECT DISTINCT grade FROM students ORDER BY grade").fetchall()
    return [r["grade"] for r in rows]


def list_streams(grade=None):
    conn = get_connection()
    query = "SELECT DISTINCT stream FROM students WHERE stream IS NOT NULL AND stream != ''"
    params = []
    if grade:
        query += " AND grade = ?"
        params.append(grade)
    query += " ORDER BY stream"
    return [r.get("stream", "") for r in conn.execute(query, params).fetchall()]


def calculate_student_balances(student_id):
    """Calculate per-term balances using FIFO debt prioritization.

    Returns a dict: {term_id: balance} where balance is the remaining
    unpaid amount for that term after all payments are allocated to
    the oldest charges first.

    Students with a full fee waiver always have zero balances.

    Partial waivers (from the ``waivers`` table) reduce the *effective*
    charge amount so that the balance reflects the net amount due:

        gross_fee      = charge.amount
        waiver_total   = SUM(active waivers on this charge)
        net_amount     = gross_fee - waiver_total
        balance        = net_amount - SUM(payments allocated here)
    """
    conn = get_connection()

    if is_fee_waived(student_id):
        return {}

    waiver_totals = _get_charge_waiver_totals(student_id)

    charges = conn.execute(
        "SELECT c.id, c.amount, c.term_id, t.year, t.term_name, c.date_added FROM charges c "
        "JOIN terms t ON c.term_id = t.id "
        "WHERE c.student_id = ? "
        "ORDER BY t.year ASC, "
        "CASE t.term_name WHEN 'Term I' THEN 1 WHEN 'Term II' THEN 2 WHEN 'Term III' THEN 3 END ASC, "
        "c.date_added ASC",
        (student_id,),
    ).fetchall()

    payments = conn.execute(
        "SELECT p.id, p.amount, p.date_paid FROM payments p "
        "WHERE p.student_id = ? AND p.voided = 0 "
        "ORDER BY p.date_paid ASC",
        (student_id,),
    ).fetchall()

    charge_remaining = {
        c["id"]: c["amount"] - waiver_totals.get(c["id"], 0.0)
        for c in charges
    }
    term_charges = {}
    term_paid = {}

    for charge in charges:
        net = charge["amount"] - waiver_totals.get(charge["id"], 0.0)
        term_charges[charge["term_id"]] = term_charges.get(charge["term_id"], 0.0) + net

    for payment in payments:
        remaining = payment["amount"]
        for charge in charges:
            if remaining <= 0:
                break
            if charge_remaining[charge["id"]] <= 0:
                continue
            allocation = min(remaining, charge_remaining[charge["id"]])
            charge_remaining[charge["id"]] -= allocation
            remaining -= allocation
            term_paid[charge["term_id"]] = term_paid.get(charge["term_id"], 0.0) + allocation

    term_balances = {}
    for term_id in set(list(term_charges.keys()) + list(term_paid.keys())):
        balance = term_charges.get(term_id, 0.0) - term_paid.get(term_id, 0.0)
        term_balances[term_id] = round(balance, 2)

    return term_balances


def get_term_fee_breakdown(student_id, term_id):
    """Return gross / waived / net / paid / balance for one student×term.

    This is the canonical three-way split that receipts and statements
    need to display:

        gross_fee      — original fee charged (unchanged, always preserved)
        waiver_total   — sum of all active partial waivers
        net_amount     — gross_fee minus waiver_total (what the student
                         actually owes)
        total_paid     — sum of payments allocated to this term's charges
                         via FIFO
        balance        — net_amount minus total_paid (amount still owed)
    """
    conn = get_connection()
    waiver_totals = _get_charge_waiver_totals(student_id)

    charges = conn.execute(
        "SELECT id, amount, description FROM charges "
        "WHERE student_id = ? AND term_id = ? "
        "ORDER BY date_added",
        (student_id, term_id),
    ).fetchall()

    if not charges:
        fee_info = conn.execute(
            "SELECT f.amount, f.description, t.term_name, t.year FROM fee_structure f "
            "JOIN terms t ON f.term_id = t.id WHERE t.id = ?",
            (term_id,),
        ).fetchone()
        return {
            "gross_fee": 0.0,
            "waiver_total": 0.0,
            "net_amount": 0.0,
            "total_paid": 0.0,
            "balance": 0.0,
            "term_name": fee_info["term_name"] if fee_info else None,
            "year": fee_info["year"] if fee_info else None,
        }

    gross_fee = 0.0
    waiver_total = 0.0
    for ch in charges:
        gross_fee += ch["amount"]
        waiver_total += waiver_totals.get(ch["id"], 0.0)

    total_paid = conn.execute(
        "SELECT COALESCE(SUM(pa.amount), 0) AS total "
        "FROM payment_allocations pa "
        "JOIN charges c ON pa.charge_id = c.id "
        "WHERE c.student_id = ? AND c.term_id = ? "
        "AND pa.payment_id IN ("
        "    SELECT id FROM payments WHERE student_id = ? AND voided = 0"
        ")",
        (student_id, term_id, student_id),
    ).fetchone()["total"]

    net_amount = round(gross_fee - waiver_total, 2)
    balance = round(net_amount - (total_paid or 0.0), 2)

    return {
        "gross_fee": round(gross_fee, 2),
        "waiver_total": round(waiver_total, 2),
        "net_amount": net_amount,
        "total_paid": round(total_paid or 0.0, 2),
        "balance": balance,
    }


def get_balance(student_id):
    """Total outstanding balance using FIFO debt prioritization."""
    balances = calculate_student_balances(student_id)
    return round(sum(max(b, 0) for b in balances.values()), 2)


def get_term_balance(student_id, term_id):
    """Get the balance for a specific term after FIFO allocation."""
    balances = calculate_student_balances(student_id)
    return balances.get(term_id, 0.0)


def get_current_term_balance(student_id):
    """Get the cumulative balance up to and including the current term."""
    from models.term import get_current_term
    current_term = get_current_term()
    if not current_term:
        return get_balance(student_id)

    balances = calculate_student_balances(student_id)
    conn = get_connection()

    all_terms = conn.execute(
        "SELECT id FROM terms ORDER BY year ASC, "
        "CASE term_name WHEN 'Term I' THEN 1 WHEN 'Term II' THEN 2 WHEN 'Term III' THEN 3 END ASC"
    ).fetchall()
    term_ids = [t["id"] for t in all_terms]

    current_index = term_ids.index(current_term["id"]) if current_term["id"] in term_ids else len(term_ids) - 1
    cumulative = 0.0
    for tid in term_ids[:current_index + 1]:
        cumulative += balances.get(tid, 0.0)
    return round(cumulative, 2)


def list_students_with_balance(grade=None, search=None):
    """Convenience: students + their current balance, for the dashboard table.

    Waived students appear in the list with a zero balance and
    ``fee_waived = 1`` so the UI can flag them distinctly.
    """
    students = list_students(grade=grade, search=search)
    result = []
    for s in students:
        d = dict(s)
        d["balance"] = get_balance(s["id"])
        result.append(d)
    return result


def promote_students(from_grade, to_grade):
    conn = get_connection()
    cur = conn.execute(
        "UPDATE students SET grade = ? WHERE grade = ? AND status = 'Active'",
        (to_grade, from_grade),
    )
    conn.commit()
    return cur.rowcount


GRADE_CHAIN = [
    "Grade 7",
    "Grade 8",
    "Grade 9",
    "Grade 10",
    "Grade 11",
    "Grade 12",
]


def auto_promote_students():
    """Promote all active students to the next grade, up to Grade 12.

    Returns a dict mapping each source grade to the count of students promoted.
    """
    conn = get_connection()
    summary = {}
    for idx, grade in enumerate(GRADE_CHAIN[:-1]):
        next_grade = GRADE_CHAIN[idx + 1]
        cur = conn.execute(
            "UPDATE students SET grade = ? WHERE grade = ? AND status = 'Active'",
            (next_grade, grade),
        )
        count = cur.rowcount
        if count > 0:
            summary[grade] = count
    conn.commit()
    return summary


def list_defaulters(min_balance=0, grade=None, limit=None):
    conn = get_connection()
    query = (
        "SELECT s.*, "
        "COALESCE((SELECT SUM(amount) FROM charges WHERE student_id = s.id), 0) - "
        "COALESCE((SELECT SUM(amount) FROM waivers WHERE student_id = s.id AND revoked_at IS NULL), 0) - "
        "COALESCE((SELECT SUM(amount) FROM payments WHERE student_id = s.id AND voided = 0), 0) AS balance "
        "FROM students s "
        "WHERE s.status = 'Active' AND s.fee_waived = 0 "
        "GROUP BY s.id "
        "HAVING balance > ? "
    )
    params = [min_balance]
    if grade:
        query = query.replace("GROUP BY s.id", "AND s.grade = ? GROUP BY s.id")
        params.insert(0, grade)
    query += " ORDER BY balance DESC"
    if limit:
        query += " LIMIT ?"
        params.append(limit)
    return conn.execute(query, params).fetchall()


# ---------------------------------------------------------------------------
# Fee Waiver Management
# ---------------------------------------------------------------------------

def is_fee_waived(student_id):
    """Return True if the student has an active full fee waiver."""
    conn = get_connection()
    row = conn.execute(
        "SELECT fee_waived FROM students WHERE id = ?", (student_id,)
    ).fetchone()
    return bool(row and row["fee_waived"])


def set_fee_waiver(student_id, reason=None, granted_by=None):
    """Grant a full fee waiver to a student.

    Waived students have zero balances across all terms and are excluded
    from receivables, arrears, and collection-targets reports.
    """
    import datetime
    conn = get_connection()
    conn.execute(
        "UPDATE students SET fee_waived = 1, waiver_reason = ?, "
        "waiver_date = ? WHERE id = ?",
        (reason.strip() if reason else None,
         datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
         student_id),
    )
    conn.commit()
    return True


def remove_fee_waiver(student_id):
    """Revoke a fee waiver — the student's normal balances resume."""
    conn = get_connection()
    conn.execute(
        "UPDATE students SET fee_waived = 0, waiver_reason = NULL, "
        "waiver_date = NULL WHERE id = ?",
        (student_id,),
    )
    conn.commit()
    return True


def list_waived_students():
    """Return all students with an active full fee waiver, ordered by grade/name."""
    conn = get_connection()
    return conn.execute(
        "SELECT * FROM students WHERE fee_waived = 1 "
        "ORDER BY grade, full_name"
    ).fetchall()


def get_total_receivables(grade=None):
    """Total fees still to be collected across all *active* students,
    excluding any student with a full fee waiver.

    A waived student contributes 0 to this figure regardless of charges
    or payments recorded against their account.
    """
    students = list_students(grade=grade)
    total = 0.0
    for s in students:
        if s["fee_waived"]:
            continue
        if s["status"] != "Active":
            continue
        total += max(get_balance(s["id"]), 0.0)
    return round(total, 2)
