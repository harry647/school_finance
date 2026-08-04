"""Report aggregation helpers used by the Dashboard, Arrears, and Income tabs."""
import datetime
from db.database import get_connection
from models.student import (list_students, list_defaulters, list_grades,
                            get_balance, get_total_receivables)
from models.payment import list_recent_payments, VALID_METHODS
from models.term import get_current_term, list_terms
from models.fee_structure import list_fees


def get_dashboard_data(term_id=None):
    conn = get_connection()
    current_term_row = get_current_term()
    current_term = term_id or (current_term_row["id"] if current_term_row else None)

    total_collected = 0.0
    total_outstanding = 0.0
    students_per_grade = {}
    top_defaulters = []
    waived_count = 0

    students = list_students()
    for s in students:
        grade = s["grade"]
        if s["fee_waived"]:
            waived_count += 1
            continue
        students_per_grade[grade] = students_per_grade.get(grade, 0) + 1
        bal = get_balance(s["id"])
        total_outstanding += max(bal, 0)

    if current_term:
        payments = conn.execute(
            "SELECT COALESCE(SUM(p.amount), 0) AS total FROM payments p "
            "JOIN students s ON p.student_id = s.id "
            "WHERE p.term_id = ? AND p.voided = 0 AND s.fee_waived = 0",
            (current_term,),
        ).fetchone()
        total_collected = payments["total"] if payments else 0.0

    defaulters = list_defaulters(min_balance=0, limit=5)
    for d in defaulters:
        top_defaulters.append({
            "name": d["full_name"],
            "grade": d["grade"],
            "stream": dict(d).get("stream", ""),
            "balance": d["balance"],
        })

    return {
        "total_collected_term": total_collected,
        "total_outstanding": total_outstanding,
        "students_per_grade": students_per_grade,
        "top_defaulters": top_defaulters,
        "current_term": current_term_row,
        "waived_count": waived_count,
        "total_receivables": get_total_receivables(),
    }


def get_dashboard_collection_trend(limit=6):
    conn = get_connection()
    rows = conn.execute(
        """SELECT t.year, t.term_name, COALESCE(SUM(p.amount), 0) AS total
           FROM terms t
           LEFT JOIN payments p ON p.term_id = t.id AND p.voided = 0
           GROUP BY t.id
           ORDER BY t.year DESC,
             CASE t.term_name WHEN 'Term I' THEN 1 WHEN 'Term II' THEN 2
             WHEN 'Term III' THEN 3 ELSE 4 END
           LIMIT ?""",
        (limit,),
    ).fetchall()
    result = []
    for r in rows:
        result.append({
            "label": f"{r['term_name']} {r['year']}",
            "total": r["total"],
        })
    result.reverse()
    return result


def get_arrears_data(min_balance=0, grade=None):
    defaulters = list_defaulters(min_balance=min_balance, grade=grade)
    result = []
    for d in defaulters:
        result.append({
            "id": d["id"],
            "full_name": d["full_name"],
            "grade": d["grade"],
            "stream": dict(d).get("stream", ""),
            "admission_no": d["admission_no"],
            "balance": d["balance"],
        })
    return result


def get_income_by_method_data(term_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT method, COALESCE(SUM(amount), 0) AS total FROM payments "
        "WHERE term_id = ? AND voided = 0 GROUP BY method ORDER BY method",
        (term_id,),
    ).fetchall()
    result = {method: 0.0 for method in VALID_METHODS}
    for r in rows:
        result[r["method"]] = r["total"]
    return result


def get_income_by_method_students(term_id, method=None):
    conn = get_connection()
    query = (
        "SELECT p.*, s.full_name, s.grade, t.term_name, t.year FROM payments p "
        "JOIN students s ON p.student_id = s.id "
        "LEFT JOIN terms t ON p.term_id = t.id "
        "WHERE p.term_id = ? AND p.voided = 0"
    )
    params = [term_id]
    if method:
        query += " AND p.method = ?"
        params.append(method)
    query += " ORDER BY p.date_paid DESC"
    return conn.execute(query, params).fetchall()
