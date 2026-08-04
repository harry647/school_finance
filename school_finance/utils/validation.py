"""Input validation and sanitization utilities."""
import re
import os

MAX_TEXT_LENGTH = 200
ALLOWED_COLUMNS = {"full_name", "grade", "admission_no", "remarks", "status"}


def sanitize_text(value, max_length=MAX_TEXT_LENGTH):
    if value is None:
        return None
    text = str(value).strip()
    if len(text) > max_length:
        text = text[:max_length]
    return text


def validate_amount(value):
    try:
        amount = float(value)
    except (TypeError, ValueError):
        raise ValueError("Amount must be a valid number")
    if amount <= 0:
        raise ValueError("Amount must be greater than zero")
    return round(amount, 2)


def validate_column_name(column_name):
    if column_name not in ALLOWED_COLUMNS:
        raise ValueError(f"Invalid column name: {column_name}")
    return column_name


def safe_file_path(user_path, base_dir):
    resolved = os.path.realpath(user_path)
    base = os.path.realpath(base_dir)
    if not resolved.startswith(base + os.sep) and resolved != base:
        raise ValueError("Path is outside the allowed directory")
    return resolved


def validate_username(username):
    if not username or not username.strip():
        raise ValueError("Username cannot be empty")
    if len(username.strip()) > 50:
        raise ValueError("Username must be 50 characters or fewer")
    if not re.match(r"^[a-zA-Z0-9_]+$", username.strip()):
        raise ValueError("Username may only contain letters, digits, and underscores")
    return username.strip()


def validate_password(password):
    if not password:
        raise ValueError("Password cannot be empty")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    if len(password) > 128:
        raise ValueError("Password must be 128 characters or fewer")
    return password


def validate_grade(grade):
    if not grade or not grade.strip():
        raise ValueError("Grade cannot be empty")
    if len(grade.strip()) > 20:
        raise ValueError("Grade must be 20 characters or fewer")
    return grade.strip()


def validate_role(role):
    valid_roles = {"Admin", "Bursar", "Clerk"}
    if role not in valid_roles:
        raise ValueError(
            f"Invalid role '{role}'. Must be one of: {', '.join(sorted(valid_roles))}"
        )
    return role