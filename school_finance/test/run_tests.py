"""Unit tests for the School Finance System."""
import os
import sys
import tempfile
import shutil
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

from db.database import get_connection, close_connection, DB_PATH, DATA_DIR
from models.student import (add_student, update_student, delete_student,
                             get_student, list_students, get_balance,
                             list_students_with_balance)
from models.payment import (add_payment, list_payments_for_student,
                             list_recent_payments, next_receipt_no,
                             VALID_METHODS)
from models.term import get_or_create_term, list_terms
from models.user import (create_user, authenticate, any_users_exist,
                          log_action)
from utils.validation import (sanitize_text, validate_amount,
                               validate_column_name, validate_username,
                               validate_password, validate_grade)


class TestValidation(unittest.TestCase):
    def test_sanitize_text_normal(self):
        self.assertEqual(sanitize_text("Hello World"), "Hello World")

    def test_sanitize_text_none(self):
        self.assertIsNone(sanitize_text(None))

    def test_sanitize_text_truncation(self):
        long_str = "A" * 300
        result = sanitize_text(long_str, max_length=50)
        self.assertEqual(len(result), 50)

    def test_sanitize_text_strips_whitespace(self):
        self.assertEqual(sanitize_text("  hello  "), "hello")

    def test_validate_amount_valid(self):
        self.assertEqual(validate_amount("100.50"), 100.5)

    def test_validate_amount_zero_raises(self):
        with self.assertRaises(ValueError):
            validate_amount("0")

    def test_validate_amount_negative_raises(self):
        with self.assertRaises(ValueError):
            validate_amount("-10")

    def test_validate_amount_invalid_raises(self):
        with self.assertRaises(ValueError):
            validate_amount("not_a_number")

    def test_validate_column_name_valid(self):
        self.assertEqual(validate_column_name("full_name"), "full_name")

    def test_validate_column_name_invalid_raises(self):
        with self.assertRaises(ValueError):
            validate_column_name("evil_column; DROP TABLE students")

    def test_validate_username_valid(self):
        self.assertEqual(validate_username("admin"), "admin")

    def test_validate_username_empty_raises(self):
        with self.assertRaises(ValueError):
            validate_username("")

    def test_validate_username_special_chars_raises(self):
        with self.assertRaises(ValueError):
            validate_username("admin<script>")

    def test_validate_password_min_length(self):
        with self.assertRaises(ValueError):
            validate_password("short")

    def test_validate_password_valid(self):
        self.assertEqual(validate_password("validpassword"), "validpassword")

    def test_validate_grade_valid(self):
        self.assertEqual(validate_grade("Grade 7"), "Grade 7")

    def test_validate_grade_empty_raises(self):
        with self.assertRaises(ValueError):
            validate_grade("")


class TestDatabase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._orig_db = DB_PATH
        cls._tmp_dir = tempfile.mkdtemp()
        cls._tmp_db = os.path.join(cls._tmp_dir, "test.db")
        import db.database as db_mod
        db_mod.DB_PATH = cls._tmp_db
        db_mod.DATA_DIR = cls._tmp_dir
        db_mod._connection = None

    @classmethod
    def tearDownClass(cls):
        import db.database as db_mod
        close_connection()
        db_mod.DB_PATH = cls._orig_db
        db_mod.DATA_DIR = os.path.dirname(cls._orig_db)
        db_mod._connection = None
        shutil.rmtree(cls._tmp_dir, ignore_errors=True)

    def setUp(self):
        close_connection()
        import db.database as db_mod
        db_mod._connection = None

    def test_get_connection_creates_db(self):
        conn = get_connection()
        self.assertIsNotNone(conn)
        self.assertTrue(os.path.exists(self._tmp_db))

    def test_integrity_check_passes(self):
        conn = get_connection()
        result = conn.execute("PRAGMA integrity_check").fetchone()[0]
        self.assertEqual(result, "ok")

    def test_close_connection(self):
        conn = get_connection()
        self.assertIsNotNone(conn)
        close_connection()
        self.assertIsNone(
            __import__("db.database", fromlist=["_connection"])._connection)


class TestStudentCRUD(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._orig_db = DB_PATH
        cls._tmp_dir = tempfile.mkdtemp()
        cls._tmp_db = os.path.join(cls._tmp_dir, "test.db")
        import db.database as db_mod
        db_mod.DB_PATH = cls._tmp_db
        db_mod.DATA_DIR = cls._tmp_dir
        db_mod._connection = None

    @classmethod
    def tearDownClass(cls):
        import db.database as db_mod
        close_connection()
        db_mod.DB_PATH = cls._orig_db
        db_mod.DATA_DIR = os.path.dirname(cls._orig_db)
        db_mod._connection = None
        shutil.rmtree(cls._tmp_dir, ignore_errors=True)

    def setUp(self):
        close_connection()
        import db.database as db_mod
        db_mod._connection = None
        get_connection()

    def test_add_student(self):
        student_id = add_student("John Doe", "Grade 7",
                                  admission_no="A001")
        self.assertIsInstance(student_id, int)
        student = get_student(student_id)
        self.assertEqual(student["full_name"], "John Doe")

    def test_update_student(self):
        student_id = add_student("Jane Doe", "Grade 8")
        update_student(student_id, full_name="Jane Smith")
        student = get_student(student_id)
        self.assertEqual(student["full_name"], "Jane Smith")

    def test_update_student_invalid_column_raises(self):
        student_id = add_student("Test User", "Grade 9")
        with self.assertRaises(ValueError):
            update_student(student_id, evil_column="hacked")

    def test_delete_student(self):
        student_id = add_student("To Be Deleted", "Grade 10")
        delete_student(student_id)
        student = get_student(student_id)
        self.assertIsNone(student)

    def test_list_students(self):
        add_student("Alice", "Grade 7")
        add_student("Bob", "Grade 8")
        students = list_students()
        self.assertGreaterEqual(len(students), 2)

    def test_list_students_with_balance(self):
        student_id = add_student("Balance Student", "Grade 9")
        add_payment(student_id, 100.0, "Cash")
        students = list_students_with_balance()
        bal_student = next(
            (s for s in students if s["full_name"] == "Balance Student"),
            None)
        self.assertIsNotNone(bal_student)
        self.assertEqual(bal_student["balance"], 0.0)

    def test_get_balance(self):
        student_id = add_student("Balance Test", "Grade 10")
        add_payment(student_id, 50.0, "Cash")
        balance = get_balance(student_id)
        self.assertEqual(balance, 0.0)


class TestPaymentCRUD(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._orig_db = DB_PATH
        cls._tmp_dir = tempfile.mkdtemp()
        cls._tmp_db = os.path.join(cls._tmp_dir, "test.db")
        import db.database as db_mod
        db_mod.DB_PATH = cls._tmp_db
        db_mod.DATA_DIR = cls._tmp_dir
        db_mod._connection = None

    @classmethod
    def tearDownClass(cls):
        import db.database as db_mod
        close_connection()
        db_mod.DB_PATH = cls._orig_db
        db_mod.DATA_DIR = os.path.dirname(cls._orig_db)
        db_mod._connection = None
        shutil.rmtree(cls._tmp_dir, ignore_errors=True)

    def setUp(self):
        close_connection()
        import db.database as db_mod
        db_mod._connection = None
        get_connection()

    def test_add_payment_valid(self):
        student_id = add_student("Pay Student", "Grade 7")
        payment_id, receipt_no = add_payment(
            student_id, 200.0, "Cash", received_by="TestUser")
        self.assertIsInstance(payment_id, int)
        self.assertTrue(receipt_no.startswith("RCT-"))

    def test_add_payment_invalid_method_raises(self):
        student_id = add_student("Bad Method", "Grade 8")
        with self.assertRaises(ValueError):
            add_payment(student_id, 100.0, "Bitcoin")

    def test_add_payment_zero_amount_raises(self):
        student_id = add_student("Zero Amount", "Grade 9")
        with self.assertRaises(ValueError):
            add_payment(student_id, 0, "Cash")

    def test_add_payment_negative_amount_raises(self):
        student_id = add_student("Negative Amount", "Grade 10")
        with self.assertRaises(ValueError):
            add_payment(student_id, -50.0, "Cash")

    def test_list_payments_for_student(self):
        student_id = add_student("Payment List", "Grade 7")
        add_payment(student_id, 100.0, "Cash")
        add_payment(student_id, 50.0, "M-Pesa", mpesa_code="MP123")
        payments = list_payments_for_student(student_id)
        self.assertEqual(len(payments), 2)

    def test_list_recent_payments(self):
        add_student("Recent Student", "Grade 8")
        students = list_students()
        if students:
            add_payment(students[0]["id"], 75.0, "Cash")
            recent = list_recent_payments(limit=5)
            self.assertGreater(len(recent), 0)

    def test_next_receipt_no(self):
        no = next_receipt_no()
        self.assertTrue(no.startswith("RCT-"))


class TestTermCRUD(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._orig_db = DB_PATH
        cls._tmp_dir = tempfile.mkdtemp()
        cls._tmp_db = os.path.join(cls._tmp_dir, "test.db")
        import db.database as db_mod
        db_mod.DB_PATH = cls._tmp_db
        db_mod.DATA_DIR = cls._tmp_dir
        db_mod._connection = None

    @classmethod
    def tearDownClass(cls):
        import db.database as db_mod
        close_connection()
        db_mod.DB_PATH = cls._orig_db
        db_mod.DATA_DIR = os.path.dirname(cls._orig_db)
        db_mod._connection = None
        shutil.rmtree(cls._tmp_dir, ignore_errors=True)

    def setUp(self):
        close_connection()
        import db.database as db_mod
        db_mod._connection = None
        get_connection()

    def test_get_or_create_term(self):
        term_id = get_or_create_term(2026, "Term I")
        self.assertIsInstance(term_id, int)
        term_id2 = get_or_create_term(2026, "Term I")
        self.assertEqual(term_id, term_id2)

    def test_list_terms(self):
        get_or_create_term(2026, "Term I")
        terms = list_terms()
        self.assertGreater(len(terms), 0)


class TestUserAuth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._orig_db = DB_PATH
        cls._tmp_dir = tempfile.mkdtemp()
        cls._tmp_db = os.path.join(cls._tmp_dir, "test.db")
        import db.database as db_mod
        db_mod.DB_PATH = cls._tmp_db
        db_mod.DATA_DIR = cls._tmp_dir
        db_mod._connection = None

    @classmethod
    def tearDownClass(cls):
        import db.database as db_mod
        close_connection()
        db_mod.DB_PATH = cls._orig_db
        db_mod.DATA_DIR = os.path.dirname(cls._orig_db)
        db_mod._connection = None
        shutil.rmtree(cls._tmp_dir, ignore_errors=True)

    def setUp(self):
        close_connection()
        import db.database as db_mod
        db_mod._connection = None
        get_connection()

    def test_create_and_authenticate_user(self):
        create_user("testuser", "testpassword123", role="Clerk")
        user = authenticate("testuser", "testpassword123")
        self.assertIsNotNone(user)
        self.assertEqual(user["role"], "Clerk")

    def test_authenticate_wrong_password(self):
        create_user("wrongpassuser", "correctpass", role="Admin")
        user = authenticate("wrongpassuser", "wrongpass")
        self.assertIsNone(user)

    def test_any_users_exist(self):
        create_user("existcheck", "password123", role="Admin")
        self.assertTrue(any_users_exist())

    def test_log_action(self):
        create_user("loguser", "password123", role="Clerk")
        log_action("loguser", "test_action", "test detail")
        conn = get_connection()
        rows = conn.execute(
            "SELECT COUNT(*) AS n FROM audit_log WHERE username = ?",
            ("loguser",)).fetchone()
        self.assertGreater(rows["n"], 0)


if __name__ == "__main__":
    unittest.main()