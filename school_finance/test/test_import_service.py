"""Tests for the legacy balance-sheet importer (Excel + CSV + folder mode)."""
import os
import sys
import tempfile
import shutil
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

import openpyxl

import db.database as db_mod
from db.database import get_connection, close_connection
from services.import_service import (
    import_balance_sheet,
    import_csv_balance_sheet,
    import_balance_sheet_folder,
    _classify_columns,
    _normalize_grade,
    _to_amount,
)


def _make_xlsx(path, headers, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(headers)
    for r in rows:
        ws.append(r)
    wb.save(path)
    return path


class TestImportService(unittest.TestCase):
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
        # Fresh database per test so student/charge records don't leak over.
        if os.path.exists(db_mod.DB_PATH):
            os.remove(db_mod.DB_PATH)
        get_connection()

    def test_classify_grade7_style(self):
        headers = ["Admission No", "Grade", "Name", "Term 1 Balance 2026",
                   "Term 2 Balance 2026", "Term 3 Balance 2026", "Remarks"]
        cols = _classify_columns(headers, 2026)
        self.assertEqual(cols[0], ("admission", None, None))
        self.assertEqual(cols[1], ("grade", None, None))
        self.assertEqual(cols[2], ("name", None, None))
        self.assertEqual(cols[3], ("charge", "Term I", 2026))
        self.assertEqual(cols[4], ("charge", "Term II", 2026))
        self.assertEqual(cols[5], ("charge", "Term III", 2026))
        self.assertEqual(cols[6], ("remarks", None, None))

    def test_classify_grade8_style(self):
        headers = ["Admission No", "Grade ", "Name", "2025 Balance",
                   "Term I 2026", "Term II 2026", "Term III 2026", "Comment"]
        cols = _classify_columns(headers, 2026)
        self.assertEqual(cols[3], ("charge", "Opening Balance", 2025))
        self.assertEqual(cols[4], ("charge", "Term I", 2026))
        self.assertEqual(cols[7], ("remarks", None, None))

    def test_classify_skips_total_and_no(self):
        headers = ["No.", "S/No", "Name", "Total Balance"]
        cols = _classify_columns(headers, 2026)
        self.assertEqual(list(cols.keys()), [2])
        self.assertEqual(cols[2], ("name", None, None))

    def test_normalize_grade(self):
        self.assertEqual(_normalize_grade("Grade 7"), "Grade 7")
        self.assertEqual(_normalize_grade("Grade7"), "Grade 7")
        self.assertEqual(_normalize_grade("7"), "Grade 7")
        self.assertEqual(_normalize_grade(8), "Grade 8")
        self.assertEqual(_normalize_grade("Form 3"), "Grade 3")
        self.assertEqual(_normalize_grade(""), None)
        self.assertEqual(_normalize_grade("7 East"), "Grade 7")

    def test_to_amount(self):
        self.assertEqual(_to_amount(500), 500.0)
        self.assertEqual(_to_amount("KSh 5,000"), 5000.0)
        self.assertEqual(_to_amount("1,234.56"), 1234.56)
        self.assertEqual(_to_amount("none"), None)
        self.assertEqual(_to_amount(None), None)
        self.assertEqual(_to_amount(True), None)

    def test_import_all_columns(self):
        path = os.path.join(self._tmp_dir, "Grade7_import.xlsx")
        _make_xlsx(
            path,
            ["Admission No", "Grade", "Name", "Term I 2026", "Remarks"],
            [
                [101, "Grade 7", "Ada Lovelace", 1500, "Needs books"],
                [102, "Grade 7", "Grace Hopper", 0, ""],
                [103, "Grade 7", "Alan Turing", 2500.5, "Sponsor"],
            ],
        )
        result = import_balance_sheet(path)
        self.assertEqual(result["students_added"], 3)
        self.assertEqual(result["charges_added"], 2)
        self.assertEqual(result["grade"], "Grade 7")

        conn = get_connection()
        stu = conn.execute(
            "SELECT * FROM students WHERE admission_no = 101"
        ).fetchone()
        self.assertEqual(stu["full_name"], "Ada Lovelace")
        self.assertEqual(stu["grade"], "Grade 7")
        self.assertEqual(stu["remarks"], "Needs books")

        charges = conn.execute(
            "SELECT SUM(amount) total FROM charges c "
            "JOIN students s ON c.student_id = s.id "
            "WHERE s.admission_no = 103"
        ).fetchone()
        self.assertEqual(charges["total"], 2500.5)

    def test_reimport_no_duplicates(self):
        path = os.path.join(self._tmp_dir, "G8.xlsx")
        _make_xlsx(
            path,
            ["Name", "Term I 2026", "Term II 2026"],
            [["Ada Lovelace", 3000, 1500]],
        )
        r1 = import_balance_sheet(path)
        self.assertEqual(r1["students_added"], 1)
        self.assertEqual(r1["charges_added"], 2)
        r2 = import_balance_sheet(path)
        self.assertEqual(r2["students_added"], 0)
        self.assertEqual(r2["students_skipped"], 1)
        self.assertEqual(r2["charges_added"], 0)
        self.assertEqual(r2["duplicate_charges_skipped"], 2)

        conn = get_connection()
        n = conn.execute("SELECT COUNT(*) c FROM charges").fetchone()["c"]
        self.assertEqual(n, 2)

    def test_admission_backfill(self):
        from models.student import add_student
        add_student("Ada Lovelace", "Grade 7", admission_no=None)

        path = os.path.join(self._tmp_dir, "Grade7_backfill.xlsx")
        _make_xlsx(
            path,
            ["Name", "Admission No", "Term I 2026"],
            [["Ada Lovelace", 999, 1200]],
        )
        result = import_balance_sheet(path)
        self.assertEqual(result["students_added"], 0)
        self.assertEqual(result["admission_linked"], 1)
        self.assertEqual(result["charges_added"], 1)

        conn = get_connection()
        row = conn.execute(
            "SELECT admission_no FROM students WHERE full_name = 'Ada Lovelace'"
        ).fetchone()
        self.assertEqual(row["admission_no"], "999")

    def test_csv_import(self):
        csv_path = os.path.join(self._tmp_dir, "Grade9.csv")
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            f.write("Admission No,Grade,Name,Term I 2026,Comment\n")
            f.write("901,Grade 9,Ada Lovelace,2000,CSV remark\n")
        result = import_csv_balance_sheet(csv_path)
        self.assertEqual(result["students_added"], 1)
        self.assertEqual(result["charges_added"], 1)
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM students WHERE admission_no = 901"
        ).fetchone()
        self.assertEqual(row["remarks"], "CSV remark")
        self.assertEqual(row["grade"], "Grade 9")

    def test_folder_import(self):
        folder = os.path.join(self._tmp_dir, "sheets")
        os.makedirs(folder, exist_ok=True)
        _make_xlsx(
            os.path.join(folder, "Grade7_Balance.xlsx"),
            ["Name", "Term I 2026"],
            [["Ada Lovelace", 1000], ["Grace Hopper", 2000]],
        )
        _make_xlsx(
            os.path.join(folder, "Grade8_Balance.xlsx"),
            ["Name", "Term I 2026"],
            [["Alan Turing", 3000]],
        )
        result = import_balance_sheet_folder(folder)
        self.assertEqual(result["files_processed"], 2)
        self.assertEqual(result["students_added"], 3)
        self.assertEqual(result["charges_added"], 3)
        self.assertEqual(len(result["files"]), 2)


if __name__ == "__main__":
    unittest.main()

