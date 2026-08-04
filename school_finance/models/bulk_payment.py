"""Bulk payment management for sponsor/NGO payments covering multiple students."""
import datetime

from db.database import get_connection
from models.payment import add_payment, VALID_METHODS
from models.term import get_term


def next_bulk_receipt_no():
    """Sequential bulk receipt numbers: BULK-000001, BULK-000002, ..."""
    conn = get_connection()
    row = conn.execute("SELECT COUNT(*) AS n FROM bulk_payments").fetchone()
    return f"BULK-{row['n'] + 1:06d}"


def create_bulk_payment(payer_name, method, term_id, items,
                         payer_contact=None, reference_no=None,
                         notes=None, date_paid=None, created_by=None):
    """Create a bulk payment covering multiple students.

    Args:
        payer_name:    Name of the organisation / sponsor / NGO.
        method:        Payment method (must be in VALID_METHODS).
        term_id:       Term this bulk payment applies to.
        items:         List of dicts with keys:
                       - student_id (required)
                       - amount (required)
                       - notes (optional)
        payer_contact: Optional contact info for the payer.
        reference_no:  Cheque / M-Pesa / bank reference number.
        notes:         General notes for the bulk payment.
        date_paid:     Payment date string (defaults to now).
        created_by:    Username of the user recording this.

    Returns:
        dict with keys: bulk_payment_id, receipt_no, payment_ids

    Raises:
        ValueError: if method is invalid or items list is empty.
    """
    if method not in VALID_METHODS:
        raise ValueError(f"method must be one of {VALID_METHODS}")
    if not items:
        raise ValueError("bulk payment must contain at least one item")

    date_paid = date_paid or datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    receipt_no = next_bulk_receipt_no()
    total_amount = sum(float(item["amount"]) for item in items)

    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO bulk_payments "
        "(payer_name, payer_contact, method, reference_no, term_id, "
        "total_amount, date_paid, notes, created_by) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            payer_name.strip(),
            payer_contact.strip() if payer_contact else None,
            method,
            reference_no.strip() if reference_no else None,
            term_id,
            total_amount,
            date_paid,
            notes.strip() if notes else None,
            created_by,
        ),
    )
    bulk_payment_id = cur.lastrowid

    payment_ids = []
    for item in items:
        student_id = item["student_id"]
        amount = float(item["amount"])
        item_notes = item.get("notes", "")

        payment_id, _ = add_payment(
            student_id=student_id,
            amount=amount,
            method=method,
            term_id=term_id,
            date_paid=date_paid,
            received_by=created_by,
        )
        payment_ids.append(payment_id)

        conn.execute(
            "INSERT INTO bulk_payment_items "
            "(bulk_payment_id, student_id, amount, payment_id, notes) "
            "VALUES (?, ?, ?, ?, ?)",
            (bulk_payment_id, student_id, amount, payment_id,
             item_notes.strip() if item_notes else None),
        )

    conn.commit()
    return {
        "bulk_payment_id": bulk_payment_id,
        "receipt_no": receipt_no,
        "payment_ids": payment_ids,
    }


def get_bulk_payment(bulk_payment_id):
    conn = get_connection()
    return conn.execute(
        "SELECT * FROM bulk_payments WHERE id = ?", (bulk_payment_id,)
    ).fetchone()


def get_bulk_payment_items(bulk_payment_id):
    conn = get_connection()
    return conn.execute(
        "SELECT bpi.*, s.full_name, s.grade, s.admission_no, bp.term_id "
        "FROM bulk_payment_items bpi "
        "JOIN students s ON bpi.student_id = s.id "
        "JOIN bulk_payments bp ON bp.id = bpi.bulk_payment_id "
        "WHERE bpi.bulk_payment_id = ? "
        "ORDER BY s.full_name",
        (bulk_payment_id,),
    ).fetchall()


def list_bulk_payments(term_id=None):
    conn = get_connection()
    query = ("SELECT bp.*, t.term_name, t.year FROM bulk_payments bp "
             "LEFT JOIN terms t ON bp.term_id = t.id ")
    params = []
    if term_id is not None:
        query += "WHERE bp.term_id = ? "
        params.append(term_id)
    query += "ORDER BY bp.date_paid DESC"
    return conn.execute(query, params).fetchall()


def void_bulk_payment(bulk_payment_id, reason=None):
    """Void a bulk payment and all its associated individual payments."""
    from models.payment import void_payment as _void_payment

    items = get_bulk_payment_items(bulk_payment_id)
    for item in items:
        if item["payment_id"]:
            try:
                _void_payment(item["payment_id"], reason or "Bulk payment voided")
            except ValueError:
                pass
    conn = get_connection()
    conn.execute(
        "UPDATE bulk_payments SET notes = COALESCE(notes, '') || ? WHERE id = ?",
        (f" [VOIDED: {reason or 'No reason'}]", bulk_payment_id),
    )
    conn.commit()


def delete_bulk_payment(bulk_payment_id):
    """Delete a bulk payment and its items."""
    conn = get_connection()
    conn.execute("DELETE FROM bulk_payment_items WHERE bulk_payment_id = ?",
                 (bulk_payment_id,))
    conn.execute("DELETE FROM bulk_payments WHERE id = ?", (bulk_payment_id,))
    conn.commit()
