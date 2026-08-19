import tkinter as tk
from tkinter import ttk, messagebox

from models.term import list_terms, get_current_term
from services.report_service import get_income_by_method_data, get_income_by_method_students
from services.export_service import export_income_by_method
from services.pdf_report_service import export_income_pdf
from models.user import log_action
from ui.constants import FONT_BODY, FONT_TITLE_LG, PAD_MD, PAD_SM, PAD_XS, PRIMARY_DARK, SUCCESS, WARNING, ZEBRA_EVEN, ZEBRA_ODD, PRIMARY, sort_treeview_column


class IncomeTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=PAD_MD)
        self.app = app
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

        ttk.Button(top, text="Export PDF", command=self._export_pdf).pack(side="right", padx=PAD_XS)
        ttk.Button(top, text="Export Excel", command=self._export).pack(side="right", padx=PAD_XS)

        self.cards_frame = ttk.Frame(self)
        self.cards_frame.pack(fill="x", pady=(0, PAD_SM))
        self.cards_frame.columnconfigure(0, weight=1)
        self.cards_frame.columnconfigure(1, weight=1)
        self.cards_frame.columnconfigure(2, weight=1)
        self.cards_frame.columnconfigure(3, weight=1)

        self.cash_var = tk.StringVar(value="KES 0.00")
        self.mpesa_var = tk.StringVar(value="KES 0.00")
        self.bank_var = tk.StringVar(value="KES 0.00")
        self.inkind_var = tk.StringVar(value="KES 0.00")

        ttk.Label(self.cards_frame, textvariable=self.cash_var,
                  font=FONT_TITLE_LG, foreground=SUCCESS).grid(
            row=0, column=0, sticky="nsew", padx=PAD_XS)
        ttk.Label(self.cards_frame, text="Cash", font=FONT_BODY).grid(
            row=1, column=0, sticky="nsew", padx=PAD_XS)

        ttk.Label(self.cards_frame, textvariable=self.mpesa_var,
                  font=FONT_TITLE_LG, foreground=PRIMARY_DARK).grid(
            row=0, column=1, sticky="nsew", padx=PAD_XS)
        ttk.Label(self.cards_frame, text="M-Pesa", font=FONT_BODY).grid(
            row=1, column=1, sticky="nsew", padx=PAD_XS)

        ttk.Label(self.cards_frame, textvariable=self.inkind_var,
                  font=FONT_TITLE_LG, foreground=WARNING).grid(
            row=0, column=2, sticky="nsew", padx=PAD_XS)
        ttk.Label(self.cards_frame, text="In-Kind", font=FONT_BODY).grid(
            row=1, column=2, sticky="nsew", padx=PAD_XS)

        ttk.Label(self.cards_frame, textvariable=self.bank_var,
                  font=FONT_TITLE_LG, foreground=PRIMARY).grid(
            row=0, column=3, sticky="nsew", padx=PAD_XS)
        ttk.Label(self.cards_frame, text="Bank", font=FONT_BODY).grid(
            row=1, column=3, sticky="nsew", padx=PAD_XS)

        columns = ("receipt", "student", "grade", "stream", "amount", "method", "date")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=16)
        headings = {"receipt": "Receipt No.", "student": "Student", "grade": "Grade",
                    "stream": "Stream", "amount": "Amount", "method": "Method", "date": "Date"}
        widths = {"receipt": 100, "student": 170, "grade": 80, "stream": 80,
                  "amount": 100, "method": 90, "date": 140}
        for col in columns:
            self.tree.heading(col, text=headings[col],
                               command=lambda c=col: self._on_sort_column(c))
            self.tree.column(col, width=widths[col], anchor="w")
        self.tree.pack(fill="both", expand=True)
        self.tree.tag_configure("odd", background=ZEBRA_ODD)
        self.tree.tag_configure("even", background=ZEBRA_EVEN)

    def refresh(self):
        terms = list_terms()
        self.term_lookup = {f"{t['term_name']} {t['year']}": t["id"] for t in terms}
        self.term_combo["values"] = sorted(self.term_lookup.keys())
        if not self.term_var.get() and self.term_combo["values"]:
            self.term_var.set(self.term_combo["values"][0])

        term_key = self.term_var.get()
        term_id = self.term_lookup.get(term_key)
        if term_id is None:
            self.cash_var.set("KES 0.00")
            self.mpesa_var.set("KES 0.00")
            self.bank_var.set("KES 0.00")
            self.inkind_var.set("KES 0.00")
            for row in self.tree.get_children():
                self.tree.delete(row)
            return

        data = get_income_by_method_data(term_id)
        self.cash_var.set(f"KES {data.get('Cash', 0):,.2f}")
        self.mpesa_var.set(f"KES {data.get('M-Pesa', 0):,.2f}")
        self.bank_var.set(f"KES {data.get('Bank', 0):,.2f}")
        self.inkind_var.set(f"KES {data.get('In-Kind', 0):,.2f}")

        for row in self.tree.get_children():
            self.tree.delete(row)
        for idx, p in enumerate(get_income_by_method_students(term_id)):
            tag = "even" if idx % 2 == 0 else "odd"
            self.tree.insert("", "end", values=(
                p["receipt_no"], p["full_name"], p["grade"], dict(p).get("stream", "") or "-",
                f"{p['amount']:,.2f}", p["method"], p["date_paid"]), tags=(tag,))

    def _on_sort_column(self, col):
        reverse = getattr(self.tree, "_sorted_reverse", False)
        if getattr(self.tree, "_sorted_col", None) == col:
            reverse = not reverse
        sort_treeview_column(self.tree, col, reverse)

    def _export(self):
        term_key = self.term_var.get()
        term_id = self.term_lookup.get(term_key)
        if term_id is None:
            messagebox.showinfo("No term", "Please select a term.")
            return
        data = get_income_by_method_data(term_id)
        path = export_income_by_method(data, self.app.receipts_dir)
        if path:
            messagebox.showinfo("Export complete", f"Saved to:\n{path}")
            log_action(self.app.current_username, "export_income",
                       f"Exported income by method for {term_key}")

    def _export_pdf(self):
        term_key = self.term_var.get()
        term_id = self.term_lookup.get(term_key)
        if term_id is None:
            messagebox.showinfo("No term", "Please select a term.")
            return
        data = get_income_by_method_data(term_id)
        path = export_income_pdf(data, term_key, self.app.receipts_dir)
        if path:
            messagebox.showinfo("Export complete", f"Saved to:\n{path}")
            log_action(self.app.current_username, "export_income_pdf",
                       f"Exported income by method for {term_key} as PDF")
