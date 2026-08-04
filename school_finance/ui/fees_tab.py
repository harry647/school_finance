import tkinter as tk
from tkinter import ttk, messagebox

from models.student import list_grades
from models.term import list_terms, get_or_create_term
from models.fee_structure import set_fee, get_fee, list_fees, delete_fee
from models.user import log_action
from ui.constants import DANGER, FONT_MUTED, PAD_MD, PAD_SM, PAD_XS, ZEBRA_EVEN, ZEBRA_ODD


class FeesTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=PAD_MD)
        self.app = app
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        form = ttk.LabelFrame(self, text="Set Standard Fee", padding=PAD_MD)
        form.pack(fill="x", pady=(0, PAD_SM))

        ttk.Label(form, text="Grade:").grid(row=0, column=0, sticky="e", pady=PAD_XS)
        self.grade_var = tk.StringVar()
        self.grade_combo = ttk.Combobox(form, textvariable=self.grade_var,
                                        state="readonly", width=15)
        self.grade_combo.grid(row=0, column=1, pady=PAD_XS, padx=PAD_XS)

        ttk.Label(form, text="Term:").grid(row=1, column=0, sticky="e", pady=PAD_XS)
        self.term_var = tk.StringVar()
        self.term_combo = ttk.Combobox(form, textvariable=self.term_var,
                                       state="readonly", width=20)
        self.term_combo.grid(row=1, column=1, sticky="w", pady=PAD_XS, padx=PAD_XS)

        ttk.Label(form, text="Amount (KES):").grid(row=2, column=0, sticky="e", pady=PAD_XS)
        self.amount_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.amount_var, width=20).grid(
            row=2, column=1, sticky="w", pady=PAD_XS, padx=PAD_XS)

        ttk.Label(form, text="Description:").grid(row=3, column=0, sticky="e", pady=PAD_XS)
        self.desc_var = tk.StringVar(value="Term fee")
        ttk.Entry(form, textvariable=self.desc_var, width=30).grid(
            row=3, column=1, sticky="w", pady=PAD_XS, padx=PAD_XS)

        ttk.Button(form, text="Save Fee Structure",
                   command=self._save, style="Accent.TButton").grid(row=4, column=0, columnspan=2, pady=(PAD_MD, 0))

        ttk.Button(form, text="Auto-Charge Selected Grade for Selected Term",
                   command=self._auto_charge).grid(row=5, column=0, columnspan=2, pady=(PAD_SM, 0))

        ttk.Separator(self, orient="horizontal").pack(fill="x", pady=(PAD_MD, PAD_MD))

        table_frame = ttk.LabelFrame(self, text="Current Fee Structures", padding=PAD_SM)
        table_frame.pack(fill="both", expand=True)

        columns = ("grade", "term", "amount", "description")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=14)
        self.tree.heading("grade", text="Grade")
        self.tree.heading("term", text="Term")
        self.tree.heading("amount", text="Amount (KES)")
        self.tree.heading("description", text="Description")
        self.tree.column("grade", width=120, anchor="w")
        self.tree.column("term", width=140, anchor="w")
        self.tree.column("amount", width=100, anchor="e")
        self.tree.column("description", width=180, anchor="w")
        self.tree.pack(fill="both", expand=True)
        self.tree.tag_configure("odd", background=ZEBRA_ODD)
        self.tree.tag_configure("even", background=ZEBRA_EVEN)

        btn_frame = ttk.Frame(table_frame)
        btn_frame.pack(fill="x", pady=(PAD_SM, 0))
        ttk.Button(btn_frame, text="Delete Selected",
                   command=self._delete_selected, style="Danger.TButton").pack(side="right")

    def refresh(self):
        grades = list_grades()
        self.grade_combo["values"] = grades

        terms = list_terms()
        self.term_lookup = {f"{t['term_name']} {t['year']}": t["id"] for t in terms}
        self.term_combo["values"] = sorted(self.term_lookup.keys())
        if not self.term_var.get() and self.term_combo["values"]:
            self.term_var.set(self.term_combo["values"][0])

        for row in self.tree.get_children():
            self.tree.delete(row)
        for idx, f in enumerate(list_fees()):
            term_str = f"{f['term_name']} {f['year']}" if f["term_name"] else "-"
            tag = "even" if idx % 2 == 0 else "odd"
            self.tree.insert("", "end", values=(
                f["grade"], term_str, f"{f['amount']:,.2f}", f["description"] or ""), tags=(tag,))

    def _save(self):
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

        set_fee(grade, term_id, amount, self.desc_var.get().strip())
        log_action(self.app.current_username, "set_fee_structure",
                   f"Set {amount} for {grade} / {term_key}")
        messagebox.showinfo("Saved", "Fee structure updated.")
        self.refresh()

    def _auto_charge(self):
        grade = self.grade_var.get().strip()
        term_key = self.term_var.get()
        if not grade or not term_key:
            messagebox.showwarning("Missing info", "Select grade and term.")
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
                    "Please set the fee structure first before auto-charging.")
            else:
                messagebox.showwarning(
                    "No fee structure set",
                    f"No fee structure set for {grade} / {term_key}.\n\n"
                    "Please set the fee structure first before auto-charging.")
            return

        from models.student import list_students, add_charge
        from models.payment import next_receipt_no
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

        log_action(self.app.current_username, "auto_charge",
                   f"Auto-charged {added} students in {grade} for {term_key}"
                   + (f" (skipped {waived_skipped} waived)" if waived_skipped else ""))
        messagebox.showinfo("Auto-charge complete",
                            f"Charged {added} students in {grade}."
                            + (f"\nSkipped {waived_skipped} fee-waived students." if waived_skipped else ""))
        self.app.refresh_all()

    def _delete_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        grade = self.tree.item(sel[0])["values"][0]
        term_str = self.tree.item(sel[0])["values"][1]
        if not messagebox.askyesno("Confirm delete",
                                   f"Delete fee structure for {grade} / {term_str}?"):
            return
        tname, year = term_str.rsplit(" ", 1)
        term_id = None
        for k, v in self.term_lookup.items():
            if k == term_str:
                term_id = v
                break
        if term_id is None:
            term_id = get_or_create_term(int(year), tname)
        delete_fee(grade, term_id)
        log_action(self.app.current_username, "delete_fee_structure",
                   f"Deleted fee for {grade} / {term_str}")
        self.refresh()
