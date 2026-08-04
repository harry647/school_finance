"""
One-off importer for the school's existing Excel balance sheets
(the Grade 7 / Grade 8 / Grade 9 style workbooks) and CSV files.

These sheets only ever recorded the *outstanding balance* per term, not a
full payment history. So each non-zero balance column found is imported as
a `charge` (money owed) for that student/term. From then on, real payments
recorded in the app reduce that balance normally.

Supported column header patterns (case-insensitive, matched by keyword):
  - "Name"                       -> student name (required)
  - "No."                        -> ignored (just a row counter)
  - "Balance 2025" / "2025 Balance"          -> opening balance, year 2025
  - "Term I 2026" / "Term 1 Balance" etc.    -> that term's balance
  - "Total ..." / "Total Balance" etc.       -> ignored (recomputed by the app)
  - "Remarks" / "Comment"        -> copied into the student's remarks field
"""
import csv
import re
import os
import openpyxl

from models.student import add_student, list_students
from models.payment import add_charge
from models.term import get_or_create_term

TERM_WORD_MAP = {"1": "Term I", "i": "Term I",
                   "2": "Term II", "ii": "Term II",
                   "3": "Term III", "iii": "Term III"}


def _guess_grade_from_filename(file_path):
    base = os.path.basename(file_path)
    match = re.search(r"grade\s*[_\- ]?(\d+)", base, re.IGNORECASE)
    if match:
        return f"Grade {match.group(1)}"
    return None


def _find_header_row(sheet, max_scan=10):
    for row_idx in range(1, min(max_scan, sheet.max_row) + 1):
        values = [str(c.value).strip().lower() if c.value else ""
                  for c in sheet[row_idx]]
        if any(v == "name" for v in values):
            return row_idx, values
    raise ValueError("Could not find a header row containing a 'Name' column")


def _classify_columns(header_values, default_year):
    """Return dict: col_index(0-based) -> ('name'|'remarks'|'charge', term_name, year)"""
    mapping = {}
    for idx, raw in enumerate(header_values):
        text = raw.strip().lower()
        if not text:
            continue
        if text == "name":
            mapping[idx] = ("name", None, None)
            continue
        if text in ("remarks", "comment", "comments"):
            mapping[idx] = ("remarks", None, None)
            continue
        if text.startswith("total") or text.startswith("no"):
            continue  # skip totals & row-number columns

        year_match = re.search(r"(20\d{2})", text)
        year = int(year_match.group(1)) if year_match else default_year

        term_match = re.search(r"term\s*([1-3]|i{1,3})\b", text)
        if term_match:
            term_name = TERM_WORD_MAP[term_match.group(1).lower()]
            mapping[idx] = ("charge", term_name, year)
        elif "balance" in text:
            # e.g. "Balance 2025" / "2025 Balance" with no explicit term
            # -> treat as an opening balance, not tied to a specific term
            mapping[idx] = ("charge", "Opening Balance", year)
    return mapping


def _find_header_row_csv(reader):
    for row in reader:
        if any(v.strip().lower() == "name" for v in row if v):
            return row
    raise ValueError("Could not find a 'Name' column in this CSV file")


def _classify_columns_csv(header_values, default_year):
    mapping = {}
    for idx, raw in enumerate(header_values):
        text = raw.strip().lower()
        if not text:
            continue
        if text == "name":
            mapping[idx] = ("name", None, None)
            continue
        if text in ("remarks", "comment", "comments"):
            mapping[idx] = ("remarks", None, None)
            continue
        if text.startswith("total") or text.startswith("no"):
            continue

        year_match = re.search(r"(20\d{2})", text)
        year = int(year_match.group(1)) if year_match else default_year

        term_match = re.search(r"term\s*([1-3]|i{1,3})\b", text)
        if term_match:
            term_name = TERM_WORD_MAP[term_match.group(1).lower()]
            mapping[idx] = ("charge", term_name, year)
        elif "balance" in text:
            mapping[idx] = ("charge", "Opening Balance", year)
    return mapping


def import_csv_balance_sheet(file_path, default_grade=None, default_year=2026):
    grade = default_grade or _guess_grade_from_filename(file_path) \
        or "Unknown Grade"

    with open(file_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header_values = _find_header_row_csv(reader)
        columns = _classify_columns_csv(header_values, default_year)

        name_col = next((i for i, v in columns.items() if v[0] == "name"), None)
        if name_col is None:
            raise ValueError("No 'Name' column found in this CSV")
        remarks_col = next((i for i, v in columns.items() if v[0] == "remarks"), None)

        existing_names = {s["full_name"].strip().lower()
                          for s in list_students(grade=grade)}

        students_added = 0
        students_skipped = 0
        charges_added = 0

        for row in reader:
            if name_col >= len(row):
                continue
            name = row[name_col]
            if not name or not str(name).strip():
                continue
            name = str(name).strip()

            if name.strip().lower() in existing_names:
                students_skipped += 1
                student_id = next(
                    s["id"] for s in list_students(grade=grade)
                    if s["full_name"].strip().lower() == name.strip().lower()
                )
            else:
                remarks = None
                if remarks_col is not None and remarks_col < len(row):
                    remarks = str(row[remarks_col]).strip() if row[remarks_col] else None
                student_id = add_student(full_name=name, grade=grade, stream=None, remarks=remarks)
                existing_names.add(name.strip().lower())
                students_added += 1

            for idx, (kind, term_name, year) in columns.items():
                if kind != "charge" or idx >= len(row):
                    continue
                amount = row[idx]
                try:
                    amount = float(amount)
                except (ValueError, TypeError):
                    continue
                if amount <= 0:
                    continue
                term_id = get_or_create_term(year, term_name)
                add_charge(
                    student_id, amount, term_id=term_id,
                    description=f"Imported balance - {term_name} {year}",
                )
                charges_added += 1

    return {
        "grade": grade,
        "students_added": students_added,
        "students_skipped": students_skipped,
        "charges_added": charges_added,
    }


def import_balance_sheet(file_path, default_grade=None, default_year=2026):
    """
    Import one legacy balance-sheet workbook.
    Returns a summary dict: {students_added, students_skipped, charges_added, grade}
    """
    grade = default_grade or _guess_grade_from_filename(file_path) or "Unknown Grade"
    wb = openpyxl.load_workbook(file_path, data_only=True)
    sheet = wb.worksheets[0]

    header_row, header_values = _find_header_row(sheet)
    columns = _classify_columns(header_values, default_year)

    name_col = next((i for i, v in columns.items() if v[0] == "name"), None)
    if name_col is None:
        raise ValueError("No 'Name' column found in this sheet")
    remarks_col = next((i for i, v in columns.items() if v[0] == "remarks"), None)

    existing_names = {s["full_name"].strip().lower() for s in list_students(grade=grade)}

    students_added = 0
    students_skipped = 0
    charges_added = 0

    for row in sheet.iter_rows(min_row=header_row + 1, max_row=sheet.max_row):
        values = [c.value for c in row]
        if name_col >= len(values):
            continue
        name = values[name_col]
        if not name or not str(name).strip():
            continue
        name = str(name).strip()

        if name.strip().lower() in existing_names:
            students_skipped += 1
            student_id = next(
                s["id"] for s in list_students(grade=grade)
                if s["full_name"].strip().lower() == name.strip().lower()
            )
        else:
            remarks = None
            if remarks_col is not None and remarks_col < len(values):
                remarks = str(values[remarks_col]).strip() if values[remarks_col] else None
            student_id = add_student(full_name=name, grade=grade, stream=None, remarks=remarks)
            existing_names.add(name.strip().lower())
            students_added += 1

        for idx, (kind, term_name, year) in columns.items():
            if kind != "charge" or idx >= len(values):
                continue
            amount = values[idx]
            if not amount or not isinstance(amount, (int, float)) or amount <= 0:
                continue
            term_id = get_or_create_term(year, term_name)
            add_charge(
                student_id, float(amount), term_id=term_id,
                description=f"Imported balance - {term_name} {year}",
            )
            charges_added += 1

    return {
        "grade": grade,
        "students_added": students_added,
        "students_skipped": students_skipped,
        "charges_added": charges_added,
    }
