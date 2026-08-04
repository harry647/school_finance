import tkinter as tk
from tkinter import ttk, messagebox

from models.student import list_grades, get_student
from services.report_service import get_arrears_data
from services.export_service import export_arrears
from services.pdf_report_service import export_arrears_pdf
from models.user import log_action
from ui.constants import FONT_BODY_ITALIC, FONT_MUTED, PAD_MD, PAD_SM, PAD_XS, ZEBRA_EVEN, ZEBRA_ODD


class ArrearsTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=PAD_MD)
        self.app = app
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        top = ttk.Frame(self)
        top.pack(fill="x", pady=(0, PAD_SM))

        ttk.Label(top, text="Min Balance:").pack(side="left")
        self.min_balance_var = tk.StringVar(value="0")
        ttk.Entry(top, textvariable=self.min_balance_var, width=10).pack(side="left", padx=PAD_XS)

        ttk.Label(top, text="Grade:").pack(side="left")
        self.grade_var = tk.StringVar(value="All")
        self.grade_combo = ttk.Combobox(top, textvariable=self.grade_var,
                                        state="readonly", width=15)
        self.grade_combo.pack(side="left", padx=PAD_XS)
        self.grade_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh())

        ttk.Button(top, text="Apply Filter", command=self.refresh).pack(side="left", padx=PAD_XS)
        ttk.Button(top, text="Export PDF", command=self._export_pdf).pack(side="right", padx=PAD_XS)
        ttk.Button(top, text="Export Excel", command=self._export).pack(side="right", padx=PAD_XS)

        columns = ("id", "name", "grade", "stream", "admission", "balance")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=20)
        headings = {"id": "ID", "name": "Full Name", "grade": "Grade",
                    "stream": "Stream", "admission": "Admission No.", "balance": "Balance (KES)"}
        widths = {"id": 40, "name": 200, "grade": 90, "stream": 90,
                  "admission": 120, "balance": 120}
        for col in columns:
            self.tree.heading(col, text=headings[col])
            self.tree.column(col, width=widths[col],
                              anchor="center" if col in ("id", "grade", "stream", "balance") else "w")
        self.tree.pack(fill="both", expand=True)
        self.tree.tag_configure("odd", background=ZEBRA_ODD)
        self.tree.tag_configure("even", background=ZEBRA_EVEN)

        self.tree.bind("<Double-1>", self._open_statement)

        self.summary_label = ttk.Label(self, text="", font=FONT_BODY_ITALIC)
        self.summary_label.pack(anchor="w", pady=(PAD_SM, 0))

    def refresh(self):
        try:
            min_balance = float(self.min_balance_var.get())
        except ValueError:
            min_balance = 0.0

        grade = None if self.grade_var.get() in ("", "All") else self.grade_var.get()
        arrears = get_arrears_data(min_balance=min_balance, grade=grade)

        for row in self.tree.get_children():
            self.tree.delete(row)
        total = 0.0
        for idx, a in enumerate(arrears):
            tag = "even" if idx % 2 == 0 else "odd"
            self.tree.insert("", "end", values=(
                a["id"], a["full_name"], a["grade"], dict(a).get("stream", "") or "-",
                a["admission_no"] or "-", f"{a['balance']:,.2f}"), tags=(tag,))
            total += a["balance"]

        self.summary_label.config(
            text=f"{len(arrears)} student(s) in arrears  |  Total: KES {total:,.2f}")

        grades = ["All"] + list_grades()
        self.grade_combo["values"] = grades
        if self.grade_var.get() not in grades:
            self.grade_var.set("All")

    def _export(self):
        try:
            min_balance = float(self.min_balance_var.get())
        except ValueError:
            min_balance = 0.0
        grade = None if self.grade_var.get() in ("", "All") else self.grade_var.get()
        data = get_arrears_data(min_balance=min_balance, grade=grade)
        path = export_arrears(data, self.app.receipts_dir)
        if path:
            messagebox.showinfo("Export complete", f"Saved to:\n{path}")
            log_action(self.app.current_username, "export_arrears",
                       f"Exported {len(data)} arrears records")

    def _export_pdf(self):
        try:
            min_balance = float(self.min_balance_var.get())
        except ValueError:
            min_balance = 0.0
        grade = None if self.grade_var.get() in ("", "All") else self.grade_var.get()
        data = get_arrears_data(min_balance=min_balance, grade=grade)
        path = export_arrears_pdf(data, self.app.receipts_dir)
        if path:
            messagebox.showinfo("Export complete", f"Saved to:\n{path}")
            log_action(self.app.current_username, "export_arrears_pdf",
                       f"Exported {len(data)} arrears records as PDF")

    def _open_statement(self, event=None):
        sel = self.tree.selection()
        if not sel:
            return
        student_id = int(self.tree.item(sel[0])["values"][0])
        student = get_student(student_id)
        if student:
            from services.statement_service import generate_statement
            from ui.payments_tab import _open_file
            path = generate_statement(student)
            log_action(self.app.current_username, "generate_statement",
                       f"Statement for {student['full_name']}")
            _open_file(path)
