import datetime
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

from models.student import (add_student, update_student, delete_student,
                             list_students_with_balance, list_grades, get_student,
                             list_students, set_fee_waiver, remove_fee_waiver,
                             is_fee_waived, list_waived_students, auto_promote_students)
from models.payment import add_charge
from models.term import list_terms, get_or_create_term
from models.fee_structure import get_fee, get_missing_fee_structures
from models.user import log_action
from services.export_service import export_students, export_waived_students
from services.pdf_report_service import export_students_pdf
from ui.constants import (DANGER, FONT_BODY_ITALIC, FONT_MUTED,
                          INACTIVE_BG, INACTIVE_FG, MUTED_FG,
                          OVERDUE_BG, OVERDUE_FG, PAID_BG, PAID_FG,
                          PAD_MD, PAD_SM, PAD_XS,
                          WAIVED_BG, WAIVED_FG, WARNING,
                          ZEBRA_EVEN, ZEBRA_ODD, sort_treeview_column)


class StudentsTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=PAD_MD)
        self.app = app
        self._all_students = []
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        title_row = ttk.Frame(self)
        title_row.pack(fill="x", pady=(0, PAD_SM))
        ttk.Label(title_row, text="Student Register",
                  font=("Segoe UI", 15, "bold")).pack(side="left")
        ttk.Label(title_row,
                  text="Manage student records, balances and fee waivers",
                  foreground=MUTED_FG).pack(side="left", padx=(PAD_SM, 0))

        ttk.Separator(self).pack(fill="x", pady=(0, PAD_SM))

        top = ttk.Frame(self)
        top.pack(fill="x", pady=(0, PAD_SM))

        ttk.Label(top, text="Grade:").pack(side="left")
        self.grade_filter = tk.StringVar(value="All")
        self.grade_combo = ttk.Combobox(top, textvariable=self.grade_filter,
                                         state="readonly", width=15)
        self.grade_combo.pack(side="left", padx=(PAD_XS, PAD_MD))
        self.grade_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh())

        ttk.Label(top, text="Search:").pack(side="left")
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(top, textvariable=self.search_var, width=25)
        search_entry.pack(side="left", padx=PAD_XS)
        search_entry.bind("<KeyRelease>", lambda e: self._apply_search_filter())

        ttk.Button(top, text="Export PDF", command=self._export_pdf).pack(side="right", padx=PAD_XS)
        ttk.Button(top, text="Export Excel",
                       command=self._export_data).pack(side="right", padx=PAD_XS)
        ttk.Button(top, text="Export Waived Students",
                       command=self._export_waived_students).pack(side="right", padx=PAD_XS)
        ttk.Button(top, text="Add Student", command=self._open_add_dialog, style="Accent.TButton").pack(
            side="right", padx=PAD_XS)
        ttk.Button(top, text="Bulk Charge Grade...", command=self._open_bulk_charge_dialog).pack(
            side="right", padx=PAD_XS)
        ttk.Button(top, text="Edit Selected", command=self._open_edit_dialog).pack(
            side="right", padx=PAD_XS)
        self._delete_btn = ttk.Button(
            top, text="Delete Selected", command=self._delete_selected, style="Danger.TButton")
        self._delete_btn.pack(side="right", padx=PAD_XS)
        self._waiver_btn = ttk.Button(
            top, text="Toggle Fee Waiver", command=self._toggle_fee_waiver)
        self._waiver_btn.pack(side="right", padx=PAD_XS)
        self._promote_btn = ttk.Button(
            top, text="Promote Students...", command=self._open_promote_dialog)
        self._promote_btn.pack(side="right", padx=PAD_XS)
        ttk.Button(
            top, text="Auto-Promote All (End of Year)",
            command=self._auto_promote_all).pack(side="right", padx=PAD_XS)
        self._update_delete_button()

        columns = ("id", "name", "grade", "stream", "admission", "balance",
                   "status", "waived", "remarks")
        self.tree = ttk.Treeview(self, columns=columns, show="headings",
                                 height=18, selectmode="browse")
        headings = {"id": "#", "name": "Student Name", "grade": "Grade",
                    "stream": "Stream", "admission": "Admission No.",
                    "balance": "Balance (KES)", "status": "Status",
                    "waived": "Waiver", "remarks": "Remarks"}
        widths = {"id": 46, "name": 200, "grade": 70, "stream": 80,
                  "admission": 112, "balance": 120, "status": 74,
                  "waived": 66, "remarks": 170}
        center_cols = ("id", "grade", "stream", "admission", "balance",
                       "status", "waived")
        for col in columns:
            self.tree.heading(col, text=headings[col],
                               command=lambda c=col: self._on_sort_column(c))
            anchor = "e" if col == "balance" else (
                "center" if col in center_cols else "w")
            self.tree.column(col, width=widths[col], anchor=anchor)

        # Status badges: soft pastel rows with readable accent text.
        self.tree.tag_configure("overdue", background=OVERDUE_BG,
                                foreground=OVERDUE_FG)
        self.tree.tag_configure("paid", background=PAID_BG,
                                foreground=PAID_FG)
        self.tree.tag_configure("waived", background=WAIVED_BG,
                                foreground=WAIVED_FG)
        self.tree.tag_configure("inactive", background=INACTIVE_BG,
                                foreground=INACTIVE_FG)
        self.tree.tag_configure("odd", background=ZEBRA_ODD)
        self.tree.tag_configure("even", background=ZEBRA_EVEN)
        self.tree.pack(fill="both", expand=True)

        summary = ttk.LabelFrame(self, text="Summary",
                                 padding=(PAD_SM, PAD_XS))
        summary.pack(fill="x", pady=(PAD_SM, 0))
        self.summary_label = ttk.Label(summary, text="", font=FONT_BODY_ITALIC)
        self.summary_label.pack(side="left")
        self.summary_label2 = ttk.Label(summary, text="", font=FONT_MUTED,
                                        foreground=MUTED_FG)
        self.summary_label2.pack(side="right")

    def refresh(self):
        grade = None if self.grade_filter.get() in ("", "All") else self.grade_filter.get()
        self._all_students = list_students_with_balance(grade=grade, search=None)
        self._apply_search_filter()

        grades = ["All"] + list_grades()
        self.grade_combo["values"] = grades
        if self.grade_filter.get() not in grades:
            self.grade_filter.set("All")
        self._update_delete_button()

    def _apply_search_filter(self):
        search = self.search_var.get().strip().lower()
        if search:
            filtered = []
            for s in self._all_students:
                haystack = " ".join([
                    str(s.get("id", "")),
                    s.get("full_name", "") or "",
                    s.get("admission_no", "") or "",
                    s.get("grade", "") or "",
                    s.get("stream", "") or "",
                    s.get("status", "") or "",
                    s.get("remarks", "") or "",
                ]).lower()
                if search in haystack:
                    filtered.append(s)
        else:
            filtered = list(self._all_students)

        for row in self.tree.get_children():
            self.tree.delete(row)
        total_balance = 0.0
        waived_count = 0
        owing_count = 0
        paid_count = 0
        inactive_count = 0
        for idx, s in enumerate(filtered):
            status = (s.get("status") or "Active").strip()
            is_waived = s.get("fee_waived", 0)
            if is_waived:
                tag = "waived"
                waived_count += 1
            elif status and status != "Active":
                tag = "inactive"
                inactive_count += 1
            elif s["balance"] > 0:
                tag = "overdue"
                owing_count += 1
            else:
                tag = "paid"
                paid_count += 1
            row_tag = ("even",) if idx % 2 == 0 else ("odd",)
            self.tree.insert("", "end", values=(
                s["id"], s["full_name"], s["grade"],
                dict(s).get("stream", "") or "—",
                s["admission_no"] or "—", f"{s['balance']:,.2f}",
                status, "Yes" if is_waived else "—",
                s["remarks"] or ""),
                tags=row_tag + (tag,))
            total_balance += s["balance"]

        counts = [
            f"Showing {len(filtered)} of {len(self._all_students)}",
            f"Outstanding: KES {total_balance:,.2f}",
        ]
        if owing_count:
            counts.append(f"Owing: {owing_count}")
        if paid_count:
            counts.append(f"Paid-up: {paid_count}")
        if waived_count:
            counts.append(f"Waived: {waived_count}")
        if inactive_count:
            counts.append(f"Inactive: {inactive_count}")
        self.summary_label.config(text="   •   ".join(counts))
        self.summary_label2.config(
            text="Sort by clicking column headings  •  Use Search to filter")

    def _on_sort_column(self, col):
        reverse = getattr(self.tree, "_sorted_reverse", False)
        if getattr(self.tree, "_sorted_col", None) == col:
            reverse = not reverse
        sort_treeview_column(self.tree, col, reverse)

    def _update_delete_button(self):
        if not self.app.has_permission("can_delete_student"):
            self._delete_btn.config(state="disabled")
        else:
            self._delete_btn.config(state="normal")
        if not self.app.has_permission("can_manage_waivers"):
            self._waiver_btn.config(state="disabled")
        else:
            self._waiver_btn.config(state="normal")

    def get_selected_id(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("No selection", "Please select a student first.")
            return None
        return int(self.tree.item(sel[0])["values"][0])

    def _open_add_dialog(self):
        StudentDialog(self, self.app, on_save=self._after_change)

    def _open_edit_dialog(self):
        student_id = self.get_selected_id()
        if student_id is None:
            return
        student = get_student(student_id)
        StudentDialog(self, self.app, student=student, on_save=self._after_change)

    def _delete_selected(self):
        if not self.app.has_permission("can_delete_student"):
            messagebox.showwarning(
                "Permission denied",
                "Your role does not have permission to delete students.")
            return
        student_id = self.get_selected_id()
        if student_id is None:
            return
        student = get_student(student_id)
        if messagebox.askyesno(
                "Confirm delete",
                f"Delete {student['full_name']}? This also deletes their "
                f"payment and charge history. This cannot be undone."):
            delete_student(student_id)
            log_action(self.app.current_username, "delete_student",
                       f"Deleted {student['full_name']} (id={student_id})")
            self._after_change()

    def _after_change(self):
        self.refresh()
        self.app.refresh_all()

    def _open_promote_dialog(self):
        PromoteDialog(self, self.app, on_save=self._after_change)

    def _auto_promote_all(self):
        if not messagebox.askyesno(
                "Confirm Auto-Promotion",
                "This will promote ALL active students to the next grade:\n\n"
                "Grade 7 → Grade 8\n"
                "Grade 8 → Grade 9\n"
                "Grade 9 → Grade 10\n"
                "Grade 10 → Grade 11\n"
                "Grade 11 → Grade 12\n\n"
                "Students already in Grade 12 will not be changed.\n\n"
                "This action cannot be undone. Continue?"):
            return
        summary = auto_promote_students()
        if not summary:
            messagebox.showinfo("Auto-Promotion", "No students were promoted.")
            return
        details = "\n".join(f"{g}: {c} students" for g, c in summary.items())
        messagebox.showinfo("Auto-Promotion Complete",
                            f"Promoted students:\n{details}")
        log_action(self.app.current_username, "auto_promote",
                   f"Auto-promoted: {details}")
        self._after_change()

    def _export_data(self):
        grade = None if self.grade_filter.get() in ("", "All") \
            else self.grade_filter.get()
        search = self.search_var.get().strip() or None
        students = list_students_with_balance(grade=grade, search=search)
        export_data = [
            {
                "ID": s["id"],
                "Full Name": s["full_name"],
                "Grade": s["grade"],
                "Stream": dict(s).get("stream", "") or "",
                "Admission No.": s["admission_no"] or "",
                "Status": s["status"],
                "Waived": "Yes" if s.get("fee_waived", 0) else "No",
                "Waiver Reason": s.get("waiver_reason") or "",
                "Waiver Date": s.get("waiver_date") or "",
                "Remarks": s["remarks"] or "",
                "Balance (KES)": s["balance"],
            }
            for s in students
        ]
        from services.export_service import export_students
        path = export_students(export_data, self.app.receipts_dir)
        if path:
            messagebox.showinfo("Export complete", f"Saved to:\n{path}")

    def _export_pdf(self):
        grade = None if self.grade_filter.get() in ("", "All") \
            else self.grade_filter.get()
        search = self.search_var.get().strip() or None
        students = list_students_with_balance(grade=grade, search=search)
        path = export_students_pdf(students, self.app.receipts_dir)
        if path:
            messagebox.showinfo("Export complete", f"Saved to:\n{path}")
            log_action(self.app.current_username, "export_students_pdf",
                       f"Exported {len(students)} students as PDF")

    def _toggle_fee_waiver(self):
        if not self.app.has_permission("can_manage_waivers"):
            messagebox.showwarning(
                "Permission denied",
                "Your role does not have permission to manage fee waivers.")
            return
        student_id = self.get_selected_id()
        if student_id is None:
            return
        student = get_student(student_id)
        currently_waived = dict(student).get("fee_waived", 0)

        if currently_waived:
            confirm = messagebox.askyesno(
                "Revoke Fee Waiver",
                f"Revoke the full fee waiver for {student['full_name']}? "
                f"Their normal balance will resume being calculated.")
            if not confirm:
                return
            remove_fee_waiver(student_id)
            log_action(self.app.current_username, "remove_fee_waiver",
                       f"Revoked fee waiver for {student['full_name']} (id={student_id})")
        else:
            reason = simpledialog.askstring(
                "Fee Waiver Reason",
                f"Enter a reason for granting a full fee waiver to {student['full_name']}:",
                parent=self)
            if reason is None:
                return
            reason = reason.strip() or None
            set_fee_waiver(student_id, reason, granted_by=self.app.current_username)
            log_action(self.app.current_username, "set_fee_waiver",
                       f"Granted fee waiver to {student['full_name']} (id={student_id})"
                       + (f" — Reason: {reason}" if reason else ""))
            messagebox.showinfo("Waiver granted",
                                f"{student['full_name']} is now fee-waived.")
        self._after_change()

    def _export_waived_students(self):
        students = list_waived_students()
        export_data = [
            {
                "ID": s["id"],
                "Full Name": s["full_name"],
                "Grade": s["grade"],
                "Stream": dict(s).get("stream", "") or "",
                "Admission No.": s["admission_no"] or "",
                "Status": s["status"],
                "Waiver Reason": s["waiver_reason"] or "",
                "Waiver Date": s["waiver_date"] or "",
                "Remarks": s["remarks"] or "",
            }
            for s in students
        ]
        path = export_waived_students(export_data, self.app.receipts_dir)
        if path:
            messagebox.showinfo("Export complete", f"Saved to:\n{path}")
            log_action(self.app.current_username, "export_waived_students",
                       f"Exported {len(students)} waived students")

    def _open_bulk_charge_dialog(self):
        BulkChargeDialog(self, self.app, on_save=self._after_change)


class StudentDialog(tk.Toplevel):
    def __init__(self, parent, app, student=None, on_save=None):
        super().__init__(parent)
        self.app = app
        self.student = student
        self.on_save = on_save
        self.title("Edit Student" if student else "Add Student")
        self.resizable(False, False)
        self.grab_set()

        frame = ttk.Frame(self, padding=PAD_MD)
        frame.pack()

        ttk.Label(frame, text="Full Name:").grid(row=0, column=0, sticky="e", pady=PAD_XS)
        self.name_var = tk.StringVar(value=student["full_name"] if student else "")
        self.name_entry = ttk.Entry(frame, textvariable=self.name_var, width=30)
        self.name_entry.grid(row=0, column=1, pady=PAD_XS)

        ttk.Label(frame, text="Grade:").grid(row=1, column=0, sticky="e", pady=PAD_XS)
        self.grade_var = tk.StringVar(value=student["grade"] if student else "")
        grade_combo = ttk.Combobox(frame, textvariable=self.grade_var, width=27,
                                    values=list_grades())
        grade_combo.grid(row=1, column=1, pady=PAD_XS)

        ttk.Label(frame, text="Stream:").grid(row=2, column=0, sticky="e", pady=PAD_XS)
        self.stream_var = tk.StringVar(
            value=dict(student).get("stream", "") if student else "")
        self.stream_entry = ttk.Entry(frame, textvariable=self.stream_var, width=30)
        self.stream_entry.grid(row=2, column=1, pady=PAD_XS)

        ttk.Label(frame, text="Admission No.:").grid(row=3, column=0, sticky="e", pady=PAD_XS)
        self.adm_var = tk.StringVar(
            value=student["admission_no"] if student and student["admission_no"] else "")
        self.adm_entry = ttk.Entry(frame, textvariable=self.adm_var, width=30)
        self.adm_entry.grid(row=3, column=1, pady=PAD_XS)

        ttk.Label(frame, text="Remarks:").grid(row=4, column=0, sticky="e", pady=PAD_XS)
        self.remarks_var = tk.StringVar(
            value=student["remarks"] if student and student["remarks"] else "")
        self.remarks_entry = ttk.Entry(frame, textvariable=self.remarks_var, width=30)
        self.remarks_entry.grid(row=4, column=1, pady=PAD_XS)

        ttk.Label(frame, text="Full Fee Waiver:").grid(row=5, column=0, sticky="e", pady=PAD_XS)
        self.waived_var = tk.IntVar(
            value=1 if (student and dict(student).get("fee_waived", 0)) else 0)
        self.waived_check = ttk.Checkbutton(
            frame, variable=self.waived_var, command=self._on_waiver_toggle)
        self.waived_check.grid(row=5, column=1, sticky="w", pady=PAD_XS)

        ttk.Label(frame, text="Waiver Reason:").grid(row=6, column=0, sticky="e", pady=PAD_XS)
        self.waiver_reason_var = tk.StringVar(
            value=dict(student).get("waiver_reason") if student and dict(student).get("waiver_reason") else "")
        self.waiver_reason_entry = ttk.Entry(frame, textvariable=self.waiver_reason_var, width=30)
        self.waiver_reason_entry.grid(row=6, column=1, pady=PAD_XS, padx=PAD_XS)
        self._on_waiver_toggle()

        ttk.Button(frame, text="Save", command=self._save, style="Accent.TButton").grid(
            row=7, column=0, columnspan=2, pady=(PAD_MD, 0))

        for w in (self.name_entry, grade_combo, self.stream_entry, self.adm_entry,
                   self.remarks_entry, self.waiver_reason_entry):
            w.bind("<Return>", lambda e: self._save())

    def _on_waiver_toggle(self):
        if self.waived_var.get():
            self.waiver_reason_entry.config(state="normal")
        else:
            self.waiver_reason_entry.config(state="disabled")
        if not self.app.has_permission("can_manage_waivers"):
            self.waived_check.config(state="disabled")

    def _save(self):
        name = self.name_var.get().strip()
        grade = self.grade_var.get().strip()
        if not name or not grade:
            messagebox.showwarning("Missing info", "Name and Grade are required.")
            return
        admission = self.adm_var.get().strip() or None
        stream = self.stream_var.get().strip() or None
        remarks = self.remarks_var.get().strip() or None

        fee_waived = self.waived_var.get()
        waiver_reason = self.waiver_reason_var.get().strip() or None
        waiver_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M") if fee_waived else None

        if self.student:
            update_student(self.student["id"], full_name=name, grade=grade,
                           admission_no=admission, stream=stream, remarks=remarks,
                           fee_waived=fee_waived, waiver_reason=waiver_reason,
                           waiver_date=waiver_date)
            log_action(self.app.current_username, "edit_student",
                       f"Edited {name} (id={self.student['id']})")
            if fee_waived:
                log_action(self.app.current_username, "set_fee_waiver",
                           f"Fee waiver set for {name} (id={self.student['id']})"
                           + (f" — {waiver_reason}" if waiver_reason else ""))
        else:
            new_id = add_student(name, grade, admission_no=admission, stream=stream,
                                 remarks=remarks, fee_waived=fee_waived,
                                 waiver_reason=waiver_reason, waiver_date=waiver_date)
            log_action(self.app.current_username, "add_student", f"Added {name} (id={new_id})")
            if fee_waived:
                log_action(self.app.current_username, "set_fee_waiver",
                           f"Fee waiver set for {name} (id={new_id})"
                           + (f" — {waiver_reason}" if waiver_reason else ""))

        if self.on_save:
            self.on_save()
        self.destroy()


class PromoteDialog(tk.Toplevel):
    def __init__(self, parent, app, on_save=None):
        super().__init__(parent)
        self.app = app
        self.on_save = on_save
        self.title("Promote Students")
        self.resizable(False, False)
        self.grab_set()

        frame = ttk.Frame(self, padding=PAD_MD)
        frame.pack()

        ttk.Label(frame, text="From Grade:").grid(row=0, column=0, sticky="e", pady=PAD_XS)
        self.from_grade_var = tk.StringVar()
        self.from_combo = ttk.Combobox(frame, textvariable=self.from_grade_var,
                                       state="readonly", width=20)
        self.from_combo["values"] = ["Grade 7", "Grade 8", "Grade 9", "Grade 10", "Grade 11"]
        self.from_combo.grid(row=0, column=1, pady=PAD_XS, padx=PAD_XS)
        self.from_combo.bind("<<ComboboxSelected>>", self._on_from_changed)

        ttk.Label(frame, text="To Grade:").grid(row=1, column=0, sticky="e", pady=PAD_XS)
        self.to_grade_var = tk.StringVar()
        self.to_combo = ttk.Combobox(frame, textvariable=self.to_grade_var,
                                     state="readonly", width=20)
        self.to_combo["values"] = []
        self.to_combo.grid(row=1, column=1, pady=PAD_XS, padx=PAD_XS)

        ttk.Button(frame, text="Promote", command=self._promote, style="Accent.TButton").grid(
            row=2, column=0, columnspan=2, pady=(PAD_MD, 0))

        self.status_var = tk.StringVar(value="")
        ttk.Label(frame, textvariable=self.status_var,
                  foreground=MUTED_FG).grid(row=3, column=0, columnspan=2, pady=(PAD_SM, 0))

        for w in (self.from_combo, self.to_combo):
            w.bind("<Return>", lambda e: self._promote())

    def _on_from_changed(self, event=None):
        grade_map = {
            "Grade 7": "Grade 8",
            "Grade 8": "Grade 9",
            "Grade 9": "Grade 10",
            "Grade 10": "Grade 11",
            "Grade 11": "Grade 12",
        }
        from_grade = self.from_grade_var.get()
        to_grade = grade_map.get(from_grade, "")
        self.to_grade_var.set(to_grade)

    def _promote(self):
        from_grade = self.from_grade_var.get().strip()
        to_grade = self.to_grade_var.get().strip()
        if not from_grade or not to_grade:
            messagebox.showwarning("Missing info", "Select both grades.")
            return
        if from_grade == to_grade:
            messagebox.showwarning("Invalid", "From and To grades must differ.")
            return
        if not messagebox.askyesno(
                "Confirm promotion",
                f"Promote all Active students from {from_grade} to {to_grade}?"):
            return
        from models.student import promote_students
        count = promote_students(from_grade, to_grade)
        log_action(self.app.current_username, "promote_students",
                   f"Promoted {count} students from {from_grade} to {to_grade}")
        self.status_var.set(f"Promoted {count} students.")
        messagebox.showinfo("Promotion complete", f"{count} students promoted.")
        if self.on_save:
            self.on_save()
        self.destroy()


class BulkChargeDialog(tk.Toplevel):
    def __init__(self, parent, app, on_save=None):
        super().__init__(parent)
        self.app = app
        self.on_save = on_save
        self.title("Bulk Charge Grade")
        self.resizable(False, False)
        self.grab_set()

        frame = ttk.Frame(self, padding=PAD_MD)
        frame.pack()

        ttk.Label(frame, text="Grade:").grid(row=0, column=0, sticky="e", pady=PAD_XS)
        self.grade_var = tk.StringVar()
        self.grade_combo = ttk.Combobox(frame, textvariable=self.grade_var,
                                        state="readonly", width=20)
        self.grade_combo["values"] = list_grades()
        self.grade_combo.grid(row=0, column=1, pady=PAD_XS, padx=PAD_XS)

        ttk.Label(frame, text="Term:").grid(row=1, column=0, sticky="e", pady=PAD_XS)
        self.term_var = tk.StringVar()
        self.term_combo = ttk.Combobox(frame, textvariable=self.term_var,
                                       state="readonly", width=20)
        terms = list_terms()
        self.term_lookup = {f"{t['term_name']} {t['year']}": t["id"] for t in terms}
        for year in (2025, 2026, 2027):
            for tname in ("Term I", "Term II", "Term III"):
                key = f"{tname} {year}"
                if key not in self.term_lookup:
                    self.term_lookup[key] = None
        self.term_combo["values"] = sorted(self.term_lookup.keys())
        self.term_combo.grid(row=1, column=1, pady=PAD_XS, padx=PAD_XS)
        if self.term_combo["values"]:
            self.term_var.set(self.term_combo["values"][0])

        ttk.Label(frame, text="Amount (KES):").grid(row=2, column=0, sticky="e", pady=PAD_XS)
        self.amount_var = tk.StringVar()
        self.amount_entry = ttk.Entry(frame, textvariable=self.amount_var, width=20)
        self.amount_entry.grid(row=2, column=1, sticky="w", pady=PAD_XS, padx=PAD_XS)

        ttk.Label(frame, text="Description:").grid(row=3, column=0, sticky="e", pady=PAD_XS)
        self.desc_var = tk.StringVar(value="Term fee")
        ttk.Entry(frame, textvariable=self.desc_var, width=30).grid(
            row=3, column=1, sticky="w", pady=PAD_XS, padx=PAD_XS)

        ttk.Button(frame, text="Charge Grade", command=self._charge, style="Accent.TButton").grid(
            row=4, column=0, columnspan=2, pady=(PAD_MD, 0))

        self.status_var = tk.StringVar(value="")
        ttk.Label(frame, textvariable=self.status_var,
                  foreground=MUTED_FG).grid(row=5, column=0, columnspan=2, pady=(PAD_SM, 0))

        for w in (self.grade_combo, self.term_combo, self.amount_entry):
            w.bind("<Return>", lambda e: self._charge())

    def _charge(self):
        grade = self.grade_var.get().strip()
        term_key = self.term_var.get()
        if not grade or not term_key:
            messagebox.showwarning("Missing info", "Select grade and term.")
            return
        try:
            amount = float(self.amount_var.get())
            if amount <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Invalid amount", "Enter a valid positive amount.")
            return

        term_id = self.term_lookup.get(term_key)
        if term_id is None:
            tname, year = term_key.rsplit(" ", 1)
            term_id = get_or_create_term(int(year), tname)

        fee = get_fee(grade, term_id)
        if fee is None:
            tname, year = term_key.rsplit(" ", 1)
            missing = get_missing_fee_structures(grade, int(year))
            if missing:
                missing_list = ", ".join(m["term_name"] for m in missing)
                messagebox.showwarning(
                    "No fee structure set",
                    f"No fee structure set for {grade} / {term_key}.\n\n"
                    f"Missing fees for: {missing_list}\n\n"
                    "Please set the fee structure first before charging.")
            else:
                messagebox.showwarning(
                    "No fee structure set",
                    f"No fee structure set for {grade} / {term_key}.\n\n"
                    "Please set the fee structure first before charging.")
            return

        from models.student import list_students
        students = list_students(grade=grade, search=None)
        added = 0
        waived_skipped = 0
        for s in students:
            if s["status"] != "Active":
                continue
            if s.get("fee_waived", 0):
                waived_skipped += 1
                continue
            add_charge(s["id"], fee["amount"], term_id=term_id,
                       description=fee["description"] or "Term fee")
            added += 1

        log_action(self.app.current_username, "bulk_charge",
                   f"Bulk-charged {added} students in {grade} for {term_key}"
                   + (f" (skipped {waived_skipped} waived)" if waived_skipped else ""))
        self.status_var.set(f"Charged {added} students (skipped {waived_skipped} waived).")
        messagebox.showinfo("Bulk charge complete",
                            f"Charged {added} students in {grade}."
                            + (f"\nSkipped {waived_skipped} fee-waived students." if waived_skipped else ""))
        if self.on_save:
            self.on_save()
        self.destroy()
