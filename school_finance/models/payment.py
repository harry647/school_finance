"""Payments (money received) and charges (money owed) CRUD."""
import datetime
from db.database import get_connection
from models.term import get_current_term

VALID_METHODS = ("Cash", "M-Pesa", "Bank", "In-Kind")


def amount_in_words(amount):
    """Convert a numeric amount to Kenyan Shillings in words.

    Examples:
        500.00    -> Kenya Shillings Five Hundred Only
        12550.50  -> Kenya Shillings Twelve Thousand Five Hundred Fifty and Fifty Cents Only
    """
    if amount is None:
        return "Zero Kenya Shillings Only"

    amount = round(float(amount), 2)
    if amount == 0:
        return "Zero Kenya Shillings Only"

    whole = int(amount)
    cents = int(round((amount - whole) * 100))

    ones = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
            "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
            "Seventeen", "Eighteen", "Nineteen"]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]

    def two_digit(n):
        if n < 20:
            return ones[n]
        return f"{tens[n // 10]} {ones[n % 10]}".strip()

    def three_digit(n):
        if n < 100:
            return two_digit(n)
        return f"{ones[n // 100]} Hundred {two_digit(n % 100)}".strip()

    parts = []
    remaining = whole
    if remaining >= 1000000:
        millions = remaining // 1000000
        parts.append(f"{three_digit(millions)} Million")
        remaining %= 1000000
    if remaining >= 1000:
        thousands = remaining // 1000
        parts.append(f"{three_digit(thousands)} Thousand")
        remaining %= 1000
    if remaining > 0:
        parts.append(three_digit(remaining))

    whole_words = " ".join(parts).strip()
    if not whole_words:
        whole_words = "Zero"

    if cents == 0:
        return f"Kenya Shillings {whole_words} Only"
    return f"Kenya Shillings {whole_words} and {two_digit(cents)} Cents Only"


def next_receipt_no():
    """Simple sequential receipt numbers: RCT-000001, RCT-000002, ..."""
    conn = get_connection()
    row = conn.execute("SELECT COUNT(*) AS n FROM payments").fetchone()
    return f"RCT-{row['n'] + 1:06d}"


def add_charge(student_id, amount, term_id=None, description="Term fee"):
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO charges (student_id, term_id, amount, description) "
        "VALUES (?, ?, ?, ?)",
        (student_id, term_id, amount, description),
    )
    conn.commit()
    return cur.lastrowid


def _allocate_payment_fifo(conn, payment_id, student_id, payment_amount):
    """Allocate a payment to the student's oldest unpaid charges first (FIFO).

    The *effective* unpaid amount on each charge is reduced by any active
    partial waivers (see models/waiver.py), so payments never over-allocate
    beyond the net amount the student actually owes.
    """
    waiver_totals = {}
    waiver_rows = conn.execute(
        "SELECT charge_id, COALESCE(SUM(amount), 0) AS total "
        "FROM waivers "
        "WHERE student_id = ? AND revoked_at IS NULL "
        "GROUP BY charge_id",
        (student_id,),
    ).fetchall()
    waiver_totals = {r["charge_id"]: r["total"] for r in waiver_rows}

    charges = conn.execute(
        "SELECT c.id, c.amount, c.term_id, t.year, t.term_name FROM charges c "
        "JOIN terms t ON c.term_id = t.id "
        "WHERE c.student_id = ? "
        "ORDER BY t.year ASC, "
        "CASE t.term_name WHEN 'Term I' THEN 1 WHEN 'Term II' THEN 2 WHEN 'Term III' THEN 3 END ASC, "
        "c.date_added ASC",
        (student_id,),
    ).fetchall()

    existing_allocations = conn.execute(
        "SELECT charge_id, SUM(amount) as allocated FROM payment_allocations "
        "WHERE payment_id IN (SELECT id FROM payments WHERE student_id = ? AND voided = 0) "
        "GROUP BY charge_id",
        (student_id,),
    ).fetchall()
    allocated_map = {r["charge_id"]: r["allocated"] for r in existing_allocations}

    remaining_payment = payment_amount
    for charge in charges:
        if remaining_payment <= 0:
            break
        waived = waiver_totals.get(charge["id"], 0.0)
        net_amount = charge["amount"] - waived
        already_paid = allocated_map.get(charge["id"], 0.0)
        unpaid = net_amount - already_paid
        if unpaid <= 0:
            continue
        allocation = min(remaining_payment, unpaid)
        conn.execute(
            "INSERT INTO payment_allocations (payment_id, charge_id, amount) VALUES (?, ?, ?)",
            (payment_id, charge["id"], allocation),
        )
        remaining_payment -= allocation
    return remaining_payment


def add_payment(student_id, amount, method, term_id=None, mpesa_code=None,
                 in_kind_desc=None, received_by=None, date_paid=None):
    if method not in VALID_METHODS:
        raise ValueError(f"method must be one of {VALID_METHODS}")
    if amount <= 0:
        raise ValueError("amount must be greater than zero")

    conn = get_connection()
    if term_id is None:
        current_term = get_current_term()
        term_id = current_term["id"] if current_term else None

    receipt_no = next_receipt_no()
    date_paid = date_paid or datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    cur = conn.execute(
        "INSERT INTO payments (student_id, term_id, amount, method, mpesa_code, "
        "in_kind_desc, date_paid, received_by, receipt_no) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (student_id, term_id, amount, method, mpesa_code, in_kind_desc,
         date_paid, received_by, receipt_no),
    )
    payment_id = cur.lastrowid
    remaining = _allocate_payment_fifo(conn, payment_id, student_id, amount)
    if remaining > 0.005:
        from models.student_credits import add_credit
        add_credit(student_id, round(remaining, 2), reason="Overpayment")
    conn.commit()
    return payment_id, receipt_no


def get_payment(payment_id):
    conn = get_connection()
    return conn.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone()


def void_payment(payment_id, reason):
    conn = get_connection()
    payment = conn.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone()
    if payment is None:
        raise ValueError("Payment not found")
    if payment["voided"]:
        raise ValueError("Payment is already voided")
    conn.execute(
        "DELETE FROM payment_allocations WHERE payment_id = ?",
        (payment_id,),
    )
    conn.execute(
        "UPDATE payments SET voided = 1, void_reason = ? WHERE id = ?",
        (reason.strip() if reason else "", payment_id),
    )
    conn.commit()


def edit_payment(payment_id, amount=None, method=None, mpesa_code=None,
                 in_kind_desc=None, received_by=None, date_paid=None):
    conn = get_connection()
    payment = conn.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone()
    if payment is None:
        raise ValueError("Payment not found")
    if payment["voided"]:
        raise ValueError("Cannot edit a voided payment")

    fields, values = [], []
    if amount is not None:
        if amount <= 0:
            raise ValueError("amount must be greater than zero")
        fields.append("amount = ?")
        values.append(amount)
    if method is not None:
        if method not in VALID_METHODS:
            raise ValueError(f"method must be one of {VALID_METHODS}")
        fields.append("method = ?")
        values.append(method)
    if mpesa_code is not None:
        fields.append("mpesa_code = ?")
        values.append(mpesa_code)
    if in_kind_desc is not None:
        fields.append("in_kind_desc = ?")
        values.append(in_kind_desc)
    if received_by is not None:
        fields.append("received_by = ?")
        values.append(received_by)
    if date_paid is not None:
        fields.append("date_paid = ?")
        values.append(date_paid)

    if not fields:
        return

    values.append(payment_id)
    conn.execute("UPDATE payments SET " + ", ".join(fields) + " WHERE id = ?", values)
    conn.execute("DELETE FROM payment_allocations WHERE payment_id = ?", (payment_id,))
    if amount is not None:
        new_amount = amount
    else:
        new_amount = payment["amount"]
    _allocate_payment_fifo(conn, payment_id, payment["student_id"], new_amount)
    conn.commit()


def list_payments_for_student(student_id, include_voided=False):
    query = ("SELECT p.*, t.term_name, t.year FROM payments p "
             "LEFT JOIN terms t ON p.term_id = t.id "
             "WHERE p.student_id = ?")
    params = [student_id]
    if not include_voided:
        query += " AND p.voided = 0"
    query += " ORDER BY p.date_paid"
    conn = get_connection()
    return conn.execute(query, params).fetchall()


def list_charges_for_student(student_id):
    """Return charges for a student with active-waiver totals joined in.

    Adds two computed columns:
      * waiver_total — sum of active (non-revoked) waivers on this charge
      * net_amount   — charge.amount - waiver_total
    """
    conn = get_connection()
    return conn.execute(
        "SELECT c.*, t.term_name, t.year, "
        "COALESCE(w.waiver_total, 0) AS waiver_total, "
        "(c.amount - COALESCE(w.waiver_total, 0)) AS net_amount "
        "FROM charges c "
        "LEFT JOIN terms t ON c.term_id = t.id "
        "LEFT JOIN ( "
        "    SELECT charge_id, SUM(amount) AS waiver_total "
        "    FROM waivers WHERE revoked_at IS NULL "
        "    GROUP BY charge_id "
        ") w ON w.charge_id = c.id "
        "WHERE c.student_id = ? "
        "ORDER BY c.date_added",
        (student_id,),
    ).fetchall()


def list_recent_payments(limit=50, student_id=None, term_id=None, method=None,
                         date_from=None, date_to=None):
    conn = get_connection()
    query = ("SELECT p.*, s.full_name, s.grade FROM payments p "
             "JOIN students s ON p.student_id = s.id "
             "WHERE p.voided = 0 ")
    params = []
    if student_id is not None:
        query += " AND p.student_id = ?"
        params.append(student_id)
    if term_id is not None:
        query += " AND p.term_id = ?"
        params.append(term_id)
    if method:
        query += " AND p.method = ?"
        params.append(method)
    if date_from:
        query += " AND p.date_paid >= ?"
        params.append(date_from)
    if date_to:
        query += " AND p.date_paid <= ?"
        params.append(date_to + " 23:59:59")
    query += " ORDER BY p.id DESC LIMIT ?"
    params.append(limit)
    return conn.execute(query, params).fetchall()


def get_payment_allocations(payment_id):
    conn = get_connection()
    return conn.execute(
        "SELECT pa.*, c.amount as charge_amount, c.description as charge_description, "
        "t.term_name, t.year FROM payment_allocations pa "
        "JOIN charges c ON pa.charge_id = c.id "
        "JOIN terms t ON c.term_id = t.id "
        "WHERE pa.payment_id = ?",
        (payment_id,),
    ).fetchall()
