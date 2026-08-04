import os
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import subprocess
import sys
import logging

from models.student import list_students, list_grades, list_streams, get_student, get_balance
from models.term import list_terms, get_or_create_term, get_current_term
from models.payment import add_payment, list_recent_payments, VALID_METHODS
from models.user import log_action
from services.receipt_service import generate_receipt
from services.export_service import export_arrears, export_payments
from services.pdf_report_service import export_payments_pdf
from ui.constants import BORDER, DANGER, FONT_MUTED, MUTED_FG, PAD_MD, PAD_SM, PAD_XS, ZEBRA_EVEN, ZEBRA_ODD, sort_treeview_column

logger = logging.getLogger("school_finance")


def _open_file(path):
    """Cross-platform 'open this file with the default viewer'."""
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # noqa
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass  # non-fatal; the file is still saved on disk


class PaymentsTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=PAD_MD)
        self.app = app
        self.selected_student_id = None
        self._all_payments = []
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        form = ttk.LabelFrame(self, text="Record a Payment", padding=PAD_MD)
        form.pack(fill="x", pady=(0, PAD_SM))

        filter_frame = ttk.Frame(form)
        filter_frame.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, PAD_SM))

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

        ttk.Label(form, text="Student:").grid(row=1, column=0, sticky="e", pady=PAD_XS)
        self.student_var = tk.StringVar()
        self.student_combo = ttk.Combobox(form, textvariable=self.student_var,
                                           width=35, state="readonly")
        self.student_combo.grid(row=1, column=1, pady=PAD_XS, padx=PAD_XS)
        self.student_combo.bind("<<ComboboxSelected>>", self._on_student_selected)

        self.balance_label = ttk.Label(form, text="Current balance: -")
        self.balance_label.grid(row=1, column=2, padx=PAD_MD)

        ttk.Label(form, text="Term:").grid(row=2, column=0, sticky="e", pady=PAD_XS)
        self.term_var = tk.StringVar()
        self.term_combo = ttk.Combobox(form, textvariable=self.term_var, width=20,
                                        state="readonly")
        self.term_combo.grid(row=2, column=1, sticky="w", pady=PAD_XS, padx=PAD_XS)

        ttk.Label(form, text="Amount (KES):").grid(row=3, column=0, sticky="e", pady=PAD_XS)
        self.amount_var = tk.StringVar()
        self.amount_entry = ttk.Entry(form, textvariable=self.amount_var, width=20)
        self.amount_entry.grid(row=3, column=1, sticky="w", pady=PAD_XS, padx=PAD_XS)

        ttk.Label(form, text="Method:").grid(row=4, column=0, sticky="e", pady=PAD_XS)
        self.method_var = tk.StringVar(value=VALID_METHODS[0])
        method_combo = ttk.Combobox(form, textvariable=self.method_var, width=15,
                                     state="readonly", values=VALID_METHODS)
        method_combo.grid(row=4, column=1, sticky="w", pady=PAD_XS, padx=PAD_XS)
        method_combo.bind("<<ComboboxSelected>>", self._on_method_change)

        self.detail_label = ttk.Label(form, text="M-Pesa Code:")
        self.detail_label.grid(row=4, column=2, sticky="e", padx=(PAD_MD, PAD_XS))
        self.detail_var = tk.StringVar()
        self.detail_entry = ttk.Entry(form, textvariable=self.detail_var, width=20)
        self.detail_entry.grid(row=4, column=3, sticky="w")

        ttk.Label(form, text="Received By:").grid(row=5, column=0, sticky="e", pady=PAD_XS)
        self.received_by_var = tk.StringVar(value=self.app.current_username)
        self.received_by_entry = ttk.Entry(form, textvariable=self.received_by_var, width=20)
        self.received_by_entry.grid(row=5, column=1, sticky="w", pady=PAD_XS, padx=PAD_XS)

        ttk.Button(form, text="Save & Print Receipt",
                       command=self._save_payment, style="Accent.TButton").grid(
            row=5, column=3, sticky="e", pady=PAD_XS)

        ttk.Button(form, text="Export Payments PDF",
                        command=self._export_payments_pdf).grid(
            row=5, column=2, sticky="e", padx=(PAD_MD, 0), pady=PAD_XS)
        ttk.Button(form, text="Export Payments Excel",
                        command=self._export_payments).grid(
            row=5, column=2, sticky="e", pady=PAD_XS)

        for w in (self.student_combo, self.term_combo,
                  self.amount_entry, self.detail_entry, self.received_by_entry):
            w.bind("<Return>", lambda e: self._save_payment())

        # Recent payments table
        filter_frame = ttk.Frame(self)
        filter_frame.pack(fill="x", pady=(0, PAD_SM))

        ttk.Label(filter_frame, text="Search:").pack(side="left")
        self.payment_search_var = tk.StringVar()
        payment_search_entry = ttk.Entry(filter_frame, textvariable=self.payment_search_var, width=20)
        payment_search_entry.pack(side="left", padx=PAD_XS)
        payment_search_entry.bind("<KeyRelease>", lambda e: self._apply_payment_search_filter())

        ttk.Label(filter_frame, text="Filter by Student:").pack(side="left")
        self.filter_student_var = tk.StringVar(value="All")
        self.filter_student_combo = ttk.Combobox(
            filter_frame, textvariable=self.filter_student_var,
            state="readonly", width=30)
        self.filter_student_combo.pack(side="left", padx=(PAD_XS, PAD_MD))
        self.filter_student_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_recent_table())

        ttk.Label(filter_frame, text="Term:").pack(side="left")
        self.filter_term_var = tk.StringVar(value="All")
        self.filter_term_combo = ttk.Combobox(
            filter_frame, textvariable=self.filter_term_var,
            state="readonly", width=18)
        self.filter_term_combo.pack(side="left", padx=(PAD_XS, PAD_MD))
        self.filter_term_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_recent_table())

        ttk.Label(filter_frame, text="Method:").pack(side="left")
        self.filter_method_var = tk.StringVar(value="All")
        self.filter_method_combo = ttk.Combobox(
            filter_frame, textvariable=self.filter_method_var,
            state="readonly", width=12,
            values=["All"] + list(VALID_METHODS))
        self.filter_method_combo.pack(side="left", padx=(PAD_XS, PAD_MD))
        self.filter_method_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_recent_table())

        ttk.Label(filter_frame, text="From:").pack(side="left")
        self.filter_date_from_var = tk.StringVar()
        ttk.Entry(filter_frame, textvariable=self.filter_date_from_var, width=12).pack(
            side="left", padx=(PAD_XS, PAD_XS))
        self.filter_date_from_var.trace_add("write", lambda *a: self._refresh_recent_table())

        ttk.Label(filter_frame, text="To:").pack(side="left")
        self.filter_date_to_var = tk.StringVar()
        ttk.Entry(filter_frame, textvariable=self.filter_date_to_var, width=12).pack(
            side="left", padx=(PAD_XS, PAD_MD))
        self.filter_date_to_var.trace_add("write", lambda *a: self._refresh_recent_table())

        ttk.Button(filter_frame, text="Clear",
                        command=self._clear_filters).pack(side="right", padx=PAD_XS)

        table_frame = ttk.LabelFrame(self, text="Recent Payments", padding=PAD_SM)
        table_frame.pack(fill="both", expand=True)

        btn_frame = ttk.Frame(table_frame)
        btn_frame.pack(fill="x", pady=(0, PAD_XS))
        ttk.Button(btn_frame, text="Export Arrears Summary (Excel)",
                        command=self._export_arrears).pack(side="right")

        columns = ("receipt", "student", "grade", "amount", "method", "date")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=14)
        headings = {"receipt": "Receipt No.", "student": "Student", "grade": "Grade",
                    "amount": "Amount", "method": "Method", "date": "Date"}
        widths = {"receipt": 100, "student": 180, "grade": 80, "amount": 100,
                  "method": 90, "date": 140}
        for col in columns:
            self.tree.heading(col, text=headings[col],
                              command=lambda c=col: self._on_sort_column(c))
            self.tree.column(col, width=widths[col], anchor="w")
        self.tree.pack(fill="both", expand=True)
        self.tree.tag_configure("odd", background=ZEBRA_ODD)
        self.tree.tag_configure("even", background=ZEBRA_EVEN)
        self.tree.bind("<Double-1>", self._open_selected_receipt)
        self.tree.bind("<Button-3>", self._show_context_menu)
        self._context_menu = tk.Menu(self, tearoff=0)
        self._context_menu.add_command(label="Void Payment...", command=self._void_selected)
        self._context_menu.add_command(label="Edit Payment...", command=self._edit_selected)

    def _on_method_change(self, event=None):
        if self.method_var.get() == "M-Pesa":
            self.detail_label.config(text="M-Pesa Code:")
            self.detail_entry.config(state="normal")
        elif self.method_var.get() == "In-Kind":
            self.detail_label.config(text="Description:")
            self.detail_entry.config(state="normal")
        else:
            self.detail_label.config(text="")
            self.detail_var.set("")
            self.detail_entry.config(state="disabled")

    def _on_student_selected(self, event=None):
        idx = self.student_combo.current()
        if idx < 0:
            return
        self.selected_student_id = self.student_ids[idx]
        bal = get_balance(self.selected_student_id)
        self.balance_label.config(text=f"Current balance: KES {bal:,.2f}")

    def refresh(self):
        grades = list_grades()
        self.filter_grade_combo["values"] = ["All"] + grades
        self.filter_grade_var.set("All")

        self._update_stream_filter_options()

        self.search_var.set("")

        terms = list_terms()
        self.term_lookup = {f"{t['term_name']} {t['year']}": t["id"] for t in terms}
        for year in (2025, 2026, 2027):
            for tname in ("Term I", "Term II", "Term III"):
                key = f"{tname} {year}"
                if key not in self.term_lookup:
                    self.term_lookup[key] = None

        current_term = get_current_term()
        if current_term:
            current_term_key = f"{current_term['term_name']} {current_term['year']}"
            self.term_combo["values"] = [current_term_key]
            self.term_var.set(current_term_key)
        else:
            self.term_combo["values"] = sorted(self.term_lookup.keys())
            if self.term_combo["values"]:
                self.term_var.set(self.term_combo["values"][0])

        self._update_student_filters()

        all_students = list_students()
        self.filter_student_ids = [s["id"] for s in all_students]
        self.filter_student_combo["values"] = ["All"] + [
            f"{s['full_name']} ({s['grade']} - {s['stream'] or 'N/A'})" for s in all_students]
        self.filter_student_var.set("All")

        self.filter_term_combo["values"] = ["All"] + sorted(self.term_lookup.keys())
        self.filter_term_var.set("All")
        self.filter_method_var.set("All")

        self._on_method_change()
        self._refresh_recent_table()

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
            self._on_student_selected()
        else:
            self.student_var.set("")
            self.selected_student_id = None
            self.balance_label.config(text="Current balance: -")

    def _refresh_recent_table(self):
        for row in self.tree.get_children():
            self.tree.delete(row)

        student_id = None
        if self.filter_student_var.get() != "All":
            idx = self.filter_student_combo.current()
            if idx >= 0 and idx < len(self.filter_student_ids):
                student_id = self.filter_student_ids[idx]

        term_id = None
        if self.filter_term_var.get() != "All":
            term_id = self.term_lookup.get(self.filter_term_var.get())

        method = None
        if self.filter_method_var.get() != "All":
            method = self.filter_method_var.get()

        date_from = self.filter_date_from_var.get().strip() or None
        date_to = self.filter_date_to_var.get().strip() or None

        self._all_payments = list_recent_payments(limit=1000, student_id=student_id,
                                                  term_id=term_id, method=method,
                                                  date_from=date_from, date_to=date_to)
        self._apply_payment_search_filter()

    def _apply_payment_search_filter(self):
        search = self.payment_search_var.get().strip().lower()
        if search:
            filtered = [p for p in self._all_payments
                        if search in str(p["receipt_no"]).lower()
                        or search in p["full_name"].lower()]
        else:
            filtered = list(self._all_payments)

        for row in self.tree.get_children():
            self.tree.delete(row)
        for idx, p in enumerate(filtered):
            tag = "even" if idx % 2 == 0 else "odd"
            self.tree.insert("", "end", values=(
                p["receipt_no"], p["full_name"], p["grade"],
                f"{p['amount']:,.2f}", p["method"], p["date_paid"]),
                tags=(str(p["id"]), tag))

    def _on_sort_column(self, col):
        reverse = getattr(self.tree, "_sorted_reverse", False)
        if getattr(self.tree, "_sorted_col", None) == col:
            reverse = not reverse
        sort_treeview_column(self.tree, col, reverse)

    def _clear_filters(self):
        self.filter_student_var.set("All")
        self.filter_term_var.set("All")
        self.filter_method_var.set("All")
        self.filter_date_from_var.set("")
        self.filter_date_to_var.set("")
        self.payment_search_var.set("")
        self._refresh_recent_table()

    def _show_context_menu(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        self.tree.selection_set(sel[0])
        self._context_menu.post(event.x_root, event.y_root)

    def _get_selected_payment_id(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("No selection", "Please select a payment first.")
            return None
        return int(self.tree.item(sel[0])["values"][0])

    def _void_selected(self):
        payment_id = self._get_selected_payment_id()
        if payment_id is None:
            return
        reason = tk.simpledialog.askstring("Void Payment", "Reason for voiding:")
        if reason is None:
            return
        from models.payment import void_payment
        try:
            void_payment(payment_id, reason)
        except ValueError as e:
            messagebox.showerror("Error", str(e))
            return
        log_action(self.app.current_username, "void_payment",
                   f"Voided payment id={payment_id}: {reason}")
        messagebox.showinfo("Voided", "Payment has been voided.")
        self.refresh()
        self.app.refresh_all()

    def _edit_selected(self):
        payment_id = self._get_selected_payment_id()
        if payment_id is None:
            return
        from models.payment import get_payment, VALID_METHODS
        payment = get_payment(payment_id)
        if payment is None:
            messagebox.showerror("Error", "Payment not found.")
            return
        if payment["voided"]:
            messagebox.showerror("Error", "Cannot edit a voided payment.")
            return
        PaymentEditDialog(self, self.app, payment, on_save=self.refresh)

    def _open_selected_receipt(self, event=None):
        sel = self.tree.selection()
        if not sel:
            return
        receipt_no = self.tree.item(sel[0])["values"][0]
        path = os.path.join(self.app.receipts_dir, f"{receipt_no}.pdf")
        if os.path.exists(path):
            _open_file(path)
        else:
            messagebox.showinfo("Not found", "Receipt PDF file could not be located.")

    def _save_payment(self):
        if self.selected_student_id is None:
            messagebox.showwarning("No student", "Please select a student.")
            return
        try:
            amount = float(self.amount_var.get())
            if amount <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Invalid amount", "Enter a valid positive amount.")
            return

        term_key = self.term_var.get()
        term_id = self.term_lookup.get(term_key)
        if term_id is None and term_key:
            tname, year = term_key.rsplit(" ", 1)
            term_id = get_or_create_term(int(year), tname)

        method = self.method_var.get()
        mpesa_code = self.detail_var.get().strip() if method == "M-Pesa" else None
        in_kind_desc = self.detail_var.get().strip() if method == "In-Kind" else None
        received_by = self.received_by_var.get().strip() or self.app.current_username

        try:
            payment_id, receipt_no = add_payment(
                self.selected_student_id, amount, method, term_id=term_id,
                mpesa_code=mpesa_code, in_kind_desc=in_kind_desc,
                received_by=received_by)
        except ValueError as e:
            messagebox.showerror("Error", str(e))
            return

        student = get_student(self.selected_student_id)
        bal_after = get_balance(self.selected_student_id)
        receipt_path = generate_receipt(payment_id, student, term_id, bal_after)

        log_action(self.app.current_username, "add_payment",
                   f"{receipt_no}: KES {amount} ({method}) for {student['full_name']}")

        messagebox.showinfo(
            "Payment recorded",
            f"Receipt {receipt_no} saved.\nNew balance: KES {bal_after:,.2f}")
        _open_file(receipt_path)

        self.amount_var.set("")
        self.detail_var.set("")
        self._on_student_selected()
        self.refresh()
        self.app.refresh_all()

    def _export_payments(self):
        from services.export_service import export_payments
        payments = list_recent_payments(limit=1000)
        export_data = [
            {
                "Receipt No.": p["receipt_no"],
                "Student": p["full_name"],
                "Grade": p["grade"],
                "Amount": p["amount"],
                "Method": p["method"],
                "Date": p["date_paid"],
                "Term": f"{p['term_name']} {p['year']}"
                if p["term_name"] else "-",
                "Received By": p["received_by"] or "",
            }
            for p in payments
        ]
        path = export_payments(export_data, self.app.receipts_dir)
        if path:
            messagebox.showinfo("Export complete", f"Saved to:\n{path}")

    def _export_payments_pdf(self):
        payments = list_recent_payments(limit=1000)
        path = export_payments_pdf(payments, self.app.receipts_dir)
        if path:
            messagebox.showinfo("Export complete", f"Saved to:\n{path}")
            log_action(self.app.current_username, "export_payments_pdf",
                       f"Exported {len(payments)} payments as PDF")

    def _export_arrears(self):
        from services.report_service import get_arrears_data
        data = get_arrears_data(min_balance=0)
        path = export_arrears(data, self.app.receipts_dir)
        if path:
            messagebox.showinfo("Export complete", f"Saved to:\n{path}")
            log_action(self.app.current_username, "export_arrears",
                       f"Exported {len(data)} arrears records from Payments")


class PaymentEditDialog(tk.Toplevel):
    def __init__(self, parent, app, payment, on_save=None):
        super().__init__(parent)
        self.app = app
        self.payment = payment
        self.on_save = on_save
        self.title("Edit Payment")
        self.resizable(False, False)
        self.grab_set()

        frame = ttk.Frame(self, padding=PAD_MD)
        frame.pack()

        ttk.Label(frame, text="Amount (KES):").grid(row=0, column=0, sticky="e", pady=PAD_XS)
        self.amount_var = tk.StringVar(value=str(payment["amount"]))
        self.amount_entry = ttk.Entry(frame, textvariable=self.amount_var, width=20)
        self.amount_entry.grid(row=0, column=1, pady=PAD_XS, padx=PAD_XS)

        ttk.Label(frame, text="Method:").grid(row=1, column=0, sticky="e", pady=PAD_XS)
        self.method_var = tk.StringVar(value=payment["method"])
        method_combo = ttk.Combobox(frame, textvariable=self.method_var, width=15,
                                     state="readonly", values=VALID_METHODS)
        method_combo.grid(row=1, column=1, sticky="w", pady=PAD_XS, padx=PAD_XS)
        method_combo.bind("<<ComboboxSelected>>", self._on_method_change)

        self.detail_label = ttk.Label(frame, text="M-Pesa Code:")
        self.detail_label.grid(row=1, column=2, sticky="e", padx=(PAD_MD, PAD_XS))
        self.detail_var = tk.StringVar(value=payment["mpesa_code"] or payment["in_kind_desc"] or "")
        self.detail_entry = ttk.Entry(frame, textvariable=self.detail_var, width=20)
        self.detail_entry.grid(row=1, column=3, sticky="w")

        ttk.Label(frame, text="Received By:").grid(row=2, column=0, sticky="e", pady=PAD_XS)
        self.received_by_var = tk.StringVar(value=payment["received_by"] or "")
        self.received_by_entry = ttk.Entry(frame, textvariable=self.received_by_var, width=20)
        self.received_by_entry.grid(row=2, column=1, sticky="w", pady=PAD_XS, padx=PAD_XS)

        ttk.Label(frame, text="Date Paid:").grid(row=3, column=0, sticky="e", pady=PAD_XS)
        self.date_var = tk.StringVar(value=payment["date_paid"])
        self.date_entry = ttk.Entry(frame, textvariable=self.date_var, width=20)
        self.date_entry.grid(row=3, column=1, sticky="w", pady=PAD_XS, padx=PAD_XS)

        ttk.Button(frame, text="Save", command=self._save, style="Accent.TButton").grid(
            row=4, column=0, columnspan=4, pady=(PAD_MD, 0))

        self._on_method_change()

        for w in (self.amount_entry, method_combo, self.detail_entry,
                  self.received_by_entry, self.date_entry):
            w.bind("<Return>", lambda e: self._save())

    def _on_method_change(self, event=None):
        if self.method_var.get() == "M-Pesa":
            self.detail_label.config(text="M-Pesa Code:")
            self.detail_entry.config(state="normal")
        elif self.method_var.get() == "In-Kind":
            self.detail_label.config(text="Description:")
            self.detail_entry.config(state="normal")
        else:
            self.detail_label.config(text="")
            self.detail_var.set("")
            self.detail_entry.config(state="disabled")

    def _save(self):
        try:
            amount = float(self.amount_var.get())
            if amount <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Invalid amount", "Enter a valid positive amount.")
            return

        method = self.method_var.get()
        mpesa_code = self.detail_var.get().strip() if method == "M-Pesa" else None
        in_kind_desc = self.detail_var.get().strip() if method == "In-Kind" else None
        received_by = self.received_by_var.get().strip() or None
        date_paid = self.date_var.get().strip() or None

        try:
            from models.payment import edit_payment
            edit_payment(self.payment["id"], amount=amount, method=method,
                         mpesa_code=mpesa_code, in_kind_desc=in_kind_desc,
                         received_by=received_by, date_paid=date_paid)
        except ValueError as e:
            messagebox.showerror("Error", str(e))
            return

        log_action(self.app.current_username, "edit_payment",
                   f"Edited payment id={self.payment['id']}")
        messagebox.showinfo("Saved", "Payment updated.")
        if self.on_save:
            self.on_save()
        self.destroy()
