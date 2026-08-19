import json
import os
import shutil
import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from db.database import DATA_DIR, DB_PATH, BASE_DIR, logger
from models.user import ROLE_PERMISSIONS, log_action
from services.config import get_setting, set_setting as save_setting
from services.export_service import export_students, export_payments
from ui.constants import BACKGROUND, BORDER, DANGER, FONT_HEADER_BOLD, FONT_MUTED, MUTED_FG, PAD_LG, PAD_MD, PAD_SM, PAD_XS, PRIMARY, SUCCESS, SURFACE, apply_theme
from ui.students_tab import StudentsTab
from ui.payments_tab import PaymentsTab
from ui.statements_tab import StatementsTab
from ui.import_tab import ImportTab
from ui.settings_tab import SettingsTab
from ui.dashboard_tab import DashboardTab
from ui.arrears_tab import ArrearsTab
from ui.income_tab import IncomeTab
from ui.fees_tab import FeesTab
from ui.users_tab import UsersTab
from ui.waivers_tab import WaiversTab
from ui.bulk_payments_tab import BulkPaymentsTab
from ui.credits_tab import CreditsTab

GEOMETRY_FILE = os.path.join(BASE_DIR, "window_geometry.json")


class MainWindow(tk.Toplevel):
    def __init__(self, parent, current_user):
        super().__init__(parent)
        self.current_username = current_user["username"]
        self.current_role = current_user["role"]
        self.current_user_id = current_user["id"]
        self.receipts_dir = os.path.join(BASE_DIR, "receipts")
        self.statements_dir = os.path.join(BASE_DIR, "statements")
        self.backups_dir = os.path.join(BASE_DIR, "backups")
        self._permissions = ROLE_PERMISSIONS.get(self.current_role, set())
        self._auto_backup_enabled = True
        self._logout_requested = False

        self._setup_dpi_awareness()
        apply_theme()

        self.title("School Finance System")
        self._load_geometry()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_menu()
        self._build_status_bar()
        self._build_tabs()
        self._bind_shortcuts()
        self._verify_latest_backup()
        self.update_status_bar()

    def _setup_dpi_awareness(self):
        try:
            import ctypes
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except AttributeError:
                ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

        apply_theme()

    def _bind_shortcuts(self):
        self.bind_all("<Control-s>", lambda e: self._save_current())
        self.bind_all("<Control-r>", lambda e: self.refresh_all())
        self.bind_all("<Control-b>", lambda e: self._backup_now())
        self.bind_all("<F5>", lambda e: self.refresh_all())
        self.bind_all("<Escape>", lambda e: self.destroy())

    def _save_current(self):
        pass

    def has_permission(self, permission):
        return permission in self._permissions

    def _on_close(self):
        if self._auto_backup_enabled:
            self._auto_backup()
        self._save_geometry()
        self.destroy()
        self.quit()

    def logout(self):
        log_action(self.current_username, "logout", "User logged out")
        self._logout_requested = True
        self._on_close()

    def _load_geometry(self):
        try:
            with open(GEOMETRY_FILE, "r") as f:
                data = json.load(f)
            geom = data.get("geometry")
            if geom:
                self.geometry(geom)
            min_size = data.get("min_size", [980, 620])
            self.minsize(min_size[0], min_size[1])
        except Exception:
            self.minsize(980, 620)

    def _save_geometry(self):
        try:
            geom = self.geometry()
            mins = self.minsize()
            data = {
                "geometry": geom,
                "min_size": [mins[0], mins[1]]
            }
            with open(GEOMETRY_FILE, "w") as f:
                json.dump(data, f)
        except Exception:
            pass

    def _auto_backup(self):
        os.makedirs(self.backups_dir, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"school_finance_backup_{timestamp}.db"
        dest = os.path.join(self.backups_dir, default_name)
        try:
            shutil.copy2(DB_PATH, dest)
            conn = __import__("sqlite3").connect(dest)
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            conn.close()
            if integrity == "ok":
                logger.info("Auto-backup created and verified: %s", dest)
            else:
                logger.error("Auto-backup integrity check failed: %s", integrity)
                os.remove(dest)
        except Exception as e:
            logger.error("Auto-backup failed: %s", e)

    def _verify_latest_backup(self):
        if not os.path.isdir(self.backups_dir):
            return
        backups = sorted(
            [f for f in os.listdir(self.backups_dir) if f.endswith(".db")],
            reverse=True)
        if not backups:
            return
        latest = os.path.join(self.backups_dir, backups[0])
        try:
            conn = __import__("sqlite3").connect(latest)
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            conn.close()
            if integrity == "ok":
                logger.info("Latest backup integrity verified: %s", latest)
            else:
                logger.warning("Latest backup integrity check failed: %s", integrity)
        except Exception as e:
            logger.error("Latest backup verification failed: %s", e)

    def _build_menu(self):
        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=0)
        if self.has_permission("can_backup"):
            file_menu.add_command(label="Backup Database Now...",
                                  command=self._backup_now)
        file_menu.add_command(label="Logout", command=self.logout)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)
        menubar.add_cascade(label="File", menu=file_menu)

        settings_menu = tk.Menu(menubar, tearoff=0)
        settings_menu.add_command(label="Settings...",
                                    command=self._open_settings)
        settings_menu.add_separator()
        if self.has_permission("can_manage_users"):
            settings_menu.add_command(label="Manage Users...",
                                      command=self._open_users_tab)
        settings_menu.add_command(label="Change My Username/Password...",
                                  command=self._open_self_service)
        menubar.add_cascade(label="Settings", menu=settings_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="View Audit Log...",
                                command=self._view_audit_log)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.config(menu=menubar)

    def _open_settings(self):
        SettingsDialog(self)

    def _open_users_tab(self):
        if self.users_tab is not None:
            self.notebook.select(self.notebook.index(self.users_tab))

    def _open_self_service(self):
        ChangeMySettingsDialog(self)

    def _view_audit_log(self):
        AuditLogDialog(self)

    def _build_status_bar(self):
        bar = ttk.Frame(self, padding=(PAD_SM, PAD_XS))
        bar.pack(side="bottom", fill="x")

        self.db_canvas = tk.Canvas(bar, width=10, height=10, highlightthickness=0, bg=BACKGROUND)
        self.db_canvas.pack(side="left", padx=(0, PAD_XS))
        self.db_indicator = self.db_canvas.create_oval(1, 1, 9, 9, fill=SUCCESS, outline=SUCCESS)

        role_badge = tk.Label(bar, text=self.current_role, bg=PRIMARY, fg=SURFACE,
                              font=FONT_MUTED, padx=6, pady=1)
        role_badge.pack(side="left", padx=(0, PAD_SM))

        ttk.Label(bar, text=f"Logged in as: {self.current_username}").pack(side="left")
        self.status_today_var = tk.StringVar(value="Today: KES 0.00")
        ttk.Label(bar, textvariable=self.status_today_var).pack(side="left", padx=(PAD_MD, 0))
        self.status_term_var = tk.StringVar(value="Term outstanding: KES 0.00")
        ttk.Label(bar, textvariable=self.status_term_var).pack(side="left", padx=(PAD_MD, 0))
        self.status_receivables_var = tk.StringVar(value="Total receivables: KES 0.00")
        ttk.Label(bar, textvariable=self.status_receivables_var).pack(side="left", padx=(PAD_MD, 0))
        self.status_waived_var = tk.StringVar(value="Waived: 0")
        ttk.Label(bar, textvariable=self.status_waived_var).pack(side="left", padx=(PAD_MD, 0))
        ttk.Label(bar, text=f"Database: {DB_PATH}").pack(side="right")

    def update_status_bar(self):
        try:
            from services.report_service import get_dashboard_data
            data = get_dashboard_data()
            today_str = datetime.datetime.now().strftime("%Y-%m-%d")
            conn = __import__("sqlite3").connect(DB_PATH)
            conn.row_factory = __import__("sqlite3").Row
            today_total = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) AS total FROM payments "
                "WHERE date_paid LIKE ? AND voided = 0",
                (f"{today_str}%",),
            ).fetchone()["total"]
            conn.close()
            self.status_today_var.set(f"Today: KES {today_total:,.2f}")
            self.status_term_var.set(f"Term outstanding: KES {data['total_outstanding']:,.2f}")
            self.status_receivables_var.set(f"Total receivables: KES {data.get('total_receivables', 0):,.2f}")
            self.status_waived_var.set(f"Waived: {data.get('waived_count', 0)}")
        except Exception:
            pass

    def _build_tabs(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=PAD_MD, pady=PAD_MD)

        try:
            self.dashboard_tab = DashboardTab(self.notebook, self)
        except Exception as e:
            logger.error("Failed to create DashboardTab: %s", e, exc_info=True)
            raise
        try:
            self.students_tab = StudentsTab(self.notebook, self)
        except Exception as e:
            logger.error("Failed to create StudentsTab: %s", e, exc_info=True)
            raise
        try:
            self.payments_tab = PaymentsTab(self.notebook, self)
        except Exception as e:
            logger.error("Failed to create PaymentsTab: %s", e, exc_info=True)
            raise
        try:
            self.statements_tab = StatementsTab(self.notebook, self)
        except Exception as e:
            logger.error("Failed to create StatementsTab: %s", e, exc_info=True)
            raise
        try:
            self.arrears_tab = ArrearsTab(self.notebook, self)
        except Exception as e:
            logger.error("Failed to create ArrearsTab: %s", e, exc_info=True)
            raise
        try:
            self.income_tab = IncomeTab(self.notebook, self)
        except Exception as e:
            logger.error("Failed to create IncomeTab: %s", e, exc_info=True)
            raise
        try:
            self.fees_tab = FeesTab(self.notebook, self)
        except Exception as e:
            logger.error("Failed to create FeesTab: %s", e, exc_info=True)
            raise
        try:
            self.import_tab = ImportTab(self.notebook, self)
        except Exception as e:
            logger.error("Failed to create ImportTab: %s", e, exc_info=True)
            raise
        try:
            self.settings_tab = SettingsTab(self.notebook, self)
        except Exception as e:
            logger.error("Failed to create SettingsTab: %s", e, exc_info=True)
            raise
        try:
            self.users_tab = UsersTab(self.notebook, self) \
                if self.has_permission("can_manage_users") else None
        except Exception as e:
            logger.error("Failed to create UsersTab: %s", e, exc_info=True)
            raise
        try:
            self.waivers_tab = WaiversTab(self.notebook, self) \
                if self.has_permission("can_manage_waivers") else None
        except Exception as e:
            logger.error("Failed to create WaiversTab: %s", e, exc_info=True)
            raise
        try:
            self.bulk_payments_tab = BulkPaymentsTab(self.notebook, self) \
                if self.has_permission("can_record_payment") else None
        except Exception as e:
            logger.error("Failed to create BulkPaymentsTab: %s", e, exc_info=True)
            raise
        try:
            self.credits_tab = CreditsTab(self.notebook, self) \
                if self.has_permission("can_manage_credits") else None
        except Exception as e:
            logger.error("Failed to create CreditsTab: %s", e, exc_info=True)
            raise

        self.notebook.add(self.dashboard_tab, text="Dashboard")
        self.notebook.add(self.students_tab, text="Students")
        self.notebook.add(self.payments_tab, text="Payments")
        self.notebook.add(self.statements_tab, text="Fee Statements")
        self.notebook.add(self.arrears_tab, text="Arrears")
        self.notebook.add(self.income_tab, text="Income Reports")
        self.notebook.add(self.fees_tab, text="Fee Structure")
        if self.has_permission("can_import"):
            self.notebook.add(self.import_tab, text="Import Legacy Excel")
        if self.users_tab is not None:
            self.notebook.add(self.users_tab, text="Users")
        if self.waivers_tab is not None:
            self.notebook.add(self.waivers_tab, text="Partial Waivers")
        if self.bulk_payments_tab is not None:
            self.notebook.add(self.bulk_payments_tab, text="Bulk Payments")
        if self.credits_tab is not None:
            self.notebook.add(self.credits_tab, text="Student Credits")
        self.notebook.add(self.settings_tab, text="Settings")

    def refresh_all(self):
        self.dashboard_tab.refresh()
        self.students_tab.refresh()
        self.payments_tab.refresh()
        self.statements_tab.refresh()
        self.arrears_tab.refresh()
        self.income_tab.refresh()
        self.fees_tab.refresh()
        if self.users_tab is not None:
            self.users_tab.refresh()
        if self.waivers_tab is not None:
            self.waivers_tab.refresh()
        if self.bulk_payments_tab is not None:
            self.bulk_payments_tab.refresh()
        if self.credits_tab is not None:
            self.credits_tab.refresh()
        self.settings_tab.refresh()
        self.update_status_bar()

    def _backup_now(self):
        os.makedirs(self.backups_dir, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"school_finance_backup_{timestamp}.db"
        dest = filedialog.asksaveasfilename(
            title="Save backup as",
            initialdir=self.backups_dir,
            initialfile=default_name,
            defaultextension=".db",
            filetypes=[("SQLite database", "*.db")])
        if not dest:
            return
        try:
            shutil.copy2(DB_PATH, dest)
            conn = __import__("sqlite3").connect(dest)
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            conn.close()
            if integrity == "ok":
                messagebox.showinfo("Backup complete",
                                      f"Backup saved to:\n{dest}\n"
                                      "Integrity verified.")
                logger.info("Backup created and verified: %s", dest)
            else:
                os.remove(dest)
                messagebox.showerror("Backup failed",
                                       f"Integrity check failed: {integrity}")
                logger.error("Backup integrity check failed: %s", integrity)
        except Exception as e:
            messagebox.showerror("Backup failed", str(e))
            logger.error("Backup failed: %s", e)


class SettingsDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Settings")
        self.resizable(False, False)
        self.grab_set()
        self._build_ui()
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() // 2) - (
            self.winfo_width() // 2)
        y = parent.winfo_y() + (parent.winfo_height() // 2) - (
            self.winfo_height() // 2)
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def _build_ui(self):
        frame = ttk.Frame(self, padding=PAD_LG)
        frame.pack()

        ttk.Label(frame, text="School Name:").grid(row=0, column=0,
                                                     sticky="e", pady=PAD_XS)
        self.school_name_var = tk.StringVar(
            value=get_setting("school_name"))
        ttk.Entry(frame, textvariable=self.school_name_var,
                  width=30).grid(row=0, column=1, pady=PAD_XS)

        ttk.Label(frame, text="Currency Symbol:").grid(row=1, column=0,
                                                           sticky="e", pady=PAD_XS)
        self.currency_var = tk.StringVar(value=get_setting("currency_symbol"))
        ttk.Entry(frame, textvariable=self.currency_var, width=10
                  ).grid(row=1, column=1, sticky="w", pady=PAD_XS)

        ttk.Label(frame, text="Backup Retention Count:").grid(
            row=2, column=0, sticky="e", pady=PAD_XS)
        self.retention_var = tk.StringVar(
            value=str(get_setting("backup_retention_count")))
        ttk.Entry(frame, textvariable=self.retention_var,
                  width=10).grid(row=2, column=1, sticky="w", pady=PAD_XS)

        ttk.Label(frame, text="Receipt Footer:").grid(row=3, column=0,
                                                          sticky="e", pady=PAD_XS)
        self.footer_var = tk.StringVar(value=get_setting("receipt_footer"))
        ttk.Entry(frame, textvariable=self.footer_var,
                  width=30).grid(row=3, column=1, pady=PAD_XS)

        ttk.Button(frame, text="Save", command=self._save, style="Accent.TButton").grid(
            row=4, column=0, columnspan=2, pady=(PAD_MD, 0))

    def _save(self):
        try:
            retention = int(self.retention_var.get())
            if retention < 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Invalid input",
                                     "Retention count must be a positive number.")
            return
        save_setting("school_name", self.school_name_var.get().strip())
        save_setting("currency_symbol", self.currency_var.get().strip())
        save_setting("backup_retention_count", retention)
        save_setting("receipt_footer", self.footer_var.get().strip())
        messagebox.showinfo("Settings saved", "Settings have been saved.")
        self.destroy()


class AuditLogDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Audit Log")
        self.geometry("700x400")
        self.grab_set()
        self._build_ui()

    def _build_ui(self):
        frame = ttk.Frame(self, padding=PAD_SM)
        frame.pack(fill="both", expand=True)

        columns = ("timestamp", "username", "action", "detail")
        self.tree = ttk.Treeview(frame, columns=columns, show="headings",
                                     height=20)
        self.tree.heading("timestamp", text="Timestamp")
        self.tree.heading("username", text="Username")
        self.tree.heading("action", text="Action")
        self.tree.heading("detail", text="Detail")
        self.tree.column("timestamp", width=140)
        self.tree.column("username", width=100)
        self.tree.column("action", width=120)
        self.tree.column("detail", width=300)

        scrollbar = ttk.Scrollbar(frame, orient="vertical",
                                      command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self._load_data()

    def _load_data(self):
        from db.database import get_connection
        conn = get_connection()
        for row in self.tree.get_children():
            self.tree.delete(row)
        rows = conn.execute(
            "SELECT username, action, detail, timestamp FROM audit_log "
            "ORDER BY timestamp DESC LIMIT 500"
        ).fetchall()
        for r in rows:
            self.tree.insert("", "end", values=(
                r["timestamp"], r["username"] or "-", r["action"],
                r["detail"] or ""))


class ChangeMySettingsDialog(tk.Toplevel):
    """Self-service dialog: lets any authenticated user update their own
    username and/or password.

    Requires the current password to be verified before any change is
    applied — prevents an unattended session from escalating privileges.
    """

    def __init__(self, parent):
        super().__init__(parent)
        self.app = parent
        self.title("Change My Settings")
        self.resizable(False, False)
        self.grab_set()

        frame = ttk.Frame(self, padding=PAD_MD)
        frame.pack()

        ttk.Label(frame, text="Change Username / Password",
                  font=FONT_HEADER_BOLD).grid(
            row=0, column=0, columnspan=2, pady=(0, PAD_MD))

        ttk.Label(frame, text="Current Password:").grid(
            row=1, column=0, sticky="e", pady=PAD_XS)
        self.current_pw_var = tk.StringVar()
        self.current_pw_entry = ttk.Entry(
            frame, textvariable=self.current_pw_var, show="*", width=30)
        self.current_pw_entry.grid(row=1, column=1, pady=PAD_XS)

        ttk.Label(frame, text="New Username:").grid(
            row=2, column=0, sticky="e", pady=PAD_XS)
        self.new_username_var = tk.StringVar(
            value=self.app.current_username)
        self.new_username_entry = ttk.Entry(
            frame, textvariable=self.new_username_var, width=30)
        self.new_username_entry.grid(row=2, column=1, pady=PAD_XS)

        ttk.Label(frame, text="New Password:").grid(
            row=3, column=0, sticky="e", pady=PAD_XS)
        self.new_pw_var = tk.StringVar()
        self.new_pw_entry = ttk.Entry(
            frame, textvariable=self.new_pw_var, show="*", width=30)
        self.new_pw_entry.grid(row=3, column=1, pady=PAD_XS)

        ttk.Label(frame, text="Confirm New Password:").grid(
            row=4, column=0, sticky="e", pady=PAD_XS)
        self.confirm_pw_var = tk.StringVar()
        self.confirm_pw_entry = ttk.Entry(
            frame, textvariable=self.confirm_pw_var, show="*", width=30)
        self.confirm_pw_entry.grid(row=4, column=1, pady=PAD_XS)

        ttk.Label(frame, text="(Leave password blank to keep it unchanged)",
                  font=FONT_MUTED, foreground=MUTED_FG).grid(
            row=5, column=0, columnspan=2, pady=(0, PAD_MD))

        ttk.Button(frame, text="Save Changes", command=self._save,
                   style="Accent.TButton").grid(
            row=6, column=0, columnspan=2, pady=(0, PAD_MD))

        for w in (self.current_pw_entry, self.new_username_entry,
                  self.new_pw_entry, self.confirm_pw_entry):
            w.bind("<Return>", lambda e: self._save())

        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() // 2) - (
            self.winfo_width() // 2)
        y = parent.winfo_rooty() + (parent.winfo_height() // 2) - (
            self.winfo_height() // 2)
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")

        self.current_pw_entry.focus_set()

    def _save(self):
        current_pw = self.current_pw_var.get()
        new_username = self.new_username_var.get().strip()
        new_password = self.new_pw_var.get()

        if not current_pw:
            messagebox.showwarning("Missing info",
                                  "Current password is required.")
            return
        if not new_username:
            messagebox.showwarning("Missing info", "New username is required.")
            return

        if new_password:
            if new_password != self.confirm_pw_var.get():
                messagebox.showwarning("Mismatch",
                                       "New passwords do not match.")
                return

        try:
            from models.user import update_own_settings
            update_own_settings(
                user_id=self.app.current_user_id,
                new_username=new_username,
                current_password=current_pw,
                new_password=new_password or None,
            )
        except ValueError as e:
            messagebox.showwarning("Error", str(e))
            return
        except Exception as e:
            messagebox.showerror("Error", f"Could not update settings:\n{e}")
            return

        if new_password:
            messagebox.showinfo(
                "Settings updated",
                "Your username and password have been updated. "
                "You will need to log in again.")
        else:
            messagebox.showinfo(
                "Settings updated",
                "Your username has been updated. "
                "You will need to log in again.")
        self.destroy()
