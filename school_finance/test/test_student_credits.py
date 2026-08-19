"""Test student_credits model functions."""
import os
import sys
import tempfile
import shutil
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

import db.database as db_mod
from db.database import get_connection, close_connection
from models.student import add_student, get_student
from models.payment import add_payment, add_charge
from models.student_credits import (
    add_credit,
    get_available_credit,
    get_credits_for_student,
    reimburse_credit,
    list_reimbursable_credits,
    get_student_credit_summary,
)
from models.term import get_or_create_term


class TestStudentCredits(unittest.TestCase):
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

    def test_add_credit(self):
        """Adding a credit creates a record with the correct amount."""
        student_id = add_student("Credit Test", "Grade 7", admission_no="CT001")
        credit_id = add_credit(student_id, 500.0, reason="Overpayment")
        self.assertIsNotNone(credit_id)
        credits = get_credits_for_student(student_id)
        self.assertEqual(len(credits), 1)
        self.assertEqual(credits[0]["amount"], 500.0)
        self.assertEqual(credits[0]["remaining"], 500.0)
        self.assertEqual(credits[0]["reimbursed"], 0)

    def test_get_available_credit(self):
        """Available credit sums remaining amounts for active credits."""
        student_id = add_student("Avail Credit", "Grade 7", admission_no="AC001")
        add_credit(student_id, 300.0)
        add_credit(student_id, 200.0)
        self.assertEqual(get_available_credit(student_id), 500.0)

    def test_reimburse_credit(self):
        """Reimbursing a credit marks it as reimbursed with zero remaining."""
        student_id = add_student("Reimburse Test", "Grade 9", admission_no="RT001")
        credit_id = add_credit(student_id, 400.0)
        reimburse_credit(credit_id, reimbursed_by="Bursar")
        credits = get_credits_for_student(student_id, include_reimbursed=True)
        self.assertEqual(len(credits), 1)
        self.assertEqual(credits[0]["reimbursed"], 1)
        self.assertEqual(credits[0]["remaining"], 0.0)
        self.assertEqual(get_available_credit(student_id), 0.0)

    def test_overpayment_creates_credit(self):
        """Paying more than the balance creates a credit for the excess."""
        student_id = add_student("Overpay", "Grade 7", admission_no="OP001")
        term_id = get_or_create_term(2026, "Term I")
        add_charge(student_id, 3000.0, term_id, "Term fee")
        add_payment(student_id, 3500.0, "Cash", term_id=term_id, received_by="Bursar")
        self.assertEqual(get_available_credit(student_id), 500.0)

    def test_credit_reduces_future_balance(self):
        """An overpayment credit reduces the balance on future charges."""
        student_id = add_student("Future Credit", "Grade 7", admission_no="FC001")
        term1 = get_or_create_term(2026, "Term I")
        term2 = get_or_create_term(2026, "Term II")
        add_charge(student_id, 3000.0, term1, "Term I fee")
        add_payment(student_id, 5500.0, "Cash", term_id=term1, received_by="Bursar")
        add_charge(student_id, 2000.0, term2, "Term II fee")
        from models.student import get_balance
        self.assertEqual(get_balance(student_id), 0.0)

    def test_credit_carries_across_grades(self):
        """Credits persist across grade promotions."""
        student_id = add_student("Grade Carry", "Grade 7", admission_no="GC001")
        term1 = get_or_create_term(2026, "Term I")
        add_charge(student_id, 3000.0, term1, "Term fee")
        add_payment(student_id, 3500.0, "Cash", term_id=term1, received_by="Bursar")
        self.assertEqual(get_available_credit(student_id), 500.0)
        from models.student import promote_students
        promote_students("Grade 7", "Grade 8")
        student = get_student(student_id)
        self.assertEqual(student["grade"], "Grade 8")
        self.assertEqual(get_available_credit(student_id), 500.0)

    def test_reimbursable_credits_grade_9(self):
        """Credits for Grade 9 students appear in reimbursable list."""
        student_id = add_student("G9 Reimb", "Grade 9", admission_no="G9R001")
        add_credit(student_id, 600.0)
        reimbursable = list_reimbursable_credits(grade="Grade 9")
        self.assertEqual(len(reimbursable), 1)
        self.assertEqual(reimbursable[0]["student_id"], student_id)

    def test_credit_summary(self):
        """Credit summary returns correct totals."""
        student_id = add_student("Summary", "Grade 7", admission_no="SUM001")
        add_credit(student_id, 1000.0)
        add_credit(student_id, 500.0)
        summary = get_student_credit_summary(student_id)
        self.assertEqual(summary["total_credited"], 1500.0)
        self.assertEqual(summary["total_remaining"], 1500.0)
        self.assertEqual(summary["total_reimbursed"], 0.0)
        self.assertEqual(summary["active_count"], 2)


if __name__ == "__main__":
    unittest.main()
