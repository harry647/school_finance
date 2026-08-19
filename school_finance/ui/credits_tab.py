import tkinter as tk
from tkinter import ttk, messagebox

from models.student import list_grades, get_student
from models.student_credits import (
    list_reimbursable_credits,
    reimburse_credit,
    get_student_credit_summary,
)
from models.user import log_action
from ui.constants import PAD_MD, PAD_SM, PAD_XS, ZEBRA_EVEN, ZEBRA_ODD, sort_treeview_column


class CreditsTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=PAD_MD)
        self.app = app
        self._credit_map = {}
        self._selected_credit_id = None
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        top = ttk.Frame(self)
        top.pack(fill="x", pady=(0, PAD_SM))

        ttk.Label(top, text="Grade:").pack(side="left")
        self.grade_var = tk.StringVar(value="All")
        self.grade_combo = ttk.Combobox(
            top, textvariable=self.grade_var, state="readonly", width=15)
        self.grade_combo.pack(side="left", padx=PAD_XS)
        self.grade_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh())

        ttk.Button(top, text="Refresh", command=self.refresh).pack(side="left", padx=PAD_XS)
        ttk.Button(top, text="Reimburse Selected", command=self._reimburse_selected,
                   style="Accent.TButton").pack(side="right", padx=PAD_XS)

        columns = ("student", "grade", "admission", "amount", "remaining", "date", "status")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=20)
        headings = {
            "student": "Student", "grade": "Grade",
            "admission": "Admission No.", "amount": "Credited (KES)",
            "remaining": "Remaining (KES)", "date": "Date", "status": "Status"
        }
        widths = {"student": 180, "grade": 90, "admission": 110,
                  "amount": 110, "remaining": 110, "date": 120, "status": 90}
        for col in columns:
            self.tree.heading(col, text=headings[col],
                               command=lambda c=col: self._on_sort_column(c))
            anchor = "e" if col in ("amount", "remaining") else "w"
            self.tree.column(col, width=widths[col], anchor=anchor)
        self.tree.pack(fill="both", expand=True)
        self.tree.tag_configure("odd", background=ZEBRA_ODD)
        self.tree.tag_configure("even", background=ZEBRA_EVEN)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._on_select())

        self.detail_frame = ttk.LabelFrame(self, text="Credit Details", padding=PAD_SM)
        self.detail_frame.pack(fill="x", pady=(PAD_SM, 0))
        self.detail_label = ttk.Label(self.detail_frame, text="Select a credit to view details.")
        self.detail_label.pack(anchor="w")

    def refresh(self):
        grades = ["All"] + list_grades()
        self.grade_combo["values"] = grades
        if self.grade_var.get() not in grades:
            self.grade_var.set("All")

        grade = None if self.grade_var.get() in ("", "All") else self.grade_var.get()
        reimbursable = list_reimbursable_credits(grade=grade)

        self._credit_map = {}
        for row in self.tree.get_children():
            self.tree.delete(row)
        total = 0.0
        for idx, r in enumerate(reimbursable):
            tag = "even" if idx % 2 == 0 else "odd"
            status = "Reimbursable" if r["remaining"] > 0 else "Fully Used"
            credit_id = r["id"]
            student_id = r["student_id"]
            self._credit_map[credit_id] = student_id
            self.tree.insert("", "end", iid=str(credit_id), values=(
                r["full_name"],
                r["grade"],
                r["admission_no"] or "-",
                f"{r['amount']:,.2f}",
                f"{r['remaining']:,.2f}",
                r["created_at"],
                status,
            ), tags=(tag,))
            total += r["remaining"]

        self.summary_text = f"{len(reimbursable)} credit record(s)  |  Total remaining: KES {total:,.2f}"

    def _on_select(self):
        sel = self.tree.selection()
        if not sel:
            self._selected_credit_id = None
            self.detail_label.config(text="Select a credit to view details.")
            return
        self._selected_credit_id = int(sel[0])
        student_id = self._credit_map.get(self._selected_credit_id)
        if student_id is None:
            self.detail_label.config(text="Credit details not found.")
            return
        student = get_student(student_id)
        if student:
            summary = get_student_credit_summary(student_id)
            detail = (
                f"Student: {student['full_name']} ({student['grade']})\n"
                f"Total Credited: KES {summary['total_credited']:,.2f}\n"
                f"Total Remaining: KES {summary['total_remaining']:,.2f}\n"
                f"Total Reimbursed: KES {summary['total_reimbursed']:,.2f}\n"
                f"Active Credit Records: {summary['active_count']}"
            )
            self.detail_label.config(text=detail)

    def _reimburse_selected(self):
        if not self.app.has_permission("can_manage_credits"):
            messagebox.showwarning("Permission denied", "Your role cannot manage credits.")
            return
        if self._selected_credit_id is None:
            messagebox.showwarning("No selection", "Please select a credit to reimburse.")
            return
        values = self.tree.item(self.tree.selection()[0])["values"]
        student_name = values[0]
        amount = values[4]
        if not messagebox.askyesno(
            "Confirm reimbursement",
            f"Reimburse credit of KES {amount} for {student_name}?\n"
            "This will mark the credit as fully reimbursed."
        ):
            return
        try:
            reimburse_credit(
                self._selected_credit_id,
                reimbursed_by=self.app.current_username,
            )
        except Exception as e:
            messagebox.showerror("Error", f"Could not reimburse credit:\n{e}")
            return
        log_action(self.app.current_username, "reimburse_credit",
                   f"Reimbursed credit {self._selected_credit_id} for {student_name}")
        messagebox.showinfo("Reimbursed", "Credit has been marked as reimbursed.")
        self._selected_credit_id = None
        self.detail_label.config(text="Select a credit to view details.")
        self.refresh()

    def _on_sort_column(self, col):
        reverse = getattr(self.tree, "_sorted_reverse", False)
        if getattr(self.tree, "_sorted_col", None) == col:
            reverse = not reverse
        sort_treeview_column(self.tree, col, reverse)
