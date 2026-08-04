import tkinter as tk
from tkinter import ttk, messagebox
import logging
import datetime

from models.student import list_students, list_grades, list_streams, get_student, get_balance
from models.term import list_terms
from models.user import log_action
from services.statement_service import generate_statement
from ui.payments_tab import _open_file
from ui.constants import FONT_BODY, FONT_BODY_ITALIC, MUTED_FG, PAD_MD, PAD_SM, PAD_XS

logger = logging.getLogger("school_finance")


class StatementsTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=PAD_MD)
        self.app = app
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        form = ttk.LabelFrame(self, text="Generate Fee Statement", padding=PAD_MD)
        form.pack(fill="x")

        filter_frame = ttk.Frame(form)
        filter_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, PAD_SM))

        ttk.Label(filter_frame, text="Grade:").pack(side="left")
        self.filter_grade_var = tk.StringVar(value="All")
        self.filter_grade_combo = ttk.Combobox(
            filter_frame, textvariable=self.filter_grade_var,
            state="readonly", width=12)
        self.filter_grade_combo.pack(side="left", padx=(PAD_XS, PAD_MD))
        self.filter_grade_combo.bind("<<ComboboxSelected>>", lambda e: self._update_student_filters())

        ttk.Label(filter_frame, text="Stream:").pack(side="left")
        self.filter_stream_var = tk.StringVar(value="All")
        self.filter_stream_combo = ttk.Combobox(
            filter_frame, textvariable=self.filter_stream_var,
            state="readonly", width=12)
        self.filter_stream_combo.pack(side="left", padx=(PAD_XS, PAD_MD))
        self.filter_stream_combo.bind("<<ComboboxSelected>>", lambda e: self._update_student_filters())

        ttk.Label(filter_frame, text="Search:").pack(side="left")
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(filter_frame, textvariable=self.search_var, width=20)
        search_entry.pack(side="left", padx=PAD_XS)
        search_entry.bind("<KeyRelease>", lambda e: self._update_student_filters())

        ttk.Label(filter_frame, text="Year:").pack(side="left")
        self.year_var = tk.StringVar(value="All")
        self.year_combo = ttk.Combobox(
            filter_frame, textvariable=self.year_var,
            state="readonly", width=10)
        self.year_combo.pack(side="left", padx=(PAD_XS, PAD_MD))

        ttk.Label(filter_frame, text="Term:").pack(side="left")
        self.term_var = tk.StringVar(value="All")
        self.term_combo = ttk.Combobox(filter_frame, textvariable=self.term_var,
                                       state="readonly", width=18)
        self.term_combo.pack(side="left", padx=(PAD_XS, PAD_MD))

        ttk.Label(form, text="Student:").grid(row=1, column=0, sticky="e", pady=PAD_SM)
        self.student_var = tk.StringVar()
        self.student_combo = ttk.Combobox(form, textvariable=self.student_var,
                                           width=40, state="readonly")
        self.student_combo.grid(row=1, column=1, pady=PAD_SM, padx=PAD_SM)
        self.student_combo.bind("<<ComboboxSelected>>", self._on_select)

        self.balance_label = ttk.Label(form, text="Current balance: -",
                                        font=FONT_BODY)
        self.balance_label.grid(row=2, column=0, columnspan=2, pady=(0, PAD_SM))

        ttk.Button(form, text="Generate & Open Statement PDF",
                   command=self._generate).grid(row=3, column=0, columnspan=2, pady=PAD_SM)

        ttk.Label(
            self,
            text=("The statement lists every fee charge and every payment "
                  "recorded for the selected student, with a running balance."),
            wraplength=500, foreground=MUTED_FG
        ).pack(pady=PAD_MD)

    def refresh(self):
        grades = list_grades()
        self.filter_grade_combo["values"] = ["All"] + grades
        self.filter_grade_var.set("All")
        self._update_stream_filter_options()
        self.search_var.set("")
        self._update_student_filters()

        current_year = datetime.datetime.now().year
        years = ["All"] + [str(y) for y in range(current_year - 2, current_year + 3)]
        self.year_combo["values"] = years
        self.year_var.set("All")

        terms = list_terms()
        self.term_lookup = {"All": None}
        for t in terms:
            key = f"{t['term_name']} {t['year']}"
            self.term_lookup[key] = t["id"]
        self.term_combo["values"] = sorted(self.term_lookup.keys())
        self.term_var.set("All")

    def _update_stream_filter_options(self):
        grade = self.filter_grade_var.get()
        if grade == "All":
            self.filter_stream_combo["values"] = ["All"] + list_streams()
        else:
            self.filter_stream_combo["values"] = ["All"] + list_streams(grade=grade)
        self.filter_stream_var.set("All")

    def _update_student_filters(self):
        grade = None if self.filter_grade_var.get() in ("", "All") else self.filter_grade_var.get()
        stream = None if self.filter_stream_var.get() in ("", "All") else self.filter_stream_var.get()
        search = self.search_var.get().strip() or None

        students = list_students(grade=grade, stream=stream, search=search)
        self.student_ids = [s["id"] for s in students]
        self.student_combo["values"] = [
            f"{s['full_name']} ({s['grade']} - {s['stream'] or 'N/A'})" for s in students]
        if self.student_combo["values"]:
            self.student_var.set(self.student_combo["values"][0])
            self._on_select()
        else:
            self.student_var.set("")
            self.balance_label.config(text="Current balance: -")

    def _on_select(self, event=None):
        idx = self.student_combo.current()
        if idx < 0:
            return
        student_id = self.student_ids[idx]
        bal = get_balance(student_id)
        self.balance_label.config(text=f"Current balance: KES {bal:,.2f}")

    def _generate(self):
        idx = self.student_combo.current()
        if idx < 0:
            messagebox.showwarning("No student", "Please select a student.")
            return
        student_id = self.student_ids[idx]
        student = get_student(student_id)
        term_key = self.term_var.get()
        term_id = self.term_lookup.get(term_key)
        year = None
        if self.year_var.get() != "All":
            year = int(self.year_var.get())
        try:
            path = generate_statement(student, term_id=term_id, year=year)
            log_action(self.app.current_username, "generate_statement",
                       f"Statement for {student['full_name']}")
            messagebox.showinfo("Statement ready", f"Saved to:\n{path}")
            _open_file(path)
        except Exception as e:
            logger.error("Failed to generate statement for %s: %s", student["full_name"], e, exc_info=True)
            messagebox.showerror("Error", f"Failed to generate statement: {e}")
