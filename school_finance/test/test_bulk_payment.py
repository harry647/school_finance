"""Unit tests for bulk payment model and receipt service."""
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
from models.payment import add_payment, add_charge, list_payments_for_student
from models.term import get_or_create_term, list_terms
from models.bulk_payment import (
    create_bulk_payment, get_bulk_payment, get_bulk_payment_items,
    list_bulk_payments, delete_bulk_payment, void_bulk_payment,
    next_bulk_receipt_no,
)
from services.receipt_service import generate_bulk_receipt


class TestBulkPaymentModel(unittest.TestCase):
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

    def test_next_bulk_receipt_no(self):
        no = next_bulk_receipt_no()
        self.assertTrue(no.startswith("BULK-"))
        self.assertEqual(len(no), 11)

    def test_create_bulk_payment_valid(self):
        student_id = add_student("Bulk Student", "Grade 7", admission_no="B001")
        term_id = get_or_create_term(2026, "Term I")
        items = [{"student_id": student_id, "amount": 1500.0}]
        result = create_bulk_payment(
            payer_name="Test NGO",
            method="Cash",
            term_id=term_id,
            items=items,
            payer_contact="0712000000",
            reference_no="REF123",
            notes="Test bulk",
            created_by="TestUser",
        )
        self.assertIn("bulk_payment_id", result)
        self.assertIn("receipt_no", result)
        self.assertIn("payment_ids", result)
        self.assertTrue(result["receipt_no"].startswith("BULK-"))
        self.assertEqual(len(result["payment_ids"]), 1)

        bp = get_bulk_payment(result["bulk_payment_id"])
        self.assertIsNotNone(bp)
        self.assertEqual(bp["payer_name"], "Test NGO")
        self.assertEqual(bp["method"], "Cash")
        self.assertEqual(bp["total_amount"], 1500.0)
        self.assertEqual(bp["receipt_no"], result["receipt_no"])

        items = get_bulk_payment_items(result["bulk_payment_id"])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["student_id"], student_id)
        self.assertEqual(items[0]["amount"], 1500.0)

    def test_create_bulk_payment_multiple_students(self):
        s1 = add_student("Student One", "Grade 7", admission_no="S1")
        s2 = add_student("Student Two", "Grade 8", admission_no="S2")
        term_id = get_or_create_term(2026, "Term II")
        items = [
            {"student_id": s1, "amount": 1000.0},
            {"student_id": s2, "amount": 2000.0},
        ]
        result = create_bulk_payment(
            payer_name="Multi Sponsor",
            method="M-Pesa",
            term_id=term_id,
            items=items,
            created_by="TestUser",
        )
        self.assertEqual(len(result["payment_ids"]), 2)

        bp = get_bulk_payment(result["bulk_payment_id"])
        self.assertEqual(bp["total_amount"], 3000.0)

        items = get_bulk_payment_items(result["bulk_payment_id"])
        self.assertEqual(len(items), 2)

    def test_create_bulk_payment_invalid_method_raises(self):
        student_id = add_student("Bad Method", "Grade 7")
        term_id = get_or_create_term(2026, "Term I")
        with self.assertRaises(ValueError):
            create_bulk_payment(
                payer_name="X",
                method="Bitcoin",
                term_id=term_id,
                items=[{"student_id": student_id, "amount": 100.0}],
            )

    def test_create_bulk_payment_empty_items_raises(self):
        term_id = get_or_create_term(2026, "Term I")
        with self.assertRaises(ValueError):
            create_bulk_payment(
                payer_name="X",
                method="Cash",
                term_id=term_id,
                items=[],
            )

    def test_list_bulk_payments(self):
        student_id = add_student("List Student", "Grade 7")
        term_id = get_or_create_term(2026, "Term I")
        result = create_bulk_payment(
            payer_name="List Org",
            method="Cash",
            term_id=term_id,
            items=[{"student_id": student_id, "amount": 500.0}],
        )
        payments = list_bulk_payments()
        found = [p for p in payments if p["payer_name"] == "List Org"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["payer_name"], "List Org")

    def test_list_bulk_payments_filter_by_term(self):
        s1 = add_student("Term1 Student", "Grade 7")
        s2 = add_student("Term2 Student", "Grade 8")
        t1 = get_or_create_term(2026, "Term I")
        t2 = get_or_create_term(2026, "Term II")
        result1 = create_bulk_payment(
            payer_name="Term1 Org", method="Cash", term_id=t1,
            items=[{"student_id": s1, "amount": 500.0}],
        )
        create_bulk_payment(
            payer_name="Term2 Org", method="Cash", term_id=t2,
            items=[{"student_id": s2, "amount": 700.0}],
        )
        t1_payments = list_bulk_payments(term_id=t1)
        t1_ids = [p["id"] for p in t1_payments]
        self.assertIn(result1["bulk_payment_id"], t1_ids)
        for p in t1_payments:
            self.assertEqual(p["term_id"], t1)

    def test_delete_bulk_payment(self):
        student_id = add_student("Delete Student", "Grade 7")
        term_id = get_or_create_term(2026, "Term I")
        result = create_bulk_payment(
            payer_name="Delete Org",
            method="Cash",
            term_id=term_id,
            items=[{"student_id": student_id, "amount": 500.0}],
        )
        bp_id = result["bulk_payment_id"]
        delete_bulk_payment(bp_id)
        self.assertIsNone(get_bulk_payment(bp_id))
        self.assertEqual(len(get_bulk_payment_items(bp_id)), 0)

    def test_void_bulk_payment(self):
        student_id = add_student("Void Student", "Grade 7")
        term_id = get_or_create_term(2026, "Term I")
        result = create_bulk_payment(
            payer_name="Void Org",
            method="Cash",
            term_id=term_id,
            items=[{"student_id": student_id, "amount": 500.0}],
        )
        bp_id = result["bulk_payment_id"]
        payment_id = result["payment_ids"][0]

        void_bulk_payment(bp_id, reason="Test void")

        bp = get_bulk_payment(bp_id)
        self.assertIn("VOIDED", bp["notes"])

        payments = list_payments_for_student(student_id, include_voided=True)
        self.assertEqual(len(payments), 1)
        self.assertEqual(payments[0]["voided"], 1)

    def test_bulk_payment_creates_individual_payments(self):
        student_id = add_student("Payment Student", "Grade 7")
        term_id = get_or_create_term(2026, "Term I")
        result = create_bulk_payment(
            payer_name="Payment Org",
            method="Cash",
            term_id=term_id,
            items=[{"student_id": student_id, "amount": 1000.0}],
        )
        payments = list_payments_for_student(student_id)
        self.assertEqual(len(payments), 1)
        self.assertEqual(payments[0]["amount"], 1000.0)
        self.assertEqual(payments[0]["method"], "Cash")


class TestBulkReceiptService(unittest.TestCase):
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

    def test_generate_bulk_receipt(self):
        from models.school import update_school_info
        update_school_info(
            "Test School", "123 Test Street", "555-0100",
            "info@test.school", "Knowledge is Power",
        )

        student_id = add_student("Receipt Student", "Grade 7", admission_no="R001")
        term_id = get_or_create_term(2026, "Term I")
        result = create_bulk_payment(
            payer_name="Receipt Org",
            method="Bank",
            term_id=term_id,
            items=[{"student_id": student_id, "amount": 2500.0}],
            reference_no="CHEQ999",
            created_by="TestUser",
        )
        bp = get_bulk_payment(result["bulk_payment_id"])
        items = get_bulk_payment_items(result["bulk_payment_id"])

        path = generate_bulk_receipt(result["bulk_payment_id"], bp, items)
        self.assertTrue(os.path.exists(path))
        self.assertTrue(path.endswith(".pdf"))
        self.assertGreater(os.path.getsize(path), 1000)
        self.assertIn("bulk_", os.path.basename(path))


if __name__ == "__main__":
    unittest.main()
