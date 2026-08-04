import tkinter as tk
from tkinter import ttk, messagebox

from models.student import list_students, get_student
from models.payment import list_charges_for_student
from models.waiver import (
    get_student_waiver_summary,
    get_student_term_waivers,
    add_waiver,
    revoke_waiver,
)
from models.user import log_action
from ui.constants import PAD_MD, PAD_SM, PAD_XS, ZEBRA_EVEN, ZEBRA_ODD


class WaiversTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=PAD_MD)
        self.app = app
        self._all_students = []
        self._selected_student_id = None
        self._selected_term_id = None
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        top = ttk.Frame(self)
        top.pack(fill="x", pady=(0, PAD_SM))

        ttk.Label(top, text="Student:").pack(side="left")
        self.student_var = tk.StringVar()
        self.student_combo = ttk.Combobox(
            top, textvariable=self.student_var, state="readonly", width=40)
        self.student_combo.pack(side="left", padx=PAD_XS)
        self.student_combo.bind("<<ComboboxSelected>>", lambda e: self._on_student_changed())

        ttk.Button(top, text="Refresh", command=self.refresh).pack(side="left", padx=PAD_XS)
        ttk.Button(top, text="Add Partial Waiver", command=self._open_add_waiver_dialog,
                   style="Accent.TButton").pack(side="right", padx=PAD_XS)
        ttk.Button(top, text="Revoke Selected", command=self._revoke_selected_waiver,
                   style="Danger.TButton").pack(side="right", padx=PAD_XS)

        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)

        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=1)

        ttk.Label(left_frame, text="Term-wise Waiver Summary",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, PAD_XS))

        columns = ("term", "gross", "waived", "net")
        self.term_tree = ttk.Treeview(left_frame, columns=columns, show="headings", height=15)
        headings = {"term": "Term", "gross": "Gross Fee (KES)",
                    "waived": "Waived (KES)", "net": "Net Fee (KES)"}
        widths = {"term": 160, "gross": 130, "waived": 130, "net": 130}
        for col in columns:
            self.term_tree.heading(col, text=headings[col])
            self.term_tree.column(col, width=widths[col], anchor="e" if col != "term" else "w")
        self.term_tree.pack(fill="both", expand=True)
        self.term_tree.tag_configure("odd", background=ZEBRA_ODD)
        self.term_tree.tag_configure("even", background=ZEBRA_EVEN)
        self.term_tree.bind("<<TreeviewSelect>>", lambda e: self._on_term_selected())

        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=1)

        ttk.Label(right_frame, text="Individual Waivers for Selected Term",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, PAD_XS))

        columns = ("charge", "amount", "reason", "granted_by", "date", "status")
        self.waiver_tree = ttk.Treeview(right_frame, columns=columns, show="headings", height=15)
        headings = {"charge": "Charge Description", "amount": "Amount (KES)",
                    "reason": "Reason", "granted_by": "Granted By",
                    "date": "Date", "status": "Status"}
        widths = {"charge": 140, "amount": 100, "reason": 120,
                  "granted_by": 90, "date": 120, "status": 80}
        for col in columns:
            self.waiver_tree.heading(col, text=headings[col])
            anchor = "e" if col == "amount" else "w"
            self.waiver_tree.column(col, width=widths[col], anchor=anchor)
        self.waiver_tree.pack(fill="both", expand=True)
        self.waiver_tree.tag_configure("odd", background=ZEBRA_ODD)
        self.waiver_tree.tag_configure("even", background=ZEBRA_EVEN)

    def refresh(self):
        self._all_students = list_students()
        student_names = [f"{s['id']} - {s['full_name']} ({s['grade']})" for s in self._all_students]
        self.student_combo["values"] = student_names
        if self._selected_student_id is not None:
            for i, s in enumerate(self._all_students):
                if s["id"] == self._selected_student_id:
                    self.student_combo.current(i)
                    break
            else:
                self.student_combo.set("")
                self._selected_student_id = None
        self._load_term_summary()

    def _on_student_changed(self):
        idx = self.student_combo.current()
        if idx >= 0:
            self._selected_student_id = self._all_students[idx]["id"]
        else:
            self._selected_student_id = None
        self._selected_term_id = None
        self._load_term_summary()
        self._load_waivers()

    def _on_term_selected(self):
        sel = self.term_tree.selection()
        if not sel:
            self._selected_term_id = None
            self._load_waivers()
            return
        self._selected_term_id = int(sel[0])
        self._load_waivers()

    def _load_term_summary(self):
        for row in self.term_tree.get_children():
            self.term_tree.delete(row)
        if self._selected_student_id is None:
            return
        summaries = get_student_waiver_summary(self._selected_student_id)
        for idx, s in enumerate(summaries):
            tag = "even" if idx % 2 == 0 else "odd"
            self.term_tree.insert("", "end", iid=str(s["term_id"]), values=(
                f"{s['term_key']}",
                f"{s['gross_fee']:,.2f}",
                f"{s['waived']:,.2f}",
                f"{s['net_fee']:,.2f}",
            ), tags=(tag,))

    def _load_waivers(self):
        for row in self.waiver_tree.get_children():
            self.waiver_tree.delete(row)
        if self._selected_student_id is None or self._selected_term_id is None:
            return
        rows = get_student_term_waivers(self._selected_student_id, self._selected_term_id, active_only=False)
        for idx, w in enumerate(rows):
            tag = "even" if idx % 2 == 0 else "odd"
            status = "Active" if not w["revoked_at"] else f"Revoked ({w['revoked_at']})"
            self.waiver_tree.insert("", "end", iid=str(w["id"]), values=(
                w["description"] or f"Charge #{w['charge_id']}",
                f"{w['amount']:,.2f}",
                w["reason"] or "",
                w["granted_by"] or "",
                w["granted_at"] or "",
                status,
            ), tags=(tag,))

    def _open_add_waiver_dialog(self):
        if not self.app.has_permission("can_manage_waivers"):
            messagebox.showwarning("Permission denied", "Your role cannot manage waivers.")
            return
        if self._selected_student_id is None or self._selected_term_id is None:
            messagebox.showwarning("Select student and term",
                                   "Please select a student and a term first.")
            return
        student = get_student(self._selected_student_id)
        if not student:
            messagebox.showerror("Error", "Student not found.")
            return
        charges = list_charges_for_student(self._selected_student_id)
        term_charges = [c for c in charges if c["term_id"] == self._selected_term_id]
        if not term_charges:
            messagebox.showinfo("No charges", "No charges found for this student in the selected term.")
            return

        dialog = tk.Toplevel(self)
        dialog.title(f"Add Partial Waiver - {student['full_name']}")
        dialog.resizable(False, False)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding=PAD_MD)
        frame.pack()

        ttk.Label(frame, text="Select Charge:").grid(row=0, column=0, sticky="e", pady=PAD_XS)
        charge_var = tk.StringVar()
        charge_combo = ttk.Combobox(frame, textvariable=charge_var, state="readonly", width=40)
        charge_map = {}
        for c in term_charges:
            label = f"{c['description'] or 'Charge'} - KES {c['amount']:,.2f} (Net: KES {c['net_amount']:,.2f})"
            charge_map[label] = c
        charge_combo["values"] = list(charge_map.keys())
        charge_combo.grid(row=0, column=1, pady=PAD_XS)

        ttk.Label(frame, text="Waiver Amount (KES):").grid(row=1, column=0, sticky="e", pady=PAD_XS)
        amount_var = tk.StringVar()
        amount_entry = ttk.Entry(frame, textvariable=amount_var, width=20)
        amount_entry.grid(row=1, column=1, pady=PAD_XS)

        ttk.Label(frame, text="Reason:").grid(row=2, column=0, sticky="e", pady=PAD_XS)
        reason_var = tk.StringVar()
        reason_entry = ttk.Entry(frame, textvariable=reason_var, width=40)
        reason_entry.grid(row=2, column=1, pady=PAD_XS)

        def _save():
            label = charge_var.get()
            if not label or label not in charge_map:
                messagebox.showwarning("Missing info", "Please select a charge.")
                return
            charge = charge_map[label]
            try:
                amount = float(amount_var.get())
            except ValueError:
                messagebox.showwarning("Invalid input", "Waiver amount must be a number.")
                return
            if amount <= 0:
                messagebox.showwarning("Invalid input", "Waiver amount must be positive.")
                return
            remaining = charge["amount"] - charge["waiver_total"]
            if amount > remaining:
                messagebox.showwarning("Invalid amount",
                                       f"Waiver amount KES {amount:,.2f} exceeds remaining "
                                       f"gross fee KES {remaining:,.2f}.")
                return
            reason = reason_var.get().strip() or None
            try:
                waiver_id = add_waiver(
                    student_id=self._selected_student_id,
                    amount=amount,
                    charge_id=charge["id"],
                    reason=reason,
                    granted_by=self.app.current_username,
                )
            except Exception as e:
                messagebox.showerror("Error", f"Could not add waiver:\n{e}")
                return
            log_action(self.app.current_username, "add_partial_waiver",
                       f"Added partial waiver KES {amount:,.2f} for {student['full_name']} "
                       f"(charge_id={charge['id']}, waiver_id={waiver_id})")
            messagebox.showinfo("Waiver added", f"Partial waiver of KES {amount:,.2f} recorded.")
            dialog.destroy()
            self._load_term_summary()
            self._load_waivers()

        ttk.Button(frame, text="Save Waiver", command=_save,
                   style="Accent.TButton").grid(row=3, column=0, columnspan=2, pady=(PAD_MD, 0))

        for w in (charge_combo, amount_entry, reason_entry):
            w.bind("<Return>", lambda e: _save())

        amount_entry.focus_set()

    def _revoke_selected_waiver(self):
        if not self.app.has_permission("can_manage_waivers"):
            messagebox.showwarning("Permission denied", "Your role cannot manage waivers.")
            return
        sel = self.waiver_tree.selection()
        if not sel:
            messagebox.showwarning("Select waiver", "Please select a waiver to revoke.")
            return
        waiver_id = int(sel[0])
        values = self.waiver_tree.item(sel[0])["values"]
        status = values[5] if len(values) > 5 else ""
        if status.startswith("Revoked"):
            messagebox.showinfo("Already revoked", "This waiver is already revoked.")
            return
        if not messagebox.askyesno("Confirm revoke",
                                   "Revoke this partial waiver?\nThe row will be kept for audit."):
            return
        charge_desc = values[0]
        amount = values[1]
        student_name = get_student(self._selected_student_id)["full_name"] if self._selected_student_id else "Unknown"
        try:
            revoke_waiver(waiver_id, reason=None, revoked_by=self.app.current_username)
        except Exception as e:
            messagebox.showerror("Error", f"Could not revoke waiver:\n{e}")
            return
        log_action(self.app.current_username, "revoke_partial_waiver",
                   f"Revoked partial waiver KES {amount} for {student_name} (charge={charge_desc})")
        messagebox.showinfo("Waiver revoked", "Partial waiver has been revoked.")
        self._load_waivers()
