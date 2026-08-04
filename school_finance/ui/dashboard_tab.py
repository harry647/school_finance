import tkinter as tk
from tkinter import ttk, messagebox

from services.report_service import get_dashboard_data, get_dashboard_collection_trend
from services.export_service import export_arrears
from models.user import log_action
from ui.constants import BACKGROUND, BarChart, FONT_BODY, FONT_BODY_ITALIC, FONT_MUTED, FONT_TITLE, FONT_TITLE_LG, PAD_MD, PAD_SM, PAD_XS, PRIMARY, SUCCESS, TEXT_PRIMARY, TEXT_SECONDARY, WARNING, ZEBRA_EVEN, ZEBRA_ODD


class DashboardTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=PAD_MD)
        self.app = app
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.columnconfigure(2, weight=1)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(3, weight=1)

        self.total_collected_var = tk.StringVar(value="KES 0.00")
        self.total_outstanding_var = tk.StringVar(value="KES 0.00")
        self.student_count_var = tk.StringVar(value="0")
        self.waived_count_var = tk.StringVar(value="0")

        cards = ttk.Frame(self)
        cards.grid(row=0, column=0, columnspan=4, sticky="nsew", padx=PAD_XS, pady=PAD_XS)
        for i in range(4):
            cards.columnconfigure(i, weight=1)

        self._create_stat_card(cards, "Total Collected (Current Term)",
                               self.total_collected_var, SUCCESS, 0)
        self._create_stat_card(cards, "Total Outstanding (All Students)",
                               self.total_outstanding_var, TEXT_PRIMARY, 1)
        self._create_stat_card(cards, "Active Students",
                               self.student_count_var, PRIMARY, 2)
        self._create_stat_card(cards, "Students with Fee Waiver",
                               self.waived_count_var, WARNING, 3)

        chart_wrapper = ttk.Frame(self)
        chart_wrapper.grid(row=1, column=0, columnspan=3, sticky="nsew", padx=PAD_XS, pady=(0, PAD_XS))
        chart_wrapper.rowconfigure(1, weight=1)
        chart_wrapper.columnconfigure(0, weight=1)

        ttk.Label(chart_wrapper, text="Fee Collection Trend", font=FONT_MUTED, foreground=TEXT_SECONDARY).grid(row=0, column=0, sticky="w")
        self.chart = BarChart(chart_wrapper)
        self.chart.grid(row=1, column=0, sticky="nsew")

        grade_frame = ttk.LabelFrame(self, text="Students per Grade", padding=PAD_SM)
        grade_frame.grid(row=2, column=0, columnspan=3, sticky="nsew", padx=PAD_XS, pady=(PAD_MD, PAD_XS))
        grade_frame.columnconfigure(0, weight=1)

        columns = ("grade", "count")
        self.grade_tree = ttk.Treeview(grade_frame, columns=columns, show="headings", height=6)
        self.grade_tree.heading("grade", text="Grade")
        self.grade_tree.heading("count", text="Count")
        self.grade_tree.column("grade", width=200, anchor="w")
        self.grade_tree.column("count", width=100, anchor="center")
        self.grade_tree.tag_configure("odd", background=ZEBRA_ODD)
        self.grade_tree.tag_configure("even", background=ZEBRA_EVEN)
        self.grade_tree.pack(fill="both", expand=True)

        defaulter_frame = ttk.LabelFrame(self, text="Top 5 Defaulters", padding=PAD_SM)
        defaulter_frame.grid(row=3, column=0, columnspan=3, sticky="nsew", padx=PAD_XS, pady=PAD_XS)
        defaulter_frame.columnconfigure(0, weight=1)

        btn_frame = ttk.Frame(defaulter_frame)
        btn_frame.pack(fill="x", pady=(0, PAD_XS))
        ttk.Button(btn_frame, text="Export Arrears Summary (Excel)",
                        command=self._export_arrears).pack(side="right")

        columns = ("name", "grade", "stream", "balance")
        self.defaulter_tree = ttk.Treeview(defaulter_frame, columns=columns, show="headings", height=6)
        self.defaulter_tree.heading("name", text="Student Name")
        self.defaulter_tree.heading("grade", text="Grade")
        self.defaulter_tree.heading("stream", text="Stream")
        self.defaulter_tree.heading("balance", text="Balance (KES)")
        self.defaulter_tree.column("name", width=220, anchor="w")
        self.defaulter_tree.column("grade", width=100, anchor="center")
        self.defaulter_tree.column("stream", width=100, anchor="center")
        self.defaulter_tree.column("balance", width=120, anchor="e")
        self.defaulter_tree.tag_configure("odd", background=ZEBRA_ODD)
        self.defaulter_tree.tag_configure("even", background=ZEBRA_EVEN)
        self.defaulter_tree.pack(fill="both", expand=True)

    def _create_stat_card(self, parent, title, value_var, accent_color, col):
        card = ttk.Frame(parent, style="Card.TFrame")
        card.grid(row=0, column=col, sticky="nsew", padx=PAD_XS)

        strip = tk.Canvas(card, width=4, bg=accent_color, highlightthickness=0)
        strip.pack(side="left", fill="y")

        ttk.Label(card, text=title, font=FONT_MUTED, foreground=TEXT_SECONDARY).pack(anchor="w")
        ttk.Label(card, textvariable=value_var, font=FONT_TITLE, foreground=TEXT_PRIMARY).pack(anchor="w")

    def _export_arrears(self):
        from services.report_service import get_arrears_data
        data = get_arrears_data(min_balance=0)
        path = export_arrears(data, self.app.receipts_dir)
        if path:
            messagebox.showinfo("Export complete", f"Saved to:\n{path}")
            log_action(self.app.current_username, "export_arrears",
                       f"Exported {len(data)} arrears records from Dashboard")

    def refresh(self):
        data = get_dashboard_data()
        self.total_collected_var.set(f"KES {data['total_collected_term']:,.2f}")
        self.total_outstanding_var.set(f"KES {data['total_outstanding']:,.2f}")
        total_students = sum(data["students_per_grade"].values())
        self.student_count_var.set(str(total_students))
        self.waived_count_var.set(str(data.get("waived_count", 0)))

        trend = get_dashboard_collection_trend()
        self.chart.update_data(trend)

        for row in self.grade_tree.get_children():
            self.grade_tree.delete(row)
        for idx, (grade, count) in enumerate(sorted(data["students_per_grade"].items())):
            tag = "even" if idx % 2 == 0 else "odd"
            self.grade_tree.insert("", "end", values=(grade, count), tags=(tag,))

        for row in self.defaulter_tree.get_children():
            self.defaulter_tree.delete(row)
        for idx, d in enumerate(data["top_defaulters"]):
            tag = "even" if idx % 2 == 0 else "odd"
            self.defaulter_tree.insert("", "end", values=(
                d["name"], d["grade"], d.get("stream", "") or "-", f"{d['balance']:,.2f}"), tags=(tag,))
