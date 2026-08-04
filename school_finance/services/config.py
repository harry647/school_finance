"""Application settings management using a JSON config file."""
import json
import os

from db.database import BASE_DIR

CONFIG_PATH = os.path.join(BASE_DIR, "data", "config.json")

DEFAULTS = {
    "school_name": "",
    "currency_symbol": "KES",
    "backup_interval_minutes": 0,
    "auto_backup_on_exit": True,
    "backup_retention_count": 10,
    "encryption_passphrase": "",
    "default_grade": "",
    "receipt_footer": "School Finance System",
}


def load_config():
    if not os.path.exists(CONFIG_PATH):
        return dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        result = dict(DEFAULTS)
        result.update(data)
        return result
    except (json.JSONDecodeError, IOError):
        return dict(DEFAULTS)


def save_config(config):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def get_setting(key):
    config = load_config()
    return config.get(key, DEFAULTS.get(key, ""))


def set_setting(key, value):
    config = load_config()
    config[key] = value
    save_config(config)