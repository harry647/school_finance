import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill
import logging

from models.user import log_action
from services.import_service import import_balance_sheet
from ui.constants import FONT_MUTED, MUTED_FG, PAD_LG, PAD_MD, PAD_SM, PAD_XS, SUCCESS

logger = logging.getLogger("school_finance")


class ImportTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=PAD_MD)
        self.app = app
        self._build_ui()
        self.refresh()

    def refresh(self):
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")
        self.progress_var.set("")
        self.progress_bar.stop()
        self.import_btn.config(state="normal")

    def _build_ui(self):
        box = ttk.LabelFrame(self, text="Import Legacy Excel Balance Sheet",
                                     padding=PAD_MD)
        box.pack(fill="x")

        ttk.Label(
            box,
            text=("Import an existing balance-sheet workbook (e.g. "
                  "Grade 9 Balance Sheet.xlsx'). Each student's outstanding "
                  "balance per term is imported as a charge. Students already "
                  "in the system (matched by name + grade) are skipped, not "
                  "duplicated."),
            wraplength=560, foreground=MUTED_FG,
        ).pack(anchor="w", pady=(0, PAD_MD))

        ttk.Label(
            box,
            text=("Expected format: columns should include 'Name' (required), "
                  "'Admission No' (optional), and balance columns like "
                  "'Term I 2026', 'Term II 2026', 'Balance 2025', etc. "
                  "Download the template below for the exact format."),
            wraplength=560, foreground=SUCCESS,
        ).pack(anchor="w", pady=(0, PAD_MD))

        btn_row = ttk.Frame(box)
        btn_row.pack(fill="x", pady=(0, PAD_MD))

        self.import_btn = ttk.Button(btn_row, text="Choose Excel File & Import",
                        command=self._choose_and_import)
        self.import_btn.pack(side="left", padx=(0, PAD_SM))
        ttk.Button(btn_row, text="Download Import Template",
                        command=self._download_template).pack(side="left")

        row = ttk.Frame(box)
        row.pack(fill="x", pady=PAD_XS)
        ttk.Label(row, text="Grade for this file (optional — auto-detected "
                             "from filename if left blank):").pack(side="left")
        self.grade_var = tk.StringVar()
        ttk.Entry(row, textvariable=self.grade_var, width=15).pack(side="left",
                                                                     padx=PAD_SM)

        self.progress_var = tk.StringVar(value="")
        ttk.Label(box, textvariable=self.progress_var,
                       foreground=MUTED_FG).pack(anchor="w", pady=(PAD_SM, 0))

        self.progress_bar = ttk.Progressbar(box, mode="indeterminate")
        self.progress_bar.pack(fill="x", pady=(PAD_XS, 0))

        self.log_text = tk.Text(self, height=14, state="disabled",
                                        wrap="word")
        self.log_text.pack(fill="both", expand=True, pady=(PAD_MD, 0))

    def _log(self, message):
        self.log_text.config(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _download_template(self):
        try:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Import Template"

            header_font = Font(bold=True, color="FFFFFF")
            header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
            header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

            headers = ["Name", "Admission No", "Term I 2026", "Term II 2026", "Term III 2026", "Balance 2025", "Remarks"]
            ws.append(headers)

            for cell in ws[1]:
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = header_align

            sample_data = [
                ["John Ochieng", "GVSS/2026/001", 15000, 0, 0, 5000, "Parent promised payment"],
                ["Mary Wanjiku", "GVSS/2026/002", 0, 18000, 0, 0, ""],
                ["Peter Njoroge", "GVSS/2026/003", 25000, 25000, 25000, 10000, ""],
            ]
            for row_data in sample_data:
                ws.append(row_data)

            ws.column_dimensions["A"].width = 22
            ws.column_dimensions["B"].width = 18
            ws.column_dimensions["C"].width = 14
            ws.column_dimensions["D"].width = 14
            ws.column_dimensions["E"].width = 14
            ws.column_dimensions["F"].width = 14
            ws.column_dimensions["G"].width = 28

            notes = wb.create_sheet("Format Notes")
            notes.column_dimensions["A"].width = 80
            notes.append(["IMPORT TEMPLATE FORMAT NOTES"])
            notes["A1"].font = Font(bold=True, size=14)
            notes.append([])
            notes.append(["REQUIRED COLUMNS:"])
            notes["A3"].font = Font(bold=True)
            notes.append(["• Name - Student full name (required)"])
            notes.append(["• Admission No - Student admission number (optional)"])
            notes.append([])
            notes.append(["BALANCE COLUMNS (optional but recommended):"])
            notes["A7"].font = Font(bold=True)
            notes.append(["• Use format: Term I 2026, Term II 2026, Term III 2026, etc."])
            notes.append(["• Or use: Balance 2025, Balance 2026 for opening balances"])
            notes.append(["• Any column with a year (2024, 2025, 2026, etc.) is detected"])
            notes.append([])
            notes.append(["OTHER COLUMNS:"])
            notes["A12"].font = Font(bold=True)
            notes.append(["• Remarks - Any notes about the student (optional)"])
            notes.append([])
            notes.append(["IMPORT RULES:"])
            notes["A15"].font = Font(bold=True)
            notes.append(["• Students with same Name + Grade are skipped (not duplicated)"])
            notes.append(["• Only positive numeric values are imported as charges"])
            notes.append(["• Column headers are case-insensitive"])
            notes.append(["• Save as .xlsx, .xlsm, or .csv before importing"])

            default_dir = self.app.receipts_dir
            path = os.path.join(default_dir, "import_template.xlsx")
            wb.save(path)

            messagebox.showinfo("Template Downloaded",
                                f"Template saved to:\n{path}\n\n"
                                "Fill in your student data and import it using the button above.")
            logger.info("Import template downloaded to: %s", path)
            self._log(f"Template downloaded to: {path}")
        except Exception as e:
            logger.error("Failed to create template: %s", e, exc_info=True)
            messagebox.showerror("Error", f"Failed to create template: {e}")

    def _choose_and_import(self):
        file_path = filedialog.askopenfilename(
            title="Select balance sheet Excel file",
            filetypes=[("Excel files", "*.xlsx *.xlsm"),
                        ("CSV files", "*.csv")])
        if not file_path:
            return
        self.import_btn.config(state="disabled")
        self.progress_var.set("Importing...")
        self.progress_bar.start(10)
        self.update_idletasks()
        try:
            result = import_balance_sheet(
                file_path, default_grade=self.grade_var.get().strip()
                or None)
        except Exception as e:
            logger.error("Import failed for %s: %s", file_path, e, exc_info=True)
            messagebox.showerror("Import failed", str(e))
            self._log(f"FAILED: {file_path} -> {e}")
        else:
            msg = (f"Imported '{file_path}'\n"
                   f"  Grade: {result['grade']}\n"
                   f"  New students added: {result['students_added']}\n"
                   f"  Existing students skipped: {result['students_skipped']}\n"
                   f"  Charges recorded: {result['charges_added']}")
            self._log(msg)
            log_action(self.app.current_username, "import_excel",
                       msg.replace("\n", " | "))
            messagebox.showinfo("Import complete",
                                    f"Added {result['students_added']} students, "
                                    f"recorded {result['charges_added']} charges.")
            self.app.refresh_all()
        finally:
            self.progress_bar.stop()
            self.progress_var.set("")
            self.import_btn.config(state="normal")
