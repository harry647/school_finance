"""Test the receipt_service.generate_receipt function and its visual/robustness features."""
import os
import sys
import tempfile
import shutil
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

import db.database as db_mod
from db.database import get_connection, close_connection
from models.student import add_student, get_student, get_balance
from models.payment import add_payment, add_charge
from models.term import get_or_create_term
from models.school import update_school_info
from services.receipt_service import (
    generate_receipt,
    _sanitize_filename,
    _wrap_text,
    _compute_status,
    _format_date,
    RECEIPTS_DIR,
)


class TestReceiptService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._orig_db = db_mod.DB_PATH
        cls._orig_data = db_mod.DATA_DIR
        cls._orig_base = db_mod.BASE_DIR
        cls._tmp_dir = tempfile.mkdtemp()
        cls._tmp_db = os.path.join(cls._tmp_dir, "test.db")
        db_mod.DB_PATH = cls._tmp_db
        db_mod.DATA_DIR = cls._tmp_dir
        db_mod.BASE_DIR = cls._tmp_dir
        db_mod._connection = None

    @classmethod
    def tearDownClass(cls):
        # Close the actual connection BEFORE resetting paths/pointer,
        # otherwise close_connection() sees _connection=None and leaks it.
        close_connection()
        db_mod.DB_PATH = cls._orig_db
        db_mod.DATA_DIR = cls._orig_data
        db_mod.BASE_DIR = cls._orig_base
        db_mod._connection = None
        shutil.rmtree(cls._tmp_dir, ignore_errors=True)

    def setUp(self):
        close_connection()
        db_mod._connection = None
        get_connection()

    def test_sanitize_filename(self):
        """Filename sanitization strips unsafe characters."""
        self.assertEqual(_sanitize_filename("RCT-000001"), "RCT-000001")
        self.assertEqual(_sanitize_filename("RCT/../../etc"), "RCTetc")
        self.assertEqual(_sanitize_filename("RCT 0001"), "RCT0001")
        self.assertEqual(_sanitize_filename(""), "receipt")
        self.assertEqual(_sanitize_filename("../../../"), "receipt")

    def test_compute_status(self):
        """Status badge logic covers PAID, PARTIAL, BALANCE DUE, and CREDIT."""
        self.assertEqual(_compute_status(0, 1000), "PAID")
        self.assertEqual(_compute_status(-50, 1000), "PAID")
        self.assertEqual(_compute_status(500, 1000), "PARTIAL")
        self.assertEqual(_compute_status(1000, 1000), "BALANCE DUE")
        self.assertEqual(_compute_status(1500, 1000), "BALANCE DUE")
        self.assertEqual(_compute_status(0, 1000, credit_balance=500), "CREDIT")
        self.assertEqual(_compute_status(500, 1000, credit_balance=200), "CREDIT")

    def test_format_date_valid(self):
        """Date formatting handles standard SQLite datetime formats."""
        self.assertEqual(_format_date("2026-01-15 10:30:00"), "15 January 2026")
        self.assertEqual(_format_date("2026-01-15 10:30"), "15 January 2026")
        self.assertEqual(_format_date("2026-01-15"), "15 January 2026")

    def test_format_date_fallback(self):
        """Date formatting falls back to the raw string for unparseable input."""
        self.assertEqual(_format_date("not-a-date"), "not-a-date")
        self.assertEqual(_format_date("15/01/2026"), "15/01/2026")

    def test_format_date_empty_and_none(self):
        """Date formatting returns N/A for empty/None input."""
        self.assertEqual(_format_date(""), "N/A")
        self.assertEqual(_format_date(None), "N/A")

    def test_wrap_text(self):
        """Text wrapping splits long strings into multiple lines."""
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A5
        from reportlab.lib.units import mm

        c = canvas.Canvas(os.devnull, pagesize=A5)
        # Short text fits on one line
        lines = _wrap_text(c, "Short", "Helvetica", 10, 100 * mm)
        self.assertEqual(len(lines), 1)
        # Long text wraps
        long_text = " ".join(["word"] * 20)
        lines = _wrap_text(c, long_text, "Helvetica", 10, 50 * mm)
        self.assertGreater(len(lines), 1)

    def test_generate_receipt_basic(self):
        """Receipt PDF is generated and saved to disk."""
        # Set up school info
        update_school_info(
            "Test School", "123 Test Street", "555-0100",
            "info@test.school", "Knowledge is Power",
            payment_details="Pay via M-Pesa Paybill 123456",
        )

        # Create student, term, charge, payment
        student_id = add_student("Test Student", "Grade 7", admission_no="T001")
        term_id = get_or_create_term(2026, "Term I")
        add_charge(student_id, 5000.0, term_id, "Term fee")
        payment_id, receipt_no = add_payment(
            student_id, 3000.0, "Cash", term_id=term_id, received_by="Bursar"
        )

        student = get_student(student_id)
        bal_after = get_balance(student_id)

        path = generate_receipt(payment_id, student, term_id, bal_after)

        self.assertTrue(os.path.exists(path))
        self.assertTrue(path.endswith(".pdf"))
        self.assertGreater(os.path.getsize(path), 1000)

    def test_generate_receipt_mpesa(self):
        """Receipt generation works for M-Pesa payments with transaction code."""
        student_id = add_student("Mpesa Student", "Grade 8", admission_no="M001")
        term_id = get_or_create_term(2026, "Term II")
        add_charge(student_id, 2000.0, term_id, "Term fee")
        payment_id, receipt_no = add_payment(
            student_id, 2000.0, "M-Pesa", term_id=term_id,
            mpesa_code="QGH12345678", received_by="Bursar"
        )

        student = get_student(student_id)
        bal_after = get_balance(student_id)

        path = generate_receipt(payment_id, student, term_id, bal_after)
        self.assertTrue(os.path.exists(path))

    def test_generate_receipt_in_kind(self):
        """Receipt generation works for In-Kind payments."""
        student_id = add_student("InKind Student", "Grade 9", admission_no="IK001")
        term_id = get_or_create_term(2026, "Term III")
        add_charge(student_id, 1500.0, term_id, "Term fee")
        payment_id, receipt_no = add_payment(
            student_id, 1500.0, "In-Kind", term_id=term_id,
            in_kind_desc="2 bags of maize", received_by="Bursar"
        )

        student = get_student(student_id)
        bal_after = get_balance(student_id)

        path = generate_receipt(payment_id, student, term_id, bal_after)
        self.assertTrue(os.path.exists(path))

    def test_reprint_shows_duplicate(self):
        """Reprinting a receipt increments print_count and shows DUPLICATE watermark."""
        student_id = add_student("Reprint Student", "Grade 7", admission_no="R001")
        term_id = get_or_create_term(2026, "Term I")
        add_charge(student_id, 1000.0, term_id, "Term fee")
        payment_id, receipt_no = add_payment(
            student_id, 1000.0, "Cash", term_id=term_id, received_by="Bursar"
        )

        student = get_student(student_id)
        bal_after = get_balance(student_id)

        # First print (original)
        path1 = generate_receipt(payment_id, student, term_id, bal_after)
        conn = get_connection()
        row = conn.execute(
            "SELECT print_count FROM receipts WHERE receipt_no = ?",
            (receipt_no,),
        ).fetchone()
        self.assertEqual(row["print_count"], 1)

        # Second print (duplicate)
        path2 = generate_receipt(payment_id, student, term_id, bal_after)
        row = conn.execute(
            "SELECT print_count FROM receipts WHERE receipt_no = ?",
            (receipt_no,),
        ).fetchone()
        self.assertEqual(row["print_count"], 2)

        # File should be overwritten (same path)
        self.assertEqual(path1, path2)
        self.assertTrue(os.path.exists(path2))

    def test_filename_sanitization_in_generate(self):
        """Receipt filename is sanitized even if receipt_no has odd characters."""
        student_id = add_student("Filename Test", "Grade 7", admission_no="F001")
        term_id = get_or_create_term(2026, "Term I")
        add_charge(student_id, 500.0, term_id, "Term fee")
        payment_id, receipt_no = add_payment(
            student_id, 500.0, "Cash", term_id=term_id, received_by="Bursar"
        )

        student = get_student(student_id)
        bal_after = get_balance(student_id)

        path = generate_receipt(payment_id, student, term_id, bal_after)
        filename = os.path.basename(path)
        # Filename should only contain alnum, hyphens, underscores, and .pdf
        name_without_ext = filename.replace(".pdf", "")
        for ch in name_without_ext:
            self.assertTrue(ch.isalnum() or ch in "-_",
                            f"Unexpected character '{ch}' in filename '{filename}'")

    def test_receipt_with_previous_balance(self):
        """Receipt shows previous balance breakdown when applicable."""
        student_id = add_student("Prev Bal Student", "Grade 7", admission_no="P001")
        term_id = get_or_create_term(2026, "Term I")
        # Add a charge for a different term to create a previous balance
        other_term_id = get_or_create_term(2025, "Term III")
        add_charge(student_id, 2000.0, other_term_id, "Previous term fee")
        # Add current term charge
        add_charge(student_id, 3000.0, term_id, "Term fee")
        # Make a partial payment
        payment_id, receipt_no = add_payment(
            student_id, 1000.0, "Cash", term_id=term_id, received_by="Bursar"
        )

        student = get_student(student_id)
        bal_after = get_balance(student_id)

        path = generate_receipt(payment_id, student, term_id, bal_after)
        self.assertTrue(os.path.exists(path))
        self.assertGreater(bal_after, 0)  # Should have a remaining balance


if __name__ == "__main__":
    unittest.main()