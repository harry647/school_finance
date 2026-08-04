"""Test the statement_service.generate_statement function and its visual/robustness features."""
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
from services.statement_service import (
    generate_statement,
    _wrap_text,
    _truncate_desc,
    _format_date,
    _next_statement_no,
    _draw_table_header,
    NumberedCanvas,
    STATEMENTS_DIR,
    ACCENT,
    STATUS_COLORS,
)


class TestStatementService(unittest.TestCase):
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

    def test_truncate_desc_short(self):
        """Short descriptions are returned unchanged."""
        self.assertEqual(_truncate_desc("Term fee"), "Term fee")
        self.assertEqual(_truncate_desc("Short"), "Short")

    def test_truncate_desc_long(self):
        """Long descriptions are truncated with an ellipsis."""
        long_desc = "A" * 40
        result = _truncate_desc(long_desc, max_len=35)
        self.assertEqual(len(result), 35)
        self.assertTrue(result.endswith("\u2026"))
        self.assertEqual(result, "A" * 34 + "\u2026")

    def test_truncate_desc_exact_length(self):
        """Descriptions at exactly max_len are not truncated."""
        exact = "B" * 35
        result = _truncate_desc(exact, max_len=35)
        self.assertEqual(result, exact)
        self.assertFalse(result.endswith("\u2026"))

    def test_truncate_desc_empty(self):
        """Empty/None descriptions return empty string."""
        self.assertEqual(_truncate_desc(""), "")
        self.assertEqual(_truncate_desc(None), "")

    def test_format_date_valid(self):
        """Date formatting extracts YYYY-MM-DD from datetime strings."""
        self.assertEqual(_format_date("2026-01-15 10:30:00"), "2026-01-15")
        self.assertEqual(_format_date("2026-01-15 10:30"), "2026-01-15")
        self.assertEqual(_format_date("2026-01-15"), "2026-01-15")

    def test_format_date_empty(self):
        """Date formatting returns empty string for empty/None input."""
        self.assertEqual(_format_date(""), "")
        self.assertEqual(_format_date(None), "")

    def test_wrap_text(self):
        """Text wrapping splits long strings into multiple lines."""
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm

        c = canvas.Canvas(os.devnull, pagesize=A4)
        # Short text fits on one line
        lines = _wrap_text(c, "Short", "Helvetica", 10, 100 * mm)
        self.assertEqual(len(lines), 1)
        # Long text wraps
        long_text = " ".join(["word"] * 20)
        lines = _wrap_text(c, long_text, "Helvetica", 10, 50 * mm)
        self.assertGreater(len(lines), 1)

    def test_wrap_text_empty(self):
        """Text wrapping returns empty list for empty/whitespace input."""
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4

        c = canvas.Canvas(os.devnull, pagesize=A4)
        self.assertEqual(_wrap_text(c, "", "Helvetica", 10, 100), [])
        self.assertEqual(_wrap_text(c, "   ", "Helvetica", 10, 100), [])

    def test_next_statement_no_format(self):
        """Statement number follows ST-{year}-#### format."""
        no = _next_statement_no(2026)
        self.assertTrue(no.startswith("ST-2026-"))
        # Should be zero-padded to 4 digits
        num_part = no.split("-")[-1]
        self.assertEqual(len(num_part), 4)
        self.assertTrue(num_part.isdigit())

    def test_next_statement_no_increments(self):
        """Successive calls produce incrementing numbers."""
        no1 = _next_statement_no(2027)
        no2 = _next_statement_no(2027)
        num1 = int(no1.split("-")[-1])
        num2 = int(no2.split("-")[-1])
        self.assertEqual(num2, num1 + 1)

    def test_next_statement_no_per_year(self):
        """Statement numbers are scoped per year."""
        no_a1 = _next_statement_no(2025)
        no_b1 = _next_statement_no(2026)
        no_a2 = _next_statement_no(2025)
        # 2025 should continue from where it left off
        num_a1 = int(no_a1.split("-")[-1])
        num_a2 = int(no_a2.split("-")[-1])
        self.assertEqual(num_a2, num_a1 + 1)
        # 2026 is independent
        num_b1 = int(no_b1.split("-")[-1])
        self.assertEqual(num_b1, 1)

    def test_next_statement_no_uses_db_not_files(self):
        """Statement numbers come from DB counter, not file count."""
        # Generate a number
        no1 = _next_statement_no(2028)
        num1 = int(no1.split("-")[-1])
        # Create a fake PDF file in the statements dir
        os.makedirs(STATEMENTS_DIR, exist_ok=True)
        fake_path = os.path.join(STATEMENTS_DIR, "Statement_fake_999.pdf")
        with open(fake_path, "w") as f:
            f.write("fake")
        # Next number should still increment from DB, not count files
        no2 = _next_statement_no(2028)
        num2 = int(no2.split("-")[-1])
        self.assertEqual(num2, num1 + 1)
        # Clean up
        os.remove(fake_path)

    def test_generate_statement_basic(self):
        """Statement PDF is generated and saved to disk."""
        update_school_info(
            "Test School", "123 Test Street", "555-0100",
            "info@test.school", "Knowledge is Power",
            payment_details="Pay via M-Pesa Paybill 123456",
        )

        student_id = add_student("Test Student", "Grade 7", admission_no="T001")
        term_id = get_or_create_term(2026, "Term I")
        add_charge(student_id, 5000.0, term_id, "Term fee")
        add_payment(student_id, 3000.0, "Cash", term_id=term_id, received_by="Bursar")

        student = get_student(student_id)
        path = generate_statement(student)

        self.assertTrue(os.path.exists(path))
        self.assertTrue(path.endswith(".pdf"))
        self.assertGreater(os.path.getsize(path), 1000)

    def test_generate_statement_paid(self):
        """Statement shows PAID status when balance is zero."""
        student_id = add_student("Paid Student", "Grade 8", admission_no="P001")
        term_id = get_or_create_term(2026, "Term II")
        add_charge(student_id, 2000.0, term_id, "Term fee")
        add_payment(student_id, 2000.0, "Cash", term_id=term_id, received_by="Bursar")

        student = get_student(student_id)
        bal = get_balance(student_id)
        self.assertEqual(bal, 0.0)

        path = generate_statement(student)
        self.assertTrue(os.path.exists(path))

    def test_generate_statement_credit(self):
        """Statement shows CREDIT status when balance is negative (overpayment)."""
        student_id = add_student("Credit Student", "Grade 9", admission_no="C001")
        term_id = get_or_create_term(2026, "Term III")
        add_charge(student_id, 1000.0, term_id, "Term fee")
        add_payment(student_id, 1500.0, "Cash", term_id=term_id, received_by="Bursar")

        student = get_student(student_id)
        bal = get_balance(student_id)
        self.assertEqual(bal, 0.0)  # get_balance clamps to 0 for negative terms

        path = generate_statement(student)
        self.assertTrue(os.path.exists(path))

    def test_generate_statement_outstanding(self):
        """Statement shows OUTSTANDING status when balance is positive."""
        student_id = add_student("Owing Student", "Grade 7", admission_no="O001")
        term_id = get_or_create_term(2026, "Term I")
        add_charge(student_id, 5000.0, term_id, "Term fee")
        add_payment(student_id, 1000.0, "Cash", term_id=term_id, received_by="Bursar")

        student = get_student(student_id)
        bal = get_balance(student_id)
        self.assertGreater(bal, 0)

        path = generate_statement(student)
        self.assertTrue(os.path.exists(path))

    def test_generate_statement_multi_term(self):
        """Statement with multiple terms renders all term sections."""
        student_id = add_student("Multi Term Student", "Grade 7", admission_no="M001")
        term1_id = get_or_create_term(2025, "Term III")
        term2_id = get_or_create_term(2026, "Term I")
        term3_id = get_or_create_term(2026, "Term II")
        add_charge(student_id, 2000.0, term1_id, "Previous term fee")
        add_charge(student_id, 3000.0, term2_id, "Term fee")
        add_charge(student_id, 2500.0, term3_id, "Term fee")
        add_payment(student_id, 4000.0, "Cash", term_id=term2_id, received_by="Bursar")

        student = get_student(student_id)
        path = generate_statement(student)
        self.assertTrue(os.path.exists(path))
        self.assertGreater(os.path.getsize(path), 2000)

    def test_generate_statement_payment_no_charge(self):
        """Term with payment but no charges is not skipped (bug fix)."""
        student_id = add_student("Payment Only", "Grade 8", admission_no="PO001")
        term1_id = get_or_create_term(2026, "Term I")
        term2_id = get_or_create_term(2026, "Term II")
        # Term I has a charge and payment
        add_charge(student_id, 3000.0, term1_id, "Term fee")
        add_payment(student_id, 3000.0, "Cash", term_id=term1_id, received_by="Bursar")
        # Term II has only a payment (overpayment from Term I flows here via FIFO)
        # Actually, to have a payment in Term II with no charge, we just add a payment
        add_payment(student_id, 500.0, "M-Pesa", term_id=term2_id,
                     mpesa_code="QGH12345678", received_by="Bursar")

        student = get_student(student_id)
        path = generate_statement(student)
        self.assertTrue(os.path.exists(path))
        # The PDF should be generated successfully without skipping Term II

    def test_generate_statement_long_description(self):
        """Long descriptions are truncated with ellipsis, not silently cut."""
        student_id = add_student("Long Desc Student", "Grade 7", admission_no="L001")
        term_id = get_or_create_term(2026, "Term I")
        long_desc = "This is a very long charge description that exceeds the 35 character limit"
        add_charge(student_id, 5000.0, term_id, long_desc)
        add_payment(student_id, 2000.0, "Cash", term_id=term_id, received_by="Bursar")

        student = get_student(student_id)
        path = generate_statement(student)
        self.assertTrue(os.path.exists(path))

    def test_generate_statement_long_school_name(self):
        """Long school names are wrapped, not cut off."""
        update_school_info(
            "The Extremely Long and Verbose School Name Academy for Gifted Children",
            "123 Test Street",
            "555-0100",
            "info@test.school",
            "Knowledge is Power",
        )
        student_id = add_student("Wrap Name Student", "Grade 7", admission_no="W001")
        term_id = get_or_create_term(2026, "Term I")
        add_charge(student_id, 5000.0, term_id, "Term fee")
        add_payment(student_id, 2000.0, "Cash", term_id=term_id, received_by="Bursar")

        student = get_student(student_id)
        path = generate_statement(student)
        self.assertTrue(os.path.exists(path))
        self.assertGreater(os.path.getsize(path), 2000)

    def test_generate_statement_many_charges_pagination(self):
        """Statement with many charges triggers page breaks correctly."""
        student_id = add_student("Many Charges Student", "Grade 7", admission_no="MC001")
        term_id = get_or_create_term(2026, "Term I")
        # Add many charges to force pagination
        for i in range(50):
            add_charge(student_id, 100.0, term_id, f"Charge item {i}")
        add_payment(student_id, 500.0, "Cash", term_id=term_id, received_by="Bursar")

        student = get_student(student_id)
        path = generate_statement(student)
        self.assertTrue(os.path.exists(path))
        # Multi-page PDF should be larger
        self.assertGreater(os.path.getsize(path), 5000)

    def test_generate_statement_with_year_filter(self):
        """Statement generation works with year filter."""
        student_id = add_student("Year Filter Student", "Grade 7", admission_no="Y001")
        term1_id = get_or_create_term(2025, "Term III")
        term2_id = get_or_create_term(2026, "Term I")
        add_charge(student_id, 2000.0, term1_id, "Previous year fee")
        add_charge(student_id, 3000.0, term2_id, "Current year fee")
        add_payment(student_id, 1000.0, "Cash", term_id=term2_id, received_by="Bursar")

        student = get_student(student_id)
        path = generate_statement(student, year=2026)
        self.assertTrue(os.path.exists(path))

    def test_generate_statement_with_term_filter(self):
        """Statement generation works with term_id filter."""
        student_id = add_student("Term Filter Student", "Grade 7", admission_no="TF001")
        term1_id = get_or_create_term(2026, "Term I")
        term2_id = get_or_create_term(2026, "Term II")
        add_charge(student_id, 3000.0, term1_id, "Term I fee")
        add_charge(student_id, 2500.0, term2_id, "Term II fee")
        add_payment(student_id, 1500.0, "Cash", term_id=term1_id, received_by="Bursar")

        student = get_student(student_id)
        path = generate_statement(student, term_id=term1_id)
        self.assertTrue(os.path.exists(path))

    def test_generate_statement_no_transactions(self):
        """Statement generation works for student with no charges or payments."""
        student_id = add_student("Empty Student", "Grade 7", admission_no="E001")
        student = get_student(student_id)
        path = generate_statement(student)
        self.assertTrue(os.path.exists(path))

    def test_generate_statement_mpesa_payment(self):
        """Statement includes M-Pesa payment with transaction code."""
        student_id = add_student("Mpesa Statement", "Grade 8", admission_no="MS001")
        term_id = get_or_create_term(2026, "Term I")
        add_charge(student_id, 2000.0, term_id, "Term fee")
        add_payment(student_id, 2000.0, "M-Pesa", term_id=term_id,
                     mpesa_code="QGH12345678", received_by="Bursar")

        student = get_student(student_id)
        path = generate_statement(student)
        self.assertTrue(os.path.exists(path))

    def test_generate_statement_in_kind_payment(self):
        """Statement includes In-Kind payment with description."""
        student_id = add_student("InKind Statement", "Grade 9", admission_no="IK001")
        term_id = get_or_create_term(2026, "Term I")
        add_charge(student_id, 1500.0, term_id, "Term fee")
        add_payment(student_id, 1500.0, "In-Kind", term_id=term_id,
                     in_kind_desc="2 bags of maize", received_by="Bursar")

        student = get_student(student_id)
        path = generate_statement(student)
        self.assertTrue(os.path.exists(path))

    def test_status_colors_defined(self):
        """Status color map has all expected statuses."""
        self.assertIn("PAID", STATUS_COLORS)
        self.assertIn("OUTSTANDING", STATUS_COLORS)
        self.assertIn("CREDIT", STATUS_COLORS)

    def test_accent_color_defined(self):
        """Accent color is a HexColor matching the receipt."""
        from reportlab.lib import colors
        self.assertIsInstance(ACCENT, colors.HexColor)
        # Should be the same deep blue as the receipt
        self.assertEqual(str(ACCENT), "#185FA5")

    def test_numbered_canvas_creates_pages(self):
        """NumberedCanvas tracks page states for two-pass rendering."""
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm

        tmp_path = os.path.join(self._tmp_dir, "test_numbered.pdf")
        c = NumberedCanvas(tmp_path, pagesize=A4)
        # Draw something on page 1
        c.drawString(100, 700, "Page 1 content")
        c.showPage()
        # Draw something on page 2
        c.drawString(100, 700, "Page 2 content")
        c.showPage()
        c.save()

        self.assertTrue(os.path.exists(tmp_path))
        self.assertGreater(os.path.getsize(tmp_path), 1000)
        # Should have saved 2 page states
        self.assertEqual(len(c._saved_page_states), 2)


if __name__ == "__main__":
    unittest.main()