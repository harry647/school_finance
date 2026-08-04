"""
School Finance System - entry point.

Run with:  python main.py
Or run the packaged .exe built by PyInstaller (see build_windows.bat).
"""
import logging
from db.database import get_connection  # noqa: E402
from ui.login_dialog import LoginDialog  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402

logger = logging.getLogger("school_finance")


def main():
    try:
        get_connection()
    except Exception as e:
        logger.error("Failed to initialize database: %s", e, exc_info=True)
        try:
            from tkinter import messagebox
            root = __import__("tkinter").Tk()
            root.withdraw()
            messagebox.showerror("School Finance System - Error", str(e))
            root.destroy()
        except Exception:
            pass
        return

    root = __import__("tkinter").Tk()
    root.withdraw()

    while True:
        logged_in_user = None
        while logged_in_user is None:
            try:
                dialog = LoginDialog(root)
                root.wait_window(dialog)
            except Exception as e:
                logger.error("Login dialog failed: %s", e, exc_info=True)
                try:
                    from tkinter import messagebox
                    messagebox.showerror("Error", f"Login dialog failed: {e}")
                except Exception:
                    pass
                root.destroy()
                return
            if dialog.account_just_created:
                continue
            if dialog.result_user is not None:
                logged_in_user = dialog.result_user
            else:
                root.destroy()
                return

        app = None
        try:
            app = MainWindow(root, logged_in_user)
            app.mainloop()
        except Exception as e:
            logger.error("Main window failed: %s", e, exc_info=True)
            try:
                from tkinter import messagebox
                messagebox.showerror("School Finance System - Error", str(e))
            except Exception:
                pass

        if app is None or not getattr(app, "_logout_requested", False):
            break

    root.destroy()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error("Fatal error: %s", e, exc_info=True)
        try:
            from tkinter import messagebox
            messagebox.showerror("School Finance System - Error", str(e))
        except Exception:
            pass
