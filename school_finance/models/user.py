"""Local authentication and user management.

No network calls, no external hashing libs so the app has zero extra
dependencies for this feature.  Password hashing uses PBKDF2-HMAC-SHA256
with a per-password random salt (Python 3.8 stdlib only).

RBAC: the ``role`` column on the ``users`` table determines what a user can
do.  Permission checks live in :func:`get_user_permissions` and the
convenience wrapper :func:`can_manage_users`; the UI calls
``MainWindow.has_permission(...)`` which delegates to these lookups.
"""
import binascii
import datetime
import hashlib
import hmac
import os

from db.database import get_connection
from utils.validation import (
    validate_password,
    validate_role,
    validate_username,
)

VALID_ROLES = ("Admin", "Bursar", "Clerk")

ROLE_PERMISSIONS = {
    "Admin": {
        "can_delete_student", "can_manage_users", "can_backup",
        "can_import", "can_record_payment", "can_generate_statement",
        "can_manage_waivers", "can_manage_fee_structure",
    },
    "Bursar": {
        "can_delete_student", "can_import", "can_record_payment",
        "can_generate_statement", "can_backup", "can_manage_waivers",
        "can_manage_fee_structure",
    },
    "Clerk": {
        "can_record_payment", "can_generate_statement",
    },
}


def _hash_password(password, salt=None):
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return binascii.hexlify(salt).decode() + "$" + binascii.hexlify(digest).decode()


def _verify_password(password, stored_hash):
    salt_hex, digest_hex = stored_hash.split("$")
    salt = binascii.unhexlify(salt_hex)
    computed = _hash_password(password, salt)
    return hmac.compare_digest(computed, stored_hash)


def _now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def _row_to_dict(row):
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# RBAC helpers
# ---------------------------------------------------------------------------


def get_user_permissions(role):
    """Return the set of permission strings for a role, or an empty set."""
    return ROLE_PERMISSIONS.get(role, set())


def can_manage_users(user):
    """True if *user* (a dict-like row) has admin-level access."""
    return user and user.get("role") in ("Admin",)


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


def any_users_exist():
    conn = get_connection()
    row = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()
    return row["n"] > 0


def list_users(include_inactive=False):
    """Return all users ordered by role priority then username.

    *include_inactive* — if False (default), only active (non-deleted) users
    are returned.
    """
    conn = get_connection()
    where = "" if include_inactive else "WHERE is_active = 1"
    return conn.execute(
        f"SELECT * FROM users {where} "
        "ORDER BY CASE role WHEN 'Admin' THEN 0 WHEN 'Bursar' THEN 1 "
        "ELSE 2 END, username"
    ).fetchall()


def get_user(user_id):
    conn = get_connection()
    return _row_to_dict(
        conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    )


def get_user_by_username(username):
    conn = get_connection()
    return _row_to_dict(
        conn.execute(
            "SELECT * FROM users WHERE username = ?", (username.strip(),)
        ).fetchone()
    )


# ---------------------------------------------------------------------------
# Admin CRUD
# ---------------------------------------------------------------------------


def create_user(full_name, username, password, role="Bursar", signature_path=None):
    """Admin creates a new user.

    Validates the username and password before insertion.  Raises
    ``sqlite3.IntegrityError`` if the username is already taken.
    """
    username = validate_username(username)
    password = validate_password(password)
    role = validate_role(role)
    conn = get_connection()
    now = _now()
    conn.execute(
        "INSERT INTO users (username, password_hash, full_name, role, "
        "signature_path, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            username,
            _hash_password(password),
            full_name.strip() or None,
            role,
            signature_path,
            now,
            now,
        ),
    )
    conn.commit()
    log_action(
        username, "create_user",
        f"Created user '{username}' (role={role})",
    )


def update_user_profile(user_id, full_name=None, username=None, role=None,
                        signature_path=None, is_active=None):
    """Admin updates a user's profile (not the password).

    Only the supplied keyword arguments are written to the database.
    """
    updates = []
    params = []
    if full_name is not None:
        updates.append("full_name = ?")
        params.append(full_name.strip() or None)
    if username is not None:
        new_username = validate_username(username)
        existing = get_user_by_username(new_username)
        if existing and existing["id"] != user_id:
            raise ValueError(f"Username '{new_username}' is already taken")
        updates.append("username = ?")
        params.append(new_username)
    if role is not None:
        updates.append("role = ?")
        params.append(validate_role(role))
    if signature_path is not None:
        updates.append("signature_path = ?")
        params.append(signature_path)
    if is_active is not None:
        updates.append("is_active = ?")
        params.append(1 if is_active else 0)
    if not updates:
        return 0

    params.append(_now())
    params.append(user_id)
    conn = get_connection()
    cur = conn.execute(
        "UPDATE users SET " + ", ".join(updates) + ", updated_at = ? "
        "WHERE id = ?",
        params,
    )
    conn.commit()
    return cur.rowcount


def update_user_password(user_id, new_password):
    """Admin-initiated password reset (no old-password verification)."""
    new_password = validate_password(new_password)
    conn = get_connection()
    conn.execute(
        "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
        (_hash_password(new_password), _now(), user_id),
    )
    conn.commit()
    user = get_user(user_id)
    if user:
        log_action(
            user["username"], "reset_user_password",
            f"Admin reset password for '{user['username']}' (id={user_id})",
        )
    return True


def delete_user(user_id, soft=True, requester_id=None):
    """Delete a user.

    *soft=True* (default) sets ``is_active = 0`` so audit-log references survive.

    Guards:
      - Cannot delete the requester's own account.
      - Cannot hard-delete the last active Admin (prevents lockout).
    """
    if requester_id is not None and requester_id == user_id:
        raise ValueError("You cannot delete your own account")

    user = get_user(user_id)
    if user is None:
        raise ValueError(f"User id={user_id} not found")

    conn = get_connection()

    if soft:
        conn.execute(
            "UPDATE users SET is_active = 0, updated_at = ? WHERE id = ?",
            (_now(), user_id),
        )
        conn.commit()
        log_action(
            user["username"], "delete_user",
            f"Soft-deleted user '{user['username']}' (id={user_id})",
        )
        return True

    # --- hard delete guard: ensure at least one active Admin remains ---
    active_admins = conn.execute(
        "SELECT COUNT(*) AS n FROM users WHERE role = 'Admin' AND is_active = 1"
    ).fetchone()
    if user["role"] == "Admin" and active_admins["n"] <= 1:
        raise ValueError("Cannot delete the last active Admin user")

    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    log_action(
        user["username"], "delete_user",
        f"Hard-deleted user '{user['username']}' (id={user_id})",
    )
    return True


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def authenticate(username, password):
    """Verify credentials and return the user dict on success, else None.

    Also updates ``last_login`` in the database atomically.
    """
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM users WHERE username = ?", (username.strip(),)
    ).fetchone()
    if row is None:
        return None
    if not _verify_password(password, row["password_hash"]):
        log_action(
            username.strip(), "login_failed",
            f"Failed login attempt for username '{username.strip()}'",
        )
        return None

    conn.execute(
        "UPDATE users SET last_login = ? WHERE id = ?",
        (_now(), row["id"]),
    )
    conn.commit()
    result = dict(row)
    result["last_login"] = _now()
    log_action(
        row["username"], "login",
        f"Successful login (role={row['role']})",
    )
    return result


def create_user_deprecated(username, password, role="Admin"):
    """Backward-compatible shim kept for any external callers.

    Prefer :func:`create_user` which requires ``full_name``.
    """
    create_user(full_name="", username=username, password=password, role=role)


# ---------------------------------------------------------------------------
# Self-service
# ---------------------------------------------------------------------------


def update_own_settings(user_id, new_username, current_password,
                        new_password=None):
    """Authenticated user updates their own username and optionally password.

    Requires the *current* password to be verified first — prevents an
    unattended session from escalating privileges by changing credentials.

    Raises ``ValueError`` if:
      - Current password does not match.
      - New username is already taken by another user.
      - New password fails validation.
    """
    user = get_user(user_id)
    if user is None:
        raise ValueError("User not found")

    if not _verify_password(current_password, user["password_hash"]):
        raise ValueError("Current password is incorrect")

    params = []
    updates = []

    new_username = validate_username(new_username)
    existing = get_user_by_username(new_username)
    if existing and existing["id"] != user_id:
        raise ValueError(f"Username '{new_username}' is already taken")
    updates.append("username = ?")
    params.append(new_username)

    if new_password:
        new_password = validate_password(new_password)
        updates.append("password_hash = ?")
        params.append(_hash_password(new_password))

    if updates:
        params.append(_now())
        params.append(user_id)
        conn = get_connection()
        conn.execute(
            "UPDATE users SET " + ", ".join(updates) + ", updated_at = ? "
            "WHERE id = ?",
            params,
        )
        conn.commit()

    old_username = user["username"]
    if new_username != old_username:
        log_action(
            new_username, "update_own_username",
            f"Changed own username from '{old_username}' to '{new_username}'",
        )
    if new_password:
        log_action(
            new_username, "update_own_password",
            "Changed own password",
        )
    return True


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def log_action(username, action, detail=""):
    conn = get_connection()
    conn.execute(
        "INSERT INTO audit_log (username, action, detail) VALUES (?, ?, ?)",
        (username, action, detail),
    )
    conn.commit()
