import datetime
import tkinter as tk
from tkinter import ttk, messagebox

from models.student import list_students, get_student, get_balance
from models.term import list_terms
from models.bulk_payment import (
    create_bulk_payment, get_bulk_payment, get_bulk_payment_items,
    list_bulk_payments, delete_bulk_payment,
)
from models.user import log_action
from services.receipt_service import generate_receipt
from ui.constants import PAD_MD, PAD_SM, PAD_XS, ZEBRA_EVEN, ZEBRA_ODD, DANGER


class BulkPaymentsTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=PAD_MD)
        self.app = app
        self._all_terms = []
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        top = ttk.Frame(self)
        top.pack(fill="x", pady=(0, PAD_SM))

        ttk.Label(top, text="Term:").pack(side="left")
        self.term_var = tk.StringVar()
        self.term_combo = ttk.Combobox(top, textvariable=self.term_var,
                                       state="readonly", width=20)
        self.term_combo.pack(side="left", padx=PAD_XS)
        self.term_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh())

        ttk.Button(top, text="New Bulk Payment", command=self._open_create_dialog,
                   style="Accent.TButton").pack(side="right", padx=PAD_XS)
        ttk.Button(top, text="View Details", command=self._view_details).pack(side="right", padx=PAD_XS)
        ttk.Button(top, text="Delete", command=self._delete_selected,
                   style="Danger.TButton").pack(side="right", padx=PAD_XS)

        columns = ("id", "date", "payer", "method", "reference", "term", "total", "students")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=18)
        headings = {
            "id": "ID", "date": "Date", "payer": "Payer / Org",
            "method": "Method", "reference": "Reference", "term": "Term",
            "total": "Total (KES)", "students": "Students"
        }
        widths = {
            "id": 50, "date": 140, "payer": 200, "method": 90,
            "reference": 120, "term": 100, "total": 120, "students": 80
        }
        for col in columns:
            self.tree.heading(col, text=headings[col])
            anchor = "e" if col in ("id", "total", "students") else "w"
            self.tree.column(col, width=widths[col], anchor=anchor)
        self.tree.pack(fill="both", expand=True)
        self.tree.tag_configure("odd", background=ZEBRA_ODD)
        self.tree.tag_configure("even", background=ZEBRA_EVEN)

    def refresh(self):
        self._all_terms = list_terms()
        term_lookup = {f"{t['term_name']} {t['year']}": t["id"] for t in self._all_terms}
        self.term_combo["values"] = sorted(term_lookup.keys())
        if not self.term_var.get() and self.term_combo["values"]:
            self.term_var.set(self.term_combo["values"][0])

        term_key = self.term_var.get()
        term_id = term_lookup.get(term_key)

        for row in self.tree.get_children():
            self.tree.delete(row)

        bulk_payments = list_bulk_payments(term_id=term_id)
        for idx, bp in enumerate(bulk_payments):
            tag = "even" if idx % 2 == 0 else "odd"
            term_name = f"{bp['term_name']} {bp['year']}" if bp["term_name"] else "N/A"
            items = get_bulk_payment_items(bp["id"])
            student_count = len(items)
            self.tree.insert("", "end", values=(
                bp["id"],
                bp["date_paid"] or "",
                bp["payer_name"],
                bp["method"],
                bp["reference_no"] or "",
                term_name,
                f"{bp['total_amount']:,.2f}",
                str(student_count),
            ), tags=(tag,))

    def _get_selected_bulk_payment_id(self):
        sel = self.tree.selection()
        if not sel:
            return None
        return int(self.tree.item(sel[0])["values"][0])

    def _open_create_dialog(self):
        CreateBulkPaymentDialog(self, self.app)

    def _view_details(self):
        bp_id = self._get_selected_bulk_payment_id()
        if bp_id is None:
            messagebox.showwarning("Select bulk payment", "Please select a bulk payment to view.")
            return
        ViewBulkPaymentDialog(self, bp_id)

    def _delete_selected(self):
        bp_id = self._get_selected_bulk_payment_id()
        if bp_id is None:
            messagebox.showwarning("Select bulk payment", "Please select a bulk payment to delete.")
            return
        if not messagebox.askyesno("Confirm delete",
                                   "Delete this bulk payment header?\n"
                                   "Individual payment rows will NOT be deleted."):
            return
        try:
            delete_bulk_payment(bp_id)
        except Exception as e:
            messagebox.showerror("Error", f"Could not delete bulk payment:\n{e}")
            return
        log_action(self.app.current_username, "delete_bulk_payment",
                   f"Deleted bulk payment id={bp_id}")
        self.refresh()


class CreateBulkPaymentDialog(tk.Toplevel):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.title("New Bulk Payment")
        self.resizable(False, False)
        self.grab_set()

        self._items = []
        self._build_ui()

    def _build_ui(self):
        frame = ttk.Frame(self, padding=PAD_MD)
        frame.pack()

        ttk.Label(frame, text="Payer / Organisation Name:").grid(
            row=0, column=0, sticky="e", pady=PAD_XS)
        self.payer_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.payer_var, width=40).grid(
            row=0, column=1, pady=PAD_XS)

        ttk.Label(frame, text="Contact Info:").grid(
            row=1, column=0, sticky="e", pady=PAD_XS)
        self.contact_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.contact_var, width=40).grid(
            row=1, column=1, pady=PAD_XS)

        ttk.Label(frame, text="Payment Method:").grid(
            row=2, column=0, sticky="e", pady=PAD_XS)
        self.method_var = tk.StringVar()
        self.method_combo = ttk.Combobox(frame, textvariable=self.method_var,
                                         state="readonly", width=37)
        self.method_combo["values"] = ("Cash", "M-Pesa", "Bank", "In-Kind")
        self.method_combo.current(0)
        self.method_combo.grid(row=2, column=1, pady=PAD_XS)

        ttk.Label(frame, text="Reference No. (Cheque/M-Pesa):").grid(
            row=3, column=0, sticky="e", pady=PAD_XS)
        self.ref_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.ref_var, width=40).grid(
            row=3, column=1, pady=PAD_XS)

        ttk.Label(frame, text="Term:").grid(
            row=4, column=0, sticky="e", pady=PAD_XS)
        self.term_var = tk.StringVar()
        self.term_combo = ttk.Combobox(frame, textvariable=self.term_var,
                                       state="readonly", width=37)
        terms = list_terms()
        term_names = [f"{t['term_name']} {t['year']}" for t in terms]
        self.term_combo["values"] = term_names
        if term_names:
            self.term_combo.current(0)
        self.term_combo.grid(row=4, column=1, pady=PAD_XS)

        ttk.Label(frame, text="Notes:").grid(
            row=5, column=0, sticky="e", pady=PAD_XS)
        self.notes_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.notes_var, width=40).grid(
            row=5, column=1, pady=PAD_XS)

        ttk.Label(frame, text="Students:").grid(
            row=6, column=0, sticky="ne", pady=PAD_XS)
        list_frame = ttk.Frame(frame)
        list_frame.grid(row=6, column=1, pady=PAD_XS, sticky="we")

        columns = ("name", "grade", "amount")
        self.item_tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=6)
        self.item_tree.heading("name", text="Student")
        self.item_tree.heading("grade", text="Grade")
        self.item_tree.heading("amount", text="Amount (KES)")
        self.item_tree.column("name", width=200)
        self.item_tree.column("grade", width=80)
        self.item_tree.column("amount", width=100, anchor="e")
        self.item_tree.pack(side="left", fill="both", expand=True)

        btn_frame = ttk.Frame(list_frame)
        btn_frame.pack(side="right", padx=(PAD_XS, 0))
        ttk.Button(btn_frame, text="Add Student", command=self._add_student).pack(
            fill="x", pady=(0, PAD_XS))
        ttk.Button(btn_frame, text="Remove", command=self._remove_student).pack(fill="x")

        self.total_var = tk.StringVar(value="Total: KES 0.00")
        ttk.Label(frame, textvariable=self.total_var, font=("Segoe UI", 10, "bold")).grid(
            row=7, column=1, sticky="w", pady=(PAD_XS, PAD_MD))

        ttk.Button(frame, text="Save Bulk Payment", command=self._save,
                   style="Accent.TButton").grid(row=8, column=0, columnspan=2, pady=(PAD_MD, 0))

    def _add_student(self):
        dialog = AddStudentDialog(self, self.app)
        if dialog.result:
            self._items.append(dialog.result)
            self._refresh_items()

    def _remove_student(self):
        sel = self.item_tree.selection()
        if not sel:
            return
        idx = self.item_tree.index(sel[0])
        self._items.pop(idx)
        self._refresh_items()

    def _refresh_items(self):
        for row in self.item_tree.get_children():
            self.item_tree.delete(row)
        total = 0.0
        for item in self._items:
            student = get_student(item["student_id"])
            name = student["full_name"] if student else "Unknown"
            grade = student["grade"] if student else "?"
            self.item_tree.insert("", "end", values=(
                name, grade, f"{item['amount']:,.2f}"
            ))
            total += item["amount"]
        self.total_var.set(f"Total: KES {total:,.2f}")

    def _save(self):
        payer = self.payer_var.get().strip()
        if not payer:
            messagebox.showwarning("Missing info", "Payer / Organisation name is required.")
            return
        method = self.method_var.get()
        if not method:
            messagebox.showwarning("Missing info", "Payment method is required.")
            return
        term_key = self.term_var.get()
        if not term_key:
            messagebox.showwarning("Missing info", "Term is required.")
            return
        terms = list_terms()
        term_map = {f"{t['term_name']} {t['year']}": t["id"] for t in terms}
        term_id = term_map.get(term_key)
        if term_id is None:
            messagebox.showwarning("Missing info", "Invalid term selected.")
            return
        if not self._items:
            messagebox.showwarning("Missing info", "Add at least one student.")
            return

        try:
            result = create_bulk_payment(
                payer_name=payer,
                method=method,
                term_id=term_id,
                items=self._items,
                payer_contact=self.contact_var.get().strip() or None,
                reference_no=self.ref_var.get().strip() or None,
                notes=self.notes_var.get().strip() or None,
                created_by=self.app.current_username,
            )
        except Exception as e:
            messagebox.showerror("Error", f"Could not create bulk payment:\n{e}")
            return

        log_action(self.app.current_username, "create_bulk_payment",
                   f"Created bulk payment BULK-{result['bulk_payment_id']:06d} "
                   f"for {payer} ({len(self._items)} students, KES {sum(i['amount'] for i in self._items):,.2f})")
        messagebox.showinfo("Bulk payment created",
                            f"Bulk payment {result['receipt_no']} created.\n"
                            f"{len(self._items)} payment(s) recorded.")
        self.destroy()


class AddStudentDialog(tk.Toplevel):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.result = None
        self.title("Add Student to Bulk Payment")
        self.resizable(False, False)
        self.grab_set()

        frame = ttk.Frame(self, padding=PAD_MD)
        frame.pack()

        ttk.Label(frame, text="Student:").grid(row=0, column=0, sticky="e", pady=PAD_XS)
        self.student_var = tk.StringVar()
        self.student_combo = ttk.Combobox(frame, textvariable=self.student_var,
                                          state="readonly", width=40)
        students = list_students()
        self._student_map = {f"{s['id']} - {s['full_name']} ({s['grade']})": s for s in students}
        self.student_combo["values"] = list(self._student_map.keys())
        self.student_combo.grid(row=0, column=1, pady=PAD_XS)

        ttk.Label(frame, text="Amount (KES):").grid(row=1, column=0, sticky="e", pady=PAD_XS)
        self.amount_var = tk.StringVar()
        self.amount_entry = ttk.Entry(frame, textvariable=self.amount_var, width=20)
        self.amount_entry.grid(row=1, column=1, pady=PAD_XS)

        ttk.Label(frame, text="Notes (optional):").grid(row=2, column=0, sticky="e", pady=PAD_XS)
        self.notes_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.notes_var, width=40).grid(row=2, column=1, pady=PAD_XS)

        ttk.Button(frame, text="Add", command=self._save,
                   style="Accent.TButton").grid(row=3, column=0, columnspan=2, pady=(PAD_MD, 0))

        self.amount_entry.focus_set()

    def _save(self):
        label = self.student_var.get()
        if not label or label not in self._student_map:
            messagebox.showwarning("Missing info", "Please select a student.")
            return
        try:
            amount = float(self.amount_var.get())
        except ValueError:
            messagebox.showwarning("Invalid input", "Amount must be a number.")
            return
        if amount <= 0:
            messagebox.showwarning("Invalid input", "Amount must be positive.")
            return
        student = self._student_map[label]
        self.result = {
            "student_id": student["id"],
            "amount": amount,
            "notes": self.notes_var.get().strip(),
        }
        self.destroy()


class ViewBulkPaymentDialog(tk.Toplevel):
    def __init__(self, parent, bulk_payment_id):
        super().__init__(parent)
        self.bulk_payment_id = bulk_payment_id
        self.title(f"Bulk Payment Details - ID {bulk_payment_id}")
        self.resizable(True, True)
        self.minsize(600, 400)
        self.grab_set()

        bp = get_bulk_payment(bulk_payment_id)
        if not bp:
            messagebox.showerror("Error", "Bulk payment not found.")
            self.destroy()
            return

        items = get_bulk_payment_items(bulk_payment_id)

        frame = ttk.Frame(self, padding=PAD_MD)
        frame.pack(fill="both", expand=True)

        info_frame = ttk.LabelFrame(frame, text="Bulk Payment Info", padding=PAD_MD)
        info_frame.pack(fill="x", pady=(0, PAD_SM))

        fields = [
            ("Payer / Org:", bp["payer_name"]),
            ("Contact:", bp["payer_contact"] or "N/A"),
            ("Method:", bp["method"]),
            ("Reference:", bp["reference_no"] or "N/A"),
            ("Date:", bp["date_paid"]),
            ("Total:", f"KES {bp['total_amount']:,.2f}"),
            ("Notes:", bp["notes"] or "N/A"),
            ("Recorded by:", bp["created_by"] or "N/A"),
        ]
        for i, (label, value) in enumerate(fields):
            ttk.Label(info_frame, text=label, font=("Segoe UI", 9, "bold")).grid(
                row=i, column=0, sticky="ne", pady=PAD_XS)
            ttk.Label(info_frame, text=value, wraplength=400).grid(
                row=i, column=1, sticky="w", pady=PAD_XS, padx=(PAD_XS, 0))

        items_frame = ttk.LabelFrame(frame, text="Students", padding=PAD_MD)
        items_frame.pack(fill="both", expand=True)

        columns = ("id", "name", "grade", "admission", "amount")
        self.item_tree = ttk.Treeview(items_frame, columns=columns, show="headings", height=10)
        headings = {"id": "ID", "name": "Name", "grade": "Grade",
                    "admission": "Admission No.", "amount": "Amount (KES)"}
        widths = {"id": 50, "name": 200, "grade": 80, "admission": 120, "amount": 100}
        for col in columns:
            self.item_tree.heading(col, text=headings[col])
            anchor = "e" if col in ("id", "amount") else "w"
            self.item_tree.column(col, width=widths[col], anchor=anchor)
        self.item_tree.pack(fill="both", expand=True)

        for idx, item in enumerate(items):
            tag = "even" if idx % 2 == 0 else "odd"
            self.item_tree.insert("", "end", values=(
                item["student_id"],
                item["full_name"],
                item["grade"],
                item["admission_no"] or "",
                f"{item['amount']:,.2f}",
            ), tags=(tag,))

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill="x", pady=(PAD_MD, 0))
        ttk.Button(btn_frame, text="Generate Master Receipt",
                   command=lambda: self._generate_master_receipt(bp, items)).pack(side="left")
        ttk.Button(btn_frame, text="Generate All Individual Receipts",
                   command=lambda: self._generate_individual_receipts(items)).pack(side="left", padx=PAD_XS)
        ttk.Button(btn_frame, text="Close", command=self.destroy).pack(side="right")

    def _generate_master_receipt(self, bp, items):
        try:
            from services.receipt_service import generate_bulk_receipt
            path = generate_bulk_receipt(self.bulk_payment_id, bp, items)
            messagebox.showinfo("Receipt generated", f"Master receipt saved to:\n{path}")
            log_action(self.app.current_username, "generate_bulk_receipt",
                       f"Generated master receipt for bulk payment id={self.bulk_payment_id}")
        except Exception as e:
            messagebox.showerror("Error", f"Could not generate receipt:\n{e}")

    def _generate_individual_receipts(self, items):
        count = 0
        errors = []
        for item in items:
            payment_id = item.get("payment_id")
            if not payment_id:
                continue
            try:
                student = get_student(item["student_id"])
                if not student:
                    continue
                balance = get_balance(item["student_id"])
                generate_receipt(payment_id, student, item.get("term_id"), balance)
                count += 1
            except Exception as e:
                errors.append(f"Student {item['full_name']}: {e}")
        if count:
            log_action(self.app.current_username, "generate_bulk_individual_receipts",
                       f"Generated {count} individual receipt(s) for bulk payment id={self.bulk_payment_id}")
        msg = f"Generated {count} receipt(s)."
        if errors:
            msg += f"\n\nErrors:\n" + "\n".join(errors[:5])
        messagebox.showinfo("Receipts generated", msg)
