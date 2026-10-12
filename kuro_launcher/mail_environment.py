"""Canonical Mail handoff configuration shared by Core and producer children."""
from pathlib import Path

MAIL_HANDOFF_KEYS = ("KURO_MAIL_STATUS_FILE", "KURO_MAIL_WORK_FILE")


def mail_paths(cfg):
    paths = []
    for field in ("status_path", "work_path"):
        value = getattr(cfg, "core_mail_" + field, None)
        if value is None or not str(value).strip():
            raise ValueError(f"Enabled Mail requires an explicit {field}")
        text = str(value).strip()
        if "\x00" in text or "${" in text or ("%" in text and text.count("%") >= 2):
            raise ValueError(f"Mail {field} must be resolved")
        path = Path(text)
        if not path.is_absolute():
            raise ValueError(f"Mail {field} must be absolute")
        paths.append(path.resolve())
    if paths[0] == paths[1]:
        raise ValueError("Mail work_path must differ from status_path")
    return tuple(paths)


def mail_enabled(cfg):
    return bool(cfg.core_enabled and getattr(cfg, "core_mail_enabled", False))


def mail_handoff_environment(cfg):
    if not mail_enabled(cfg):
        return {}
    return dict(zip(MAIL_HANDOFF_KEYS, map(str, mail_paths(cfg))))


def clear_mail_handoffs(env):
    for key in MAIL_HANDOFF_KEYS:
        env.pop(key, None)
