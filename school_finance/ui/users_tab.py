"""Admin-managed user management tab.

Provides CRUD for user profiles (Name, Role, Signature, Username, Password)
plus admin-initiated password resets.  Only visible to users with the
``can_manage_users`` permission (i.e. Admin role).
"""
import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from db.database import BASE_DIR, get_connection, logger
from models.user import (
    create_user,
    list_users,
    get_user,
    update_user_profile,
    update_user_password,
    delete_user,
    log_action,
)
from ui.constants import (
    DANGER, FONT_BODY, FONT_BODY_ITALIC, FONT_HEADER_BOLD, FONT_MUTED,
    MUTED_FG, PAD_MD, PAD_SM, PAD_XS, PRIMARY, SUCCESS, SURFACE,
    ZEBRA_EVEN, ZEBRA_ODD,
)
from utils.validation import validate_password, validate_username, validate_role

ASSETS_DIR = os.path.join(BASE_DIR, "assets")
SIGNATURE_DIR = os.path.join(ASSETS_DIR, "signatures")

ROLE_OPTIONS = ("Admin", "Bursar", "Clerk")
IMAGE_FILETYPES = [
    ("Image files", "*.png *.jpg *.jpeg *.gif *.bmp *.ico"),
    ("All files", "*.*"),
]


class UsersTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=PAD_MD)
        self.app = app
        self._build_ui()
        self.refresh()

    # ------------------------------------------------------------- UI ----
    def _build_ui(self):
        top = ttk.Frame(self)
        top.pack(fill="x", pady=(0, PAD_SM))

        ttk.Label(top, text="Role filter:").pack(side="left", padx=(0, PAD_XS))
        self.role_filter_var = tk.StringVar(value="All")
        self.role_filter_combo = ttk.Combobox(
            top, textvariable=self.role_filter_var, state="readonly", width=12)
        self.role_filter_combo["values"] = ["All"] + list(ROLE_OPTIONS)
        self.role_filter_combo.pack(side="left", padx=(0, PAD_MD))
        self.role_filter_combo.bind(
            "<<ComboboxSelected>>", lambda e: self._apply_filter())

        btn_box = ttk.Frame(top)
        btn_box.pack(side="right")

        self._add_btn = ttk.Button(
            btn_box, text="Add User", command=self._open_add_dialog,
            style="Accent.TButton")
        self._add_btn.pack(side="left", padx=PAD_XS)
        self._edit_btn = ttk.Button(
            btn_box, text="Edit Selected", command=self._open_edit_dialog)
        self._edit_btn.pack(side="left", padx=PAD_XS)
        self._reset_pw_btn = ttk.Button(
            btn_box, text="Reset Password", command=self._open_reset_password)
        self._reset_pw_btn.pack(side="left", padx=PAD_XS)
        self._delete_btn = ttk.Button(
            btn_box, text="Delete Selected", command=self._delete_selected,
            style="Danger.TButton")
        self._delete_btn.pack(side="left", padx=PAD_XS)

        columns = ("id", "full_name", "username", "role", "status",
                   "last_login", "created_at")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=18)
        self.tree.heading("id", text="ID")
        self.tree.heading("full_name", text="Full Name")
        self.tree.heading("username", text="Username")
        self.tree.heading("role", text="Role")
        self.tree.heading("status", text="Status")
        self.tree.heading("last_login", text="Last Login")
        self.tree.heading("created_at", text="Created")

        self.tree.column("id", width=35, anchor="center")
        self.tree.column("full_name", width=160, anchor="w")
        self.tree.column("username", width=130, anchor="w")
        self.tree.column("role", width=90, anchor="center")
        self.tree.column("status", width=80, anchor="center")
        self.tree.column("last_login", width=130, anchor="center")
        self.tree.column("created_at", width=130, anchor="center")

        self.tree.tag_configure("odd", background=ZEBRA_EVEN)
        self.tree.tag_configure("even", background=ZEBRA_ODD)
        self.tree.tag_configure("inactive", foreground=MUTED_FG)
        self.tree.tag_configure("admin", background="#E3F2FD")
        self.tree.tag_configure("bursar", background="#E8F5E9")
        self.tree.tag_configure("clerk", background="#FFF3E0")

        self.tree.pack(fill="both", expand=True)

        summary = ttk.Label(self, text="", font=FONT_BODY_ITALIC,
                            foreground=MUTED_FG)
        summary.pack(anchor="w", pady=(PAD_XS, 0))
        self._summary = summary

    # ------------------------------------------------------- data ----
    def refresh(self):
        users = list_users(include_inactive=True)
        for row in self.tree.get_children():
            self.tree.delete(row)

        role_filter = self.role_filter_var.get()
        filtered = users
        if role_filter != "All":
            filtered = [u for u in users if u["role"] == role_filter]

        total = len(filtered)
        active = sum(1 for u in filtered if u["is_active"])
        inactive = total - active

        for idx, u in enumerate(filtered):
            tag = "even" if idx % 2 == 0 else "odd"
            role_tag = u["role"].lower()
            if not u["is_active"]:
                tag = tag + " inactive" if isinstance(tag, str) else tag
                status_text = "Inactive"
            else:
                status_text = "Active"

            tags_list = [tag, role_tag] if u["is_active"] else [tag, "inactive", role_tag]
            self.tree.insert("", "end", values=(
                u["id"],
                dict(u).get("full_name") or "-",
                u["username"],
                u["role"],
                status_text,
                u["last_login"] or "-",
                u["created_at"] or "-",
            ), tags=tuple(tags_list))

        self._summary.config(
            text=f"{total} user(s)  |  {active} active  |  {inactive} inactive")

    def _apply_filter(self):
        self.refresh()

    def get_selected_user_id(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("No selection", "Please select a user first.")
            return None
        return int(self.tree.item(sel[0])["values"][0])

    def _open_add_dialog(self):
        UserDialog(self, self.app, on_save=self._after_change)

    def _open_edit_dialog(self):
        user_id = self.get_selected_user_id()
        if user_id is None:
            return
        user = get_user(user_id)
        if user is None:
            messagebox.showerror("Error", "User not found in database.")
            return
        UserDialog(self, self.app, user=user, on_save=self._after_change)

    def _open_reset_password(self):
        user_id = self.get_selected_user_id()
        if user_id is None:
            return
        user = get_user(user_id)
        if user is None:
            return
        ResetPasswordDialog(self, self.app, user, on_save=self._after_change)

    def _delete_selected(self):
        user_id = self.get_selected_user_id()
        if user_id is None:
            return
        user = get_user(user_id)
        if user is None:
            return

        if user["username"] == self.app.current_username:
            messagebox.showwarning(
                "Cannot delete self",
                "You cannot delete your own account while logged in.")
            return

        confirm_text = (
            f"Delete user '{user['username']}'?\n\n"
            "This will deactivate their account (soft delete).\n"
            "The audit trail is preserved."
        )
        if not messagebox.askyesno("Confirm delete", confirm_text):
            return

        try:
            delete_user(user_id, soft=True)
            log_action(
                self.app.current_username, "delete_user",
                f"Deactivated user '{user['username']}' (id={user_id})")
            messagebox.showinfo("User deleted", f"User '{user['username']}' has been deactivated.")
        except ValueError as e:
            messagebox.showerror("Cannot delete", str(e))
            return
        except Exception as e:
            messagebox.showerror("Error", f"Failed to delete user:\n{e}")
            logger.error("Failed to delete user id=%s: %s", user_id, e)
            return

        self._after_change()

    def _after_change(self):
        self.refresh()
        self.app.refresh_all()


class UserDialog(tk.Toplevel):
    """Modal dialog for creating or editing a user."""

    def __init__(self, parent, app, user=None, on_save=None):
        super().__init__(parent)
        self.app = app
        self.user = user
        self.on_save = on_save
        self._logo_image = None
        self._signature_dest_path = ""
        self.title("Edit User" if user else "Add User")
        self.resizable(False, False)
        self.grab_set()

        frame = ttk.Frame(self, padding=PAD_MD)
        frame.pack()

        # Full Name
        ttk.Label(frame, text="Full Name:").grid(
            row=0, column=0, sticky="e", pady=PAD_XS)
        self.name_var = tk.StringVar(
            value=dict(user).get("full_name") if user else "")
        self.name_entry = ttk.Entry(frame, textvariable=self.name_var, width=30)
        self.name_entry.grid(row=0, column=1, pady=PAD_XS)

        # Username
        ttk.Label(frame, text="Username:").grid(
            row=1, column=0, sticky="e", pady=PAD_XS)
        self.username_var = tk.StringVar(
            value=user["username"] if user else "")
        self.username_entry = ttk.Entry(frame, textvariable=self.username_var, width=30)
        self.username_entry.grid(row=1, column=1, pady=PAD_XS)

        # Role
        ttk.Label(frame, text="Role:").grid(
            row=2, column=0, sticky="e", pady=PAD_XS)
        self.role_var = tk.StringVar(
            value=user["role"] if user else "Bursar")
        self.role_combo = ttk.Combobox(
            frame, textvariable=self.role_var, state="readonly",
            values=list(ROLE_OPTIONS), width=27)
        self.role_combo.grid(row=2, column=1, pady=PAD_XS)

        # Signature
        ttk.Label(frame, text="Signature:").grid(
            row=3, column=0, sticky="e", pady=PAD_XS)
        sig_row = ttk.Frame(frame)
        sig_row.grid(row=3, column=1, sticky="we", pady=PAD_XS)
        self.sig_preview = ttk.Label(
            sig_row, text="No signature selected", foreground=MUTED_FG)
        self.sig_preview.pack(side="left", padx=(0, PAD_XS))
        ttk.Button(sig_row, text="Browse...",
                   command=self._browse_signature).pack(side="left")

        # Password fields (Create mode only — Edit mode uses Reset Password)
        if not user:
            ttk.Label(frame, text="Password:").grid(
                row=4, column=0, sticky="e", pady=PAD_XS)
            self.password_var = tk.StringVar()
            self.password_entry = ttk.Entry(
                frame, textvariable=self.password_var, show="*", width=30)
            self.password_entry.grid(row=4, column=1, pady=PAD_XS)

            ttk.Label(frame, text="Confirm Password:").grid(
                row=5, column=0, sticky="e", pady=PAD_XS)
            self.confirm_var = tk.StringVar()
            self.confirm_entry = ttk.Entry(
                frame, textvariable=self.confirm_var, show="*", width=30)
            self.confirm_entry.grid(row=5, column=1, pady=PAD_XS)

            button_row = 6
        else:
            self.password_var = None
            self.password_entry = None
            self.confirm_var = None
            self.confirm_entry = None
            button_row = 4

        ttk.Button(frame, text="Save", command=self._save,
                   style="Accent.TButton").grid(
            row=button_row, column=0, columnspan=2,
            pady=(PAD_MD, 0))

        for w in (self.name_entry, self.username_entry, self.role_combo,
                  self.password_entry, self.confirm_entry):
            if w:
                w.bind("<Return>", lambda e: self._save())

        self._initial_sig_path = dict(user).get("signature_path", "") if user else ""
        self._signature_dest_path = self._initial_sig_path
        self._show_signature_preview(self._signature_dest_path)

        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() // 2) - (
            self.winfo_width() // 2)
        y = parent.winfo_rooty() + (parent.winfo_height() // 2) - (
            self.winfo_height() // 2)
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")

        self.name_entry.focus_set()

    def _browse_signature(self):
        path = filedialog.askopenfilename(
            title="Select signature image",
            filetypes=IMAGE_FILETYPES)
        if not path:
            return

        ext = os.path.splitext(path)[1].lower() or ".png"
        username = self.username_var.get().strip() or "signature"
        safe_name = "".join(
            c for c in username if c.isalnum() or c in "_-") or "signature"
        dest_name = f"{safe_name}{ext}"
        dest_path = os.path.join(SIGNATURE_DIR, dest_name)

        try:
            os.makedirs(SIGNATURE_DIR, exist_ok=True)
            # Remove any previously stored signature for this user with a
            # different extension to avoid stale files accumulating.
            for f in os.listdir(SIGNATURE_DIR):
                if f.startswith(safe_name) and os.path.isfile(
                        os.path.join(SIGNATURE_DIR, f)):
                    try:
                        os.remove(os.path.join(SIGNATURE_DIR, f))
                    except OSError:
                        pass
            import shutil
            shutil.copy2(path, dest_path)
        except OSError as e:
            messagebox.showerror("Image copy failed",
                                 f"Could not copy signature:\n{e}")
            return

        self._signature_dest_path = dest_path
        self._show_signature_preview(dest_path)

    def _show_signature_preview(self, sig_path):
        self._logo_image = None
        if sig_path and os.path.isfile(sig_path):
            try:
                self._logo_image = tk.PhotoImage(file=sig_path)
                self._logo_image = self._logo_image.subsample(
                    max(1, self._logo_image.width() // 96),
                    max(1, self._logo_image.height() // 48),
                )
                self.sig_preview.config(
                    image=self._logo_image, text="")
                return
            except tk.TclError:
                pass
            self.sig_preview.config(
                image="", text=os.path.basename(sig_path))
        else:
            self.sig_preview.config(
                image="", text="No signature selected")

    def _save(self):
        name = self.name_var.get().strip()
        username = self.username_var.get().strip()
        role = self.role_var.get()

        if not name:
            messagebox.showwarning("Missing info", "Full Name is required.")
            return
        try:
            username = validate_username(username)
            role = validate_role(role)
        except ValueError as e:
            messagebox.showwarning("Invalid input", str(e))
            return

        if not self.user:  # Create mode — require password
            password = self.password_var.get()
            confirm = self.confirm_var.get()
            if not password:
                messagebox.showwarning(
                    "Missing info", "Password is required for new users.")
                return
            if password != confirm:
                messagebox.showwarning("Mismatch", "Passwords do not match.")
                return
            try:
                validate_password(password)
            except ValueError as e:
                messagebox.showwarning("Weak password", str(e))
                return
            try:
                create_user(
                    full_name=name, username=username,
                    password=password, role=role,
                    signature_path=self._signature_dest_path,
                )
            except Exception as e:
                messagebox.showerror("Error", f"Could not create user:\n{e}")
                return
            messagebox.showinfo("User created",
                                f"User '{username}' has been created.")

        else:  # Edit mode — update profile (no password change here)
            try:
                update_user_profile(
                    self.user["id"], full_name=name,
                    username=username, role=role,
                    signature_path=self._signature_dest_path,
                )
            except ValueError as e:
                messagebox.showwarning("Error", str(e))
                return
            except Exception as e:
                messagebox.showerror("Error", f"Could not update user:\n{e}")
                return
            messagebox.showinfo("User updated",
                                f"User '{username}' has been updated.")

        if self.on_save:
            self.on_save()
        self.destroy()


class ResetPasswordDialog(tk.Toplevel):
    """Admin-initiated password reset for an existing user."""

    def __init__(self, parent, app, user, on_save=None):
        super().__init__(parent)
        self.app = app
        self.user = user
        self.on_save = on_save
        self.title(f"Reset Password — {user['username']}")
        self.resizable(False, False)
        self.grab_set()

        frame = ttk.Frame(self, padding=PAD_MD)
        frame.pack()

        ttk.Label(frame, text=f"Reset password for: {user['username']}",
                  font=FONT_HEADER_BOLD).grid(
            row=0, column=0, columnspan=2, pady=(0, PAD_MD))

        ttk.Label(frame, text="New Password:").grid(
            row=1, column=0, sticky="e", pady=PAD_XS)
        self.password_var = tk.StringVar()
        self.password_entry = ttk.Entry(
            frame, textvariable=self.password_var, show="*", width=30)
        self.password_entry.grid(row=1, column=1, pady=PAD_XS)

        ttk.Label(frame, text="Confirm New Password:").grid(
            row=2, column=0, sticky="e", pady=PAD_XS)
        self.confirm_var = tk.StringVar()
        self.confirm_entry = ttk.Entry(
            frame, textvariable=self.confirm_var, show="*", width=30)
        self.confirm_entry.grid(row=2, column=1, pady=PAD_XS)

        ttk.Button(frame, text="Reset Password", command=self._save,
                   style="Accent.TButton").grid(
            row=3, column=0, columnspan=2, pady=(PAD_MD, 0))

        self.password_entry.bind("<Return>", lambda e: self._save())
        self.confirm_entry.bind("<Return>", lambda e: self._save())

        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() // 2) - (
            self.winfo_width() // 2)
        y = parent.winfo_rooty() + (parent.winfo_height() // 2) - (
            self.winfo_height() // 2)
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")

        self.password_entry.focus_set()

    def _save(self):
        password = self.password_var.get()
        confirm = self.confirm_var.get()

        if not password:
            messagebox.showwarning("Missing info", "Please enter a new password.")
            return
        if password != confirm:
            messagebox.showwarning("Mismatch", "Passwords do not match.")
            return
        try:
            validate_password(password)
        except ValueError as e:
            messagebox.showwarning("Weak password", str(e))
            return

        try:
            update_user_password(self.user["id"], password)
        except Exception as e:
            messagebox.showerror("Error", f"Could not reset password:\n{e}")
            return

        messagebox.showinfo(
            "Password reset",
            f"Password has been reset for '{self.user['username']}'.")
        if self.on_save:
            self.on_save()
        self.destroy()
