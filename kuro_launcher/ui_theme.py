from typing import Dict

import customtkinter as ctk


PALETTE = {
    "app_bg": "#edf6ff",
    "panel_bg": "#ffffff",
    "panel_soft": "#f7fbff",
    "panel_alt": "#f2f7ff",
    "panel_border": "#d7e4f4",
    "textbox_bg": "#fcfdff",
    "textbox_border": "#d9e4f5",
    "text": "#20304a",
    "muted": "#64748b",
    "accent_pink": "#f472b6",
    "accent_pink_hover": "#ec4899",
    "accent_blue": "#60a5fa",
    "accent_blue_hover": "#3b82f6",
    "accent_lavender": "#a78bfa",
    "accent_lavender_hover": "#8b5cf6",
    "accent_soft": "#e0edff",
    "success": "#38bdf8",
    "warning": "#f59e0b",
    "danger": "#ef4444",
}

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
LOG_DRAIN_INTERVAL_MS = 220
LOG_DRAIN_MAX_LINES = 60
STATUS_TICK_INTERVAL_MS = 2200

EXPRESSION_BASE_PARAMETERS: Dict[str, float] = {
    "Param6": 0,
    "Param7": 0,
    "Param8": 0,
    "Param9": 0,
    "Param91": 0,
    "Param92": 0,
    "Param93": 0,
    "Param94": 0,
    "ParamCheek": 0,
    "ParamEyeLSmile": 0,
    "ParamEyeRSmile": 0,
    "ParamMouthForm": 0,
    "ParamBrowLY": 0,
    "ParamBrowRY": 0,
    "ParamBrowLForm": 0,
    "ParamBrowRForm": 0,
}

EXPRESSION_PRESETS: Dict[str, dict] = {
    "neutral": {"label": "一般", "parameters": {}},
    "happy": {
        "label": "開心",
        "parameters": {
            "Param6": 1,
            "ParamCheek": 0.35,
            "ParamEyeLSmile": 0.65,
            "ParamEyeRSmile": 0.65,
            "ParamMouthForm": 0.28,
        },
    },
    "angry": {
        "label": "生氣",
        "parameters": {
            "Param7": 1,
            "ParamBrowLForm": -0.6,
            "ParamBrowRForm": -0.6,
            "ParamMouthForm": -0.32,
        },
    },
    "sad": {
        "label": "難過",
        "parameters": {
            "Param8": 1,
            "ParamBrowLY": -0.25,
            "ParamBrowRY": -0.25,
            "ParamMouthForm": -0.42,
        },
    },
    "cry": {
        "label": "哭哭",
        "parameters": {
            "Param9": 1,
            "Param91": 1,
            "Param92": 1,
            "Param93": 1,
            "Param94": 1,
            "ParamMouthForm": -0.4,
        },
    },
    "shy": {
        "label": "害羞",
        "parameters": {
            "Param6": 0.7,
            "ParamCheek": 0.85,
            "ParamEyeLSmile": 0.35,
            "ParamEyeRSmile": 0.35,
            "ParamMouthForm": 0.12,
        },
    },
    "thinking": {
        "label": "思考",
        "parameters": {
            "ParamBrowLY": 0.25,
            "ParamBrowRY": 0.25,
            "ParamMouthForm": -0.12,
        },
    },
}

EXPRESSION_LABEL_TO_ID = {
    str(item["label"]): expression_id
    for expression_id, item in EXPRESSION_PRESETS.items()
}
EXPRESSION_ID_TO_LABEL = {
    expression_id: str(item["label"])
    for expression_id, item in EXPRESSION_PRESETS.items()
}

THINKING_POWER_LABEL_TO_ID = {
    "快速": "fast",
    "普通": "normal",
    "深度": "deep",
}
THINKING_POWER_ID_TO_LABEL = {
    thinking_id: label
    for label, thinking_id in THINKING_POWER_LABEL_TO_ID.items()
}
THINKING_POWER_LABELS = list(THINKING_POWER_LABEL_TO_ID.keys())

FONT_UI = "Microsoft JhengHei UI"
FONT_MONO = "Cascadia Mono"


def ui_font(size: int, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(family=FONT_UI, size=size, weight=weight)


def mono_font(size: int, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(family=FONT_MONO, size=size, weight=weight)


class StatusBadge(ctk.CTkFrame):
    def __init__(self, master, name: str):
        super().__init__(
            master,
            corner_radius=18,
            fg_color=PALETTE["panel_bg"],
            border_width=1,
            border_color=PALETTE["panel_border"],
        )
        self.grid_columnconfigure(1, weight=1)
        self._name = name
        self.dot = ctk.CTkLabel(self, text="●", text_color=PALETTE["warning"], width=18)
        self.dot.grid(row=0, column=0, padx=(12, 6), pady=8)
        self.label = ctk.CTkLabel(
            self,
            text=f"{name} · Offline",
            font=ui_font(12, "bold"),
            anchor="w",
            text_color=PALETTE["text"],
        )
        self.label.grid(row=0, column=1, padx=(0, 12), sticky="w")

    def set_status(self, online: bool) -> None:
        self.dot.configure(text_color=PALETTE["success"] if online else PALETTE["warning"])
        self.label.configure(text=f"{self._name} · {'Online' if online else 'Offline'}")
