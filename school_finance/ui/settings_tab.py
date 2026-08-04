"""School information settings tab.

Single-school install: the form edits the one school_info row (id = 1).
The logo is browsed from the local disk and copied into assets/ so it
travels with the app install.
"""
import os
import shutil
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from db.database import BASE_DIR, DB_PATH, close_connection, logger
from models.school import get_school_info, update_school_info
from models.user import log_action
from ui.constants import FONT_MUTED, MUTED_FG, PAD_LG, PAD_MD, PAD_SM, PAD_XS

ASSETS_DIR = os.path.join(BASE_DIR, "assets")

LOGO_FILETYPES = [
    ("Image files", "*.png *.jpg *.jpeg *.gif *.bmp *.ico"),
    ("All files", "*.*"),
]


class SettingsTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=PAD_MD)
        self.app = app
        self._logo_image = None      # keep a reference to avoid GC
        self._logo_dest_path = ""    # path that will be saved to the DB
        self._build_ui()
        self.refresh()

    # ------------------------------------------------------------- UI ----
    def _build_ui(self):
        box = ttk.LabelFrame(self, text="School Information", padding=PAD_MD)
        box.pack(fill="both", expand=True)

        self._vars = {
            "school_name": tk.StringVar(),
            "address": tk.StringVar(),
            "phone": tk.StringVar(),
            "email": tk.StringVar(),
            "motto": tk.StringVar(),
        }

        row = 0
        for label, key in (
            ("School Name:", "school_name"),
            ("Address:", "address"),
            ("Phone:", "phone"),
            ("Email:", "email"),
            ("Motto:", "motto"),
        ):
            ttk.Label(box, text=label).grid(row=row, column=0, sticky="ne",
                                            pady=PAD_XS, padx=(0, PAD_MD))
            ttk.Entry(box, textvariable=self._vars[key],
                      width=50).grid(row=row, column=1, sticky="we",
                                     pady=PAD_XS)
            row += 1

        # Payment details (multi-line: paybill / till / bank info)
        ttk.Label(box, text="Payment Details:").grid(row=row, column=0,
                                                     sticky="ne", pady=PAD_XS,
                                                     padx=(0, PAD_MD))
        self.payment_text = tk.Text(box, width=50, height=5, wrap="word")
        self.payment_text.grid(row=row, column=1, sticky="we", pady=PAD_XS)
        ttk.Label(box, text="e.g. M-Pesa Paybill: 123456, Till: 987654,\n"
                            "Bank: XYZ Account 001...",
                  foreground=MUTED_FG).grid(row=row + 1, column=1, sticky="w",
                                          pady=(0, PAD_SM))
        box.columnconfigure(1, weight=1)
        row += 2

        # Logo
        logo_row = ttk.Frame(box)
        logo_row.grid(row=row, column=0, columnspan=2, sticky="we", pady=PAD_SM)
        ttk.Label(logo_row, text="Logo:").pack(side="left", padx=(0, PAD_MD))
        self.logo_preview = ttk.Label(logo_row, text="No logo selected",
                                      foreground=MUTED_FG)
        self.logo_preview.pack(side="left", padx=(0, PAD_MD))
        ttk.Button(logo_row, text="Browse for Logo...",
                   command=self._browse_logo).pack(side="left")
        ttk.Button(logo_row, text="Remove Logo",
                   command=self._remove_logo, style="Danger.TButton").pack(side="left", padx=(PAD_XS, 0))
        ttk.Label(box, text="Logo is copied into assets/ so it stays with "
                            "this install.",
                  foreground=MUTED_FG).grid(row=row + 1, column=0, columnspan=2,
                                          sticky="w", pady=(0, PAD_SM))
        row += 2

        ttk.Button(box, text="Save Settings",
                   command=self._save).grid(row=row, column=0, columnspan=2,
                                            pady=(PAD_MD, 0))

        restore_row = ttk.Frame(box)
        restore_row.grid(row=row + 1, column=0, columnspan=2, pady=(PAD_MD, 0))
        ttk.Button(restore_row, text="Restore Database from Backup...",
                   command=self._restore_database).pack(side="right")

    # ------------------------------------------------------- data ----
    def refresh(self):
        info = get_school_info()
        for key, var in self._vars.items():
            var.set(info.get(key) or "")
        self.payment_text.delete("1.0", "end")
        self.payment_text.insert("1.0", info.get("payment_details") or "")
        logo_path = info.get("logo_path") or ""
        self._logo_dest_path = logo_path
        self._show_logo_preview(logo_path)

    # ------------------------------------------------------- logo ----
    def _browse_logo(self):
        path = filedialog.askopenfilename(
            title="Select school logo image",
            filetypes=LOGO_FILETYPES)
        if not path:
            return

        ext = os.path.splitext(path)[1].lower() or ".png"
        dest_name = f"school_logo{ext}"
        dest_path = os.path.join(ASSETS_DIR, dest_name)

        try:
            os.makedirs(ASSETS_DIR, exist_ok=True)
            # Remove any previously stored logo with a different extension
            # so assets/ doesn't accumulate stale logo files.
            if os.path.isdir(ASSETS_DIR):
                for f in os.listdir(ASSETS_DIR):
                    if (f.startswith("school_logo")
                            and f != dest_name
                            and os.path.isfile(os.path.join(ASSETS_DIR, f))):
                        try:
                            os.remove(os.path.join(ASSETS_DIR, f))
                        except OSError:
                            pass
            shutil.copy2(path, dest_path)
        except OSError as e:
            messagebox.showerror("Logo copy failed",
                                 f"Could not copy logo into assets:\n{e}")
            return

        self._logo_dest_path = dest_path
        self._show_logo_preview(dest_path)

    def _remove_logo(self):
        self._logo_dest_path = ""
        self._show_logo_preview("")

    def _show_logo_preview(self, logo_path):
        """Show a small preview with Tk's native PhotoImage, or the file
        name when the format isn't natively supported (e.g. some JPEGs)."""
        self._logo_image = None
        if logo_path and os.path.isfile(logo_path):
            try:
                self._logo_image = tk.PhotoImage(file=logo_path)
                # Cap the preview at a reasonable size.
                self._logo_image = self._logo_image.subsample(
                    max(1, self._logo_image.width() // 96),
                    max(1, self._logo_image.height() // 48),
                )
                self.logo_preview.config(image=self._logo_image,
                                         text="")
                return
            except tk.TclError:
                pass
            self.logo_preview.config(image="", text=os.path.basename(logo_path))
        else:
            self.logo_preview.config(image="", text="No logo selected")

    # ------------------------------------------------------- save ----
    def _save(self):
        update_school_info(
            school_name=self._vars["school_name"].get(),
            address=self._vars["address"].get(),
            phone=self._vars["phone"].get(),
            email=self._vars["email"].get(),
            motto=self._vars["motto"].get(),
            logo_path=self._logo_dest_path,
            payment_details=self.payment_text.get("1.0", "end-1c"),
        )
        log_action(self.app.current_username, "update_school_info",
                   f"School info updated (school={self._vars['school_name'].get().strip() or '-'})")
        messagebox.showinfo("Settings saved",
                            "School information has been saved.")
        self.app.refresh_all()

    def _restore_database(self):
        path = filedialog.askopenfilename(
            title="Select database backup to restore",
            filetypes=[("SQLite database", "*.db *.sqlite"), ("All files", "*.*")])
        if not path:
            return

        if not messagebox.askyesno(
                "Confirm restore",
                "This will replace the current database with the selected backup.\n"
                "All current data will be lost.\n\nContinue?"):
            return

        try:
            import sqlite3
            conn = sqlite3.connect(path)
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            conn.close()
            if integrity != "ok":
                messagebox.showerror("Invalid backup",
                                     f"Backup integrity check failed: {integrity}")
                return
        except Exception as e:
            messagebox.showerror("Invalid backup", f"Failed to open backup: {e}")
            return

        try:
            close_connection()
            shutil.copy2(path, DB_PATH)
            self.app.refresh_all()
            messagebox.showinfo("Restore complete",
                                "Database has been restored from backup.\n"
                                "The application has been refreshed.")
            log_action(self.app.current_username, "restore_database",
                       f"Restored database from backup: {path}")
        except Exception as e:
            messagebox.showerror("Restore failed", str(e))
            logger.error("Database restore failed: %s", e)