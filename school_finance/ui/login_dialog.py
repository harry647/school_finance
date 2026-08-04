import tkinter as tk
from tkinter import ttk, messagebox

from models.user import any_users_exist, create_user, authenticate
from ui.constants import FONT_BODY, FONT_BODY_ITALIC, FONT_MUTED, FONT_TITLE, MUTED_FG, PAD_LG, PAD_MD, PAD_SM, PAD_XS


class LoginDialog(tk.Toplevel):
    """Modal login dialog. On first run, lets you create the initial admin
    account instead of logging in."""

    def __init__(self, parent):
        super().__init__(parent)
        self.result_user = None
        self.account_just_created = False
        self.first_run = not any_users_exist()

        self.title("Create Admin Account" if self.first_run else "Login")
        self.resizable(True, True)
        self.minsize(420, 320)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        container = ttk.Frame(self, padding=PAD_LG)
        container.pack(fill="both", expand=True)

        if self.first_run:
            header_text = "Welcome to School Finance System"
            sub_text = "Create the first administrator account to get started."
        else:
            header_text = "School Finance System"
            sub_text = "Enter your credentials to continue."

        header = ttk.Label(container, text=header_text, font=FONT_TITLE)
        header.pack(pady=(0, PAD_XS))

        sub = ttk.Label(container, text=sub_text, font=FONT_MUTED)
        sub.pack(pady=(0, PAD_MD))

        form = ttk.Frame(container)
        form.pack()

        row = 0

        if self.first_run:
            ttk.Label(form, text="Full Name:", font=FONT_BODY).grid(
                row=row, column=0, sticky="e", pady=(0, PAD_MD), padx=(0, PAD_MD))
            self.full_name_var = tk.StringVar()
            self.full_name_entry = ttk.Entry(
                form, textvariable=self.full_name_var, width=30, font=FONT_BODY)
            self.full_name_entry.grid(row=row, column=1, pady=(0, PAD_MD))
            row += 1

        ttk.Label(form, text="Username:", font=FONT_BODY).grid(
            row=row, column=0, sticky="e", pady=(0, PAD_MD), padx=(0, PAD_MD))
        self.username_var = tk.StringVar()
        self.username_entry = ttk.Entry(
            form, textvariable=self.username_var, width=30, font=FONT_BODY)
        self.username_entry.grid(row=row, column=1, pady=(0, PAD_MD))
        row += 1

        ttk.Label(form, text="Password:", font=FONT_BODY).grid(
            row=row, column=0, sticky="e", pady=(0, PAD_MD), padx=(0, PAD_MD))
        self.password_var = tk.StringVar()
        self.password_entry = ttk.Entry(
            form, textvariable=self.password_var, show="*", width=30, font=FONT_BODY)
        self.password_entry.grid(row=row, column=1, pady=(0, PAD_MD))
        row += 1

        if self.first_run:
            ttk.Label(form, text="Confirm Password:", font=FONT_BODY).grid(
                row=row, column=0, sticky="e", pady=(0, PAD_MD), padx=(0, PAD_MD))
            self.confirm_var = tk.StringVar()
            self.confirm_entry = ttk.Entry(
                form, textvariable=self.confirm_var, show="*", width=30, font=FONT_BODY)
            self.confirm_entry.grid(row=row, column=1, pady=(0, PAD_MD))
            row += 1

        btn_text = "Create Account" if self.first_run else "Login"
        self.submit_btn = ttk.Button(
            container, text=btn_text, command=self._submit,
            width=28, style="Accent.TButton")
        self.submit_btn.pack(pady=(PAD_MD, 0))

        for w in (self.username_entry, self.password_entry):
            w.bind("<Return>", lambda e: self._submit())
        if self.first_run:
            self.confirm_entry.bind("<Return>", lambda e: self._submit())

        self.update_idletasks()
        self.geometry("480x380" if self.first_run else "420x300")
        x = parent.winfo_x() + (parent.winfo_width() // 2) - (self.winfo_width() // 2)
        y = parent.winfo_y() + (parent.winfo_height() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{max(x,0)}+{max(y,0)}")

        self.username_entry.focus_set()

    def _submit(self):
        username = self.username_var.get().strip()
        password = self.password_var.get()

        if not username or not password:
            messagebox.showwarning("Missing info", "Please fill in all fields.")
            return

        if self.first_run:
            full_name = self.full_name_var.get().strip()
            if not full_name:
                messagebox.showwarning("Missing info", "Please enter your full name.")
                return
            confirm = self.confirm_var.get()
            if password != confirm:
                messagebox.showwarning("Mismatch", "Passwords do not match.")
                return
            try:
                if len(password) < 8:
                    raise ValueError(
                        "Password must be at least 8 characters. "
                        "Use a mix of letters, numbers, and symbols.")
                from utils.validation import validate_password
                validate_password(password)
            except ValueError as e:
                messagebox.showwarning("Weak password", str(e))
                return
            try:
                create_user(full_name, username, password, role="Admin")
            except Exception as e:
                messagebox.showerror("Error", f"Could not create account:\n{e}")
                return
            messagebox.showinfo("Account created",
                                "Admin account created. Please log in.")
            self.account_just_created = True
            self.destroy()
            return

        user = authenticate(username, password)
        if user is None:
            messagebox.showerror("Login failed", "Incorrect username or password.")
            return
        self.result_user = user
        self.destroy()

    def _on_cancel(self):
        self.result_user = None
        self.destroy()
