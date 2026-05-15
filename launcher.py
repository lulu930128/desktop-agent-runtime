import os
import sys
import threading
import time
import datetime
import queue
import webbrowser
from pathlib import Path
from typing import Optional, Dict

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, messagebox

# --- bootstrap (robust imports + crash logging) ---
def _bootstrap_paths() -> Path:
    """Return base_dir for resolving assets + ensure local imports work.

    - When running normally: base_dir = folder containing this launcher.py
    - When packaged (PyInstaller): base_dir = sys._MEIPASS (extracted temp dir)
    """
    # Determine base directory
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base_dir = Path(getattr(sys, "_MEIPASS")).resolve()
    else:
        base_dir = Path(__file__).parent.resolve()

    # Ensure we can import 'kuro_launcher' package (expected under base_dir/kuro_launcher)
    if str(base_dir) not in sys.path:
        sys.path.insert(0, str(base_dir))

    assets_dir = base_dir / "kuro_launcher"
    return assets_dir if assets_dir.exists() else base_dir



def _write_crash_log() -> None:
    """Write last exception traceback to Desktop/kuro_launcher_crash.log (best-effort)."""
    try:
        import traceback
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        p = Path.home() / "Desktop" / "kuro_launcher_crash.log"
        p.write_text(f"[{ts}]\n{traceback.format_exc()}\n", encoding="utf-8")
    except Exception:
        pass



def _dbg(msg: str) -> None:
    try:
        print(f"[launcher][DBG] {msg}", flush=True)
    except Exception:
        pass


# --- runtime logging (so `python launcher.py` shows something + keeps a log) ---
def _setup_runtime_logging(log_dir: Path) -> Path:
    """Best-effort: mirror stdout/stderr into a log file under log_dir."""
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = log_dir / "launcher.combined.log"

        class _Tee:
            def __init__(self, a, b):
                self.a, self.b = a, b
            def write(self, s):
                try: self.a.write(s)
                except Exception: pass
                try: self.b.write(s)
                except Exception: pass
            def flush(self):
                try: self.a.flush()
                except Exception: pass
                try: self.b.flush()
                except Exception: pass

        f = open(log_path, "a", encoding="utf-8", buffering=1)
        sys.stdout = _Tee(sys.stdout, f)  # type: ignore
        sys.stderr = _Tee(sys.stderr, f)  # type: ignore
        return log_path
    except Exception:
        return log_dir / "launcher_console.log"

# --- UI helpers: custom font + app icon (Windows friendly) ---
def _try_register_private_font(font_path: Path, timeout_sec: float = 1.5) -> Optional[str]:
    """Register a private TTF font on Windows (no install). Returns a best-guess family name or None.

    Some Windows+Tk setups can hang when querying tkfont.families() right after font registration.
    To keep the launcher responsive, we avoid querying families here. If registration succeeds,
    we return a reasonable guess based on filename; otherwise None.
    """
    if not font_path or not font_path.exists():
        return None
    if not sys.platform.startswith("win"):
        return None

    ok_holder = {"ok": False}

    def _do_register():
        try:
            import ctypes
            FR_PRIVATE = 0x10
            # Add font resource (private to this process)
            ret = ctypes.windll.gdi32.AddFontResourceExW(str(font_path), FR_PRIVATE, 0)
            ok_holder["ok"] = bool(ret)
            # Broadcast font change (best-effort)
            try:
                ctypes.windll.user32.SendMessageW(0xFFFF, 0x001D, 0, 0)  # HWND_BROADCAST, WM_FONTCHANGE
            except Exception:
                pass
        except Exception:
            ok_holder["ok"] = False

    t = threading.Thread(target=_do_register, daemon=True)
    t.start()
    t.join(timeout=timeout_sec)

    if not ok_holder["ok"]:
        return None

    # Best-effort guess: many fonts expose family close to filename.
    # If this guess doesn't match, ttk will just fall back to system font.
    stem = font_path.stem
    # Common cleanup
    stem = stem.replace("-Regular", "").replace("_", " ").strip()
    return stem or None


def _set_app_icon(root: tk.Tk, base_dir: Path) -> None:
    """Set window icon. Prefer .ico on Windows; fall back to .png."""
    try:
        ico = base_dir / "luncher_yuki.ico"
        png = base_dir / "luncher_yuki.png"
        if sys.platform.startswith("win") and ico.exists():
            root.iconbitmap(default=str(ico))
            return
        if png.exists():
            img = tk.PhotoImage(file=str(png))
            root.iconphoto(True, img)
            root._kuro_icon_img = img  # keep reference
    except Exception:
        pass


from kuro_launcher.config import load_config, AppConfig
from kuro_launcher.procs import ManagedProc
from kuro_launcher.runtime_conf import build_runtime_conf, write_runtime_conf
from kuro_launcher.services import start_bridge, start_tts, start_llm, validate_profile_assets, probe_tts
from kuro_launcher.utils import (
    log_ts, port_is_open, read_yaml_file, http_post_json,
    get_listening_pid_windows, taskkill_tree, build_logs_dir, strip_ansi_and_ctrl,
    load_env_file
)



class RoundedPill(tk.Canvas):
    """A small iPhone-like rounded badge with a colored dot and text."""

    def __init__(self, master, text: str, dot: str, bg: str, border: str, fg: str):
        bg_base = "#FFFFFF"
        try:
            bg_base = master.cget("background")
        except Exception:
            # ttk widgets may not support -background; fall back to white
            bg_base = "#FFFFFF"
        super().__init__(master, bg=bg_base, highlightthickness=0, bd=0)
        self._bg = bg
        self._border = border
        self._fg = fg
        self._dot = dot
        self._text = text
        self._padx = 10
        self._pady = 6
        self._r = 14
        self._font = ("Segoe UI", 10, "bold")
        self._draw()

    def set(self, text: str, online: bool):
        self._text = text
        self._dot = "#2EC4C6" if online else "#FF9A3E"
        self._draw()

    def _draw(self):
        """Draw a seamless rounded pill.

        We intentionally avoid composing arcs + rectangles with outlines, because Tk will
        often show "seams" (extra inner lines) at the join boundaries.
        """
        self.delete("all")
        fnt = tk.font.Font(font=self._font)
        tw = fnt.measure(self._text)
        th = fnt.metrics("linespace")
        h = th + self._pady * 2
        w = tw + self._padx * 2 + 18  # dot + gap
        self.config(width=w, height=h)

        r = min(self._r, h // 2)
        # Smooth polygon rounded-rect (no internal seams)
        # points go clockwise; smooth=True makes the corners rounded.
        pts = [
            r, 0,
            w - r, 0,
            w, 0,
            w, r,
            w, h - r,
            w, h,
            w - r, h,
            r, h,
            0, h,
            0, h - r,
            0, r,
            0, 0,
        ]
        self.create_polygon(
            pts,
            smooth=True,
            splinesteps=24,
            fill=self._bg,
            outline=self._border,
            width=1,
        )

        # dot + text
        cy = h // 2
        self.create_oval((self._padx, cy - 4, self._padx + 8, cy + 4), fill=self._dot, outline="")
        self.create_text(self._padx + 14, cy, text=self._text, anchor="w", fill=self._fg, font=self._font)


class LauncherApp(tk.Tk):
    """
    Kuro Launcher (Dualflow-ready)
    - Starts/stops: Bridge / TTS / LLM
    - Select character yaml
    """

    
    def _apply_fonts_and_styles(self) -> None:
        """Apply consistent font across ttk widgets (fix missing CJK glyphs)."""
        base = (self._ui_font_family, self._ui_font_base)
        bold = (self._ui_font_family, self._ui_font_base, "bold")
        title = (self._ui_font_family, 16, "bold")
        
        # ttk defaults
        self.style.configure(".", font=base)
        self.style.configure("TLabel", font=base)
        self.style.configure("TButton", font=base)
        self.style.configure("TEntry", font=base)
        self.style.configure("Treeview", font=base, rowheight=32, background="#FFFFFF", fieldbackground="#FFFFFF", foreground=self._c_fg)
        self.style.configure("Treeview.Heading", font=bold, background="#F3F8FF", foreground=self._c_fg, relief="flat")
        self.style.map("Treeview", background=[("selected", "#D6E8FF")], foreground=[("selected", self._c_fg)])
        self.style.configure("Header.TLabel", font=title)
        self.style.configure("Status.TLabel", font=bold)
        self.style.configure("CardTitle.TLabel", font=bold)

    def __init__(self, cfg: AppConfig):
        _dbg('LauncherApp.__init__ enter')
        super().__init__()
        _dbg('Tk root created')
        base_dir = _bootstrap_paths()
        _dbg(f'base_dir={base_dir}')
        # Set app icon (put luncher_yuki.ico or luncher_yuki.png in this folder)
        _set_app_icon(self, base_dir)
        _dbg('icon set (best-effort)')
        # Custom font: NaikaiFont-Regular.ttf (Windows private registration)
        font_path = base_dir / 'NaikaiFont-Regular.ttf'
        _dbg(f'font_path={font_path}')
        family = _try_register_private_font(font_path, timeout_sec=1.5)
        _dbg(f'font_family={family}')
        self._ui_font_family = family or 'Microsoft JhengHei UI'
        self._ui_font_base = 12
        # Log area font: use the same family so CJK doesn't fall back unexpectedly.
        self._log_font = (self._ui_font_family, 11)

        self.cfg = cfg

        self.title("Kuro Launcher")
        # Larger default window so the right control panel doesn't get clipped.
        # (Users can resize, but we keep a reasonable minimum.)
        self.geometry("1280x780")
        self.minsize(1160, 700)

        # procs managed by launcher (if started by launcher)
        self.proc_bridge: Optional[ManagedProc] = None
        self.proc_tts: Optional[ManagedProc] = None
        self.proc_llm: Optional[ManagedProc] = None

        # Thread-safe UI logging: background threads must not touch Tk widgets directly.
        self._main_thread_id = threading.get_ident()
        self._log_q: "queue.Queue[str]" = queue.Queue()

        self._item_to_yaml: Dict[str, Path] = {}
        self.current_run_id: Optional[str] = None

        _dbg('init_style...')
        self._init_style()
        _dbg('build_ui...')
        self._build_ui()

        # Start draining log queue after widgets exist.
        self.after(100, self._drain_log_queue)
        _dbg('refresh_character_list...')
        self._refresh_character_list()
        _dbg('character list ready')

        # ensure bridge on startup (non-blocking)
        threading.Thread(target=self._ensure_bridge_on_start, daemon=True).start()

        # periodic status refresh
        self.after(400, self._tick_status)

    # ----------------- Styling -----------------
    def _init_style(self):
        self.style = ttk.Style()
        style = self.style

        # Prefer a consistent theme (works well on Windows)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        # Pastel palette (soft blue / pink with light surfaces)
        self._c_bg = "#EEF6FF"       # window background
        self._c_panel = "#FFFFFF"    # cards/panels
        self._c_panel2 = "#F3F8FF"   # subtle tinted surface
        self._c_fg = "#1F2A44"       # text
        self._c_muted = "#5C6B8A"    # secondary text
        # Line color grading (outer -> inner)
        self._c_border = "#C9DAFF"   # borders (level-1, outer)
        self._c_border2 = "#DDE8FF"  # borders (level-2, inner groups)
        self._c_border3 = "#EEF4FF"  # borders (level-3, separators)
        self._c_blue = "#5B8CFF"     # primary accent (blue)
        self._c_pink = self._c_blue     # deprecated (keep for compatibility)
        self._c_teal = "#2EC4C6"     # supportive accent (teal)
        self._c_warn = "#FF9A3E"     # warning / offline

        self.configure(bg=self._c_bg)

        # Base fonts
        self._font_h1 = (self._ui_font_family, 16, "bold")
        self._font_h2 = (self._ui_font_family, 11, "bold")
        self._font_body = (self._ui_font_family, 11)

        # ttk element colors
        style.configure("TFrame", background=self._c_bg)
        style.configure(
            "Card.TFrame",
            background=self._c_panel,
            borderwidth=1,
            relief="solid",
        )

        style.configure("TLabel", background=self._c_bg, foreground=self._c_fg, font=self._font_body)
        style.configure("Muted.TLabel", background=self._c_bg, foreground=self._c_muted, font=self._font_body)
        style.configure("H1.TLabel", background=self._c_bg, foreground=self._c_fg, font=self._font_h1)
        style.configure("H2.TLabel", background=self._c_bg, foreground=self._c_fg, font=self._font_h2)

        # Labels that live inside white panels/cards (avoid colored label "strips")
        style.configure("Panel.TLabel", background=self._c_panel, foreground=self._c_fg, font=self._font_body)
        style.configure("PanelMuted.TLabel", background=self._c_panel, foreground=self._c_muted, font=self._font_body)
        style.configure("PanelH2.TLabel", background=self._c_panel, foreground=self._c_fg, font=self._font_h2)

        # Labelframe
        style.configure("TLabelframe", background=self._c_bg, bordercolor=self._c_border)
        style.configure("TLabelframe.Label", background=self._c_bg, foreground=self._c_fg, font=self._font_h2)

        # Separator (very light)
        style.configure("TSeparator", background=self._c_border3)

        # Buttons (keep several styles so the UI isn't single-tone)
        style.configure(
            "TButton",
            font=self._font_body,
            padding=(10, 7),
            background=self._c_panel2,
            foreground=self._c_fg,
            borderwidth=1,
            relief="flat",
        )
        style.map(
            "TButton",
            background=[("active", "#E3ECFF"), ("pressed", "#D9E6FF")],
        )

        style.configure(
            "Primary.TButton",
            font=self._font_body,
            padding=(10, 7),
            background=self._c_pink,
            foreground="#FFFFFF",
            borderwidth=0,
            relief="flat",
        )
        style.map(
            "Primary.TButton",
            background=[("active", "#FF86BE"), ("pressed", "#FF5AA6")],
            foreground=[("!disabled", "#FFFFFF")],
        )

        style.configure(
            "Blue.TButton",
            font=self._font_body,
            padding=(10, 7),
            background=self._c_blue,
            foreground="#FFFFFF",
            borderwidth=0,
            relief="flat",
        )
        style.map(
            "Blue.TButton",
            background=[("active", "#719CFF"), ("pressed", "#4A7CFF")],
            foreground=[("!disabled", "#FFFFFF")],
        )

        style.configure(
            "Ghost.TButton",
            font=self._font_body,
            padding=(10, 7),
            background=self._c_panel,
            foreground=self._c_fg,
            borderwidth=1,
            relief="flat",
        )
        style.map(
            "Ghost.TButton",
            background=[("active", "#F3F7FF"), ("pressed", "#EAF1FF")],
        )

        # Treeview (table)
        style.configure(
            "Treeview",
            background=self._c_panel,
            fieldbackground=self._c_panel,
            foreground=self._c_fg,
            bordercolor=self._c_border,
            lightcolor=self._c_border,
            darkcolor=self._c_border,
            rowheight=26,
            font=self._font_body,
        )
        style.configure(
            "Treeview.Heading",
            background="#E9F0FF",
            foreground=self._c_fg,
            relief="flat",
            font=(self._ui_font_family, 11, "bold"),
        )
        style.map(
            "Treeview",
            background=[("selected", "#DDE8FF")],
            foreground=[("selected", self._c_fg)],
        )
        style.map(
            "Treeview.Heading",
            background=[("active", "#DDE8FF")],
        )

        # Scrollbar
        style.configure("Vertical.TScrollbar", background=self._c_panel2, troughcolor=self._c_bg, bordercolor=self._c_border)



    def _mk_btn(self, parent, text: str, kind: str, command):
        """Create a border button:

        Requirement (style-2): default is "blank" (white background), hover becomes blue.
        We use tk.Button for consistent rendering across Windows themes.

        kind is kept for backward compatibility but intentionally does not change the default look.
        """
        normal_bg = self._c_panel
        normal_fg = self._c_fg
        hover_bg = self._c_blue
        hover_fg = "#FFFFFF"
        active_bg = "#3F74FF"  # slightly deeper blue

        btn = tk.Button(
            parent,
            text=text,
            command=command,
            bg=normal_bg,
            fg=normal_fg,
            activebackground=active_bg,
            activeforeground=hover_fg,
            font=(self._ui_font_family, 11),
            padx=14,
            pady=8,
            bd=1,
            relief="solid",
            highlightthickness=0,
        )

        def _on_enter(_e):
            try:
                btn.configure(bg=hover_bg, fg=hover_fg)
            except Exception:
                pass

        def _on_leave(_e):
            try:
                btn.configure(bg=normal_bg, fg=normal_fg)
            except Exception:
                pass

        btn.bind("<Enter>", _on_enter)
        btn.bind("<Leave>", _on_leave)
        return btn

    def _build_ui(self):
        # ---------------- Header ----------------
        header = ttk.Frame(self)
        header.pack(fill="x", padx=12, pady=(12, 8))

        ttk.Label(header, text="Kuro Launcher", style="H1.TLabel").pack(side="left")
        ttk.Label(header, text="Dualflow / 多角色啟動器", style="Muted.TLabel").pack(side="left", padx=(10, 0))

        status_bar = ttk.Frame(header)
        status_bar.pack(side="right")

        # iPhone-like rounded pills (Canvas-based, real rounded corners)
        self.pill_bridge = RoundedPill(status_bar, "Bridge: OFFLINE", dot="#FF9A3E",
                                       bg="#FFFFFF", border=self._c_border, fg=self._c_fg)
        self.pill_bridge.pack(side="left", padx=(0, 8))

        self.pill_tts = RoundedPill(status_bar, "TTS: OFFLINE", dot="#FF9A3E",
                                    bg="#FFFFFF", border=self._c_border, fg=self._c_fg)
        self.pill_tts.pack(side="left", padx=(0, 8))

        self.pill_llm = RoundedPill(status_bar, "LLM: OFFLINE", dot="#FF9A3E",
                                    bg="#FFFFFF", border=self._c_border, fg=self._c_fg)
        self.pill_llm.pack(side="left")

        # ---------------- Body (top) ----------------
        body = tk.Frame(self, bg=self._c_bg)
        body.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        top = tk.Frame(body, bg=self._c_bg)
        top.pack(fill="both", expand=True)

        # Left card: Characters table
        left_card = tk.Frame(top, bg=self._c_panel, highlightthickness=1, highlightbackground=self._c_border)
        left_card.pack(side="left", fill="both", expand=True, padx=(0, 10))

        # Title row
        title_row = tk.Frame(left_card, bg=self._c_panel)
        title_row.pack(fill="x", padx=12, pady=(10, 6))
        ttk.Label(title_row, text=f"角色 YAML  ({self.cfg.characters_dir})", style="PanelH2.TLabel").pack(side="left")

        ttk.Separator(left_card, orient="horizontal").pack(fill="x", padx=10)

        # Table area
        table_wrap = tk.Frame(left_card, bg=self._c_panel)
        table_wrap.pack(fill="both", expand=True, padx=10, pady=10)

        columns = ("yaml", "conf_name", "conf_uid", "live2d_model")
        self.tree = ttk.Treeview(table_wrap, columns=columns, show="headings", height=12)
        self.tree.pack(side="left", fill="both", expand=True)

        vsb = ttk.Scrollbar(table_wrap, orient="vertical", command=self.tree.yview)
        vsb.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=vsb.set)

        for col, txt, w in [
            ("yaml", "yaml", 170),
            ("conf_name", "conf_name", 160),
            ("conf_uid", "conf_uid", 170),
            ("live2d_model", "live2d_model", 160),
        ]:
            self.tree.heading(col, text=txt)
            self.tree.column(col, width=w, anchor="w", stretch=True)

        # Hover highlight (default white, hover becomes light blue)
        self._hover_iid = None
        self.tree.tag_configure("hover", background="#F3F8FF")
        self.tree.tag_configure("normal", background="#FFFFFF")
        self.tree.tag_configure("zebra", background="#FAFCFF")

        def _on_tree_motion(event):
            iid = self.tree.identify_row(event.y)
            if iid == self._hover_iid:
                return
            # clear old hover
            if self._hover_iid:
                tags = [t for t in self.tree.item(self._hover_iid, "tags") if t != "hover"]
                self.tree.item(self._hover_iid, tags=tags)
            self._hover_iid = iid if iid else None
            if iid:
                tags = list(self.tree.item(iid, "tags"))
                if "hover" not in tags:
                    tags.append("hover")
                self.tree.item(iid, tags=tags)

        def _on_tree_leave(_event):
            if self._hover_iid:
                tags = [t for t in self.tree.item(self._hover_iid, "tags") if t != "hover"]
                self.tree.item(self._hover_iid, tags=tags)
                self._hover_iid = None

        self.tree.bind("<Motion>", _on_tree_motion)
        self.tree.bind("<Leave>", _on_tree_leave)

        # Bottom buttons in left card
        ttk.Separator(left_card, orient="horizontal").pack(fill="x", padx=10)

        btns = tk.Frame(left_card, bg=self._c_panel)
        btns.pack(fill="x", padx=12, pady=10)
        # Three buttons should fill the row (equal width)
        btns.grid_columnconfigure(0, weight=1)
        btns.grid_columnconfigure(1, weight=1)
        btns.grid_columnconfigure(2, weight=1)

        self._mk_btn(btns, "重新掃描", "ghost", self._refresh_character_list).grid(row=0, column=0, sticky="ew")
        self._mk_btn(btns, "啟動選取角色", "primary", self.on_start_profile).grid(row=0, column=1, sticky="ew", padx=10)
        self._mk_btn(btns, "停止 Profile", "ghost", self.on_stop_profile).grid(row=0, column=2, sticky="ew")

        # Right card: Controls
        right_card = tk.Frame(top, bg=self._c_panel, highlightthickness=1, highlightbackground=self._c_border)
        right_card.pack(side="right", fill="y")

        right_inner = tk.Frame(right_card, bg=self._c_panel)
        right_inner.pack(fill="both", expand=True, padx=12, pady=10)

        ttk.Label(right_inner, text="控制面板", style="PanelH2.TLabel").pack(anchor="w")

        def _mk_group(title: str):
            grp = tk.Frame(right_inner, bg=self._c_panel, highlightthickness=1, highlightbackground=self._c_border2)
            grp.pack(fill="x", pady=(10, 0))
            inner = tk.Frame(grp, bg=self._c_panel)
            inner.pack(fill="x", padx=10, pady=10)
            ttk.Label(inner, text=title, style="PanelMuted.TLabel").pack(anchor="w")
            content = tk.Frame(inner, bg=self._c_panel)
            content.pack(fill="x", pady=(8, 0))
            return content

        # Group 1: Quick actions
        box = _mk_group("快速開啟")
        self._mk_btn(box, "打開桌面版（Electron）", "blue", self.on_open_electron).pack(fill="x")
        self._mk_btn(box, "備用：打開 Web UI", "ghost", lambda: webbrowser.open(self.cfg.llm_url)).pack(fill="x", pady=(8, 0))

        # Group 2: Bridge
        b = _mk_group("Bridge")
        self.btn_toggle_bridge = self._mk_btn(b, "停止 Bridge", "ghost", self.on_toggle_bridge)
        self.btn_toggle_bridge.pack(fill="x")
        self._mk_btn(b, "重啟 Bridge", "blue", self.on_restart_bridge).pack(fill="x", pady=(8, 0))

        # Group 3: Diagnose
        d = _mk_group("診斷")
        self._mk_btn(d, "測試翻譯（translate_debug）", "ghost", self.on_translate_debug).pack(fill="x")
        self._mk_btn(d, "打開 logs 資料夾", "ghost", self.on_open_logs_dir).pack(fill="x", pady=(8, 0))

        # ---------------- Bottom Log (full width) ----------------
        log_card = tk.Frame(body, bg=self._c_panel, highlightthickness=1, highlightbackground=self._c_border)
        log_card.pack(fill="both", expand=False, pady=(10, 0))

        log_head = tk.Frame(log_card, bg=self._c_panel)
        log_head.pack(fill="x", padx=12, pady=(10, 6))
        ttk.Label(log_head, text="狀態 / Log", style="PanelH2.TLabel").pack(side="left")
        ttk.Label(log_head, text="（所有啟動/錯誤資訊都會在這裡）", style="PanelMuted.TLabel").pack(side="right")

        # Log content frame (give the log area its own border)
        log_box = tk.Frame(log_card, bg=self._c_panel, highlightthickness=1, highlightbackground=self._c_border2)
        log_box.pack(fill="both", expand=True, padx=10, pady=(8, 10))

        self.txt = tk.Text(
            log_box,
            height=10,
            bg="#FFFFFF",
            fg=self._c_fg,
            insertbackground=self._c_fg,
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=self._log_font,
            padx=12,
            pady=10,
        )
        self.txt.pack(fill="both", expand=True)

# ----------------- Status badge updates -----------------
    # ----------------- Thread-safe logging -----------------
    def log(self, msg: str) -> None:
        """Append a log line to the UI (thread-safe) and also mirror to console log file."""
        # Always enqueue; only the Tk main thread drains into the Text widget.
        try:
            self._log_q.put_nowait(strip_ansi_and_ctrl(str(msg)))
        except Exception:
            return

        # If we're already on the main thread, schedule an ASAP drain to make UI feel snappy.
        if threading.get_ident() == self._main_thread_id:
            try:
                self.after_idle(self._drain_log_queue)
            except Exception:
                pass

    def _drain_log_queue(self) -> None:
        """Drain queued logs into the Tk Text widget. Must run on Tk main thread."""
        try:
            # Text widget might not exist yet or might be destroyed during shutdown.
            txt = getattr(self, "txt", None)
            if not txt or not txt.winfo_exists():
                return

            drained = 0
            while drained < 200:
                try:
                    line = self._log_q.get_nowait()
                except Exception:
                    break
                try:
                    txt.insert("end", line + "\n")
                    txt.see("end")
                except Exception:
                    break
                drained += 1
        finally:
            # Keep polling so background threads can log anytime.
            try:
                self.after(120, self._drain_log_queue)
            except Exception:
                pass


    def _tick_status(self):
        try:
            bridge_ok = port_is_open(self.cfg.bridge_host, self.cfg.bridge_port, 0.1)
            tts_ok = port_is_open(self.cfg.tts_host, self.cfg.tts_port, 0.1)
            llm_ok = port_is_open(self.cfg.llm_host, self.cfg.llm_port, 0.1)

            self._set_badge(self.pill_bridge, "Bridge", bridge_ok)
            self._set_badge(self.pill_tts, "TTS", tts_ok)
            self._set_badge(self.pill_llm, "LLM", llm_ok)

            # toggle button label
            if bridge_ok:
                self.btn_toggle_bridge.config(text="停止 Bridge")
            else:
                self.btn_toggle_bridge.config(text="啟動 Bridge")
        finally:
            self.after(800, self._tick_status)

    def _set_badge(self, pill: 'RoundedPill', name: str, ok: bool):
        # rounded badge with dot + text
        pill.set(f"{name}: ONLINE" if ok else f"{name}: OFFLINE", online=ok)

    # ----------------- Character list -----------------
    def _refresh_character_list(self):
        self.tree.delete(*self.tree.get_children())
        self._item_to_yaml.clear()

        _dbg(f'characters_dir={self.cfg.characters_dir}')
        if not self.cfg.characters_dir.exists():
            _dbg('characters_dir missing -> showerror')
            messagebox.showerror("錯誤", f"找不到 characters_dir：{self.cfg.characters_dir}")
            return

        yamls = sorted(self.cfg.characters_dir.glob("*.yaml"))
        _dbg(f'yaml_count={len(yamls)}')
        if not yamls:
            _dbg('no yamls -> showerror')
            messagebox.showerror("錯誤", f"{self.cfg.characters_dir} 裡沒有任何 *.yaml")
            return

        mao_item = None
        for i, y in enumerate(yamls):
            try:
                d = read_yaml_file(y)
                cc = d.get("character_config") or {}
                conf_name = cc.get("conf_name", y.stem)
                conf_uid = cc.get("conf_uid", "")
                model = cc.get("live2d_model_name", "")
                tag = "zebra" if (i % 2 == 0) else "normal"
                item = self.tree.insert("", "end", values=(y.name, conf_name, conf_uid, model), tags=(tag,))
                self._item_to_yaml[item] = y
                if y.stem.lower() == "mao_pro" or str(conf_name).lower() == "mao_pro":
                    mao_item = item
            except Exception:
                item = self.tree.insert("", "end", values=(y.name, "(parse failed)", "", ""))
                self._item_to_yaml[item] = y

        self.log(f"[{log_ts()}] 已載入 {len(yamls)} 個角色 yaml。")

        # default select mao_pro if exists
        if mao_item:
            self.tree.selection_set(mao_item)
            self.tree.see(mao_item)
        else:
            first = self.tree.get_children()[0]
            self.tree.selection_set(first)
            self.tree.see(first)

    def _get_selected_character_path(self) -> Optional[Path]:
        sel = self.tree.selection()
        if not sel:
            return None
        return self._item_to_yaml.get(sel[0])

    # ----------------- Bridge -----------------
    def _ensure_bridge_on_start(self):
        if not os.environ.get("OPENAI_API_KEY", "").strip():
            self.log(f"[{log_ts()}] ⚠️ 未偵測到 OPENAI_API_KEY（翻譯/腦走 OpenAI 會失敗）。")

        try:
            proc = start_bridge(self.cfg, self.log, logs_root=self.cfg.logs_dir, run_id=None)
            if proc is not None:
                self.proc_bridge = proc
        except Exception as e:
            self.log(f"[{log_ts()}] Bridge 啟動失敗：{e}")
            
            return

        for _ in range(40):
            if port_is_open(self.cfg.bridge_host, self.cfg.bridge_port, 0.2):
                break
            time.sleep(0.2)

        if port_is_open(self.cfg.bridge_host, self.cfg.bridge_port):
            self.log(f"[{log_ts()}] Bridge 已就緒：{self.cfg.bridge_url}")
        else:
            self.log(f"[{log_ts()}] ⚠️ Bridge 似乎未就緒，請看 bridge.err.log")

    def on_restart_bridge(self):
        threading.Thread(target=self._restart_bridge_flow, daemon=True).start()

    def _restart_bridge_flow(self):
        self.log(f"[{log_ts()}] 重啟 Bridge...")

        self._stop_bridge_impl(kill_external=True)

        for _ in range(10):
            if not port_is_open(self.cfg.bridge_host, self.cfg.bridge_port, 0.2):
                break
            time.sleep(0.2)

        self._ensure_bridge_on_start()

    def on_toggle_bridge(self):
        threading.Thread(target=self._toggle_bridge_flow, daemon=True).start()

    def _toggle_bridge_flow(self):
        if port_is_open(self.cfg.bridge_host, self.cfg.bridge_port):
            self.log(f"[{log_ts()}] 停止 Bridge...")
            self._stop_bridge_impl(kill_external=True)
            time.sleep(0.4)
            if not port_is_open(self.cfg.bridge_host, self.cfg.bridge_port):
                self.log(f"[{log_ts()}] Bridge 已停止。")
            else:
                self.log(f"[{log_ts()}] ⚠️ Bridge 仍在跑，請看 bridge.err.log 或確認 PID。")
        else:
            self.log(f"[{log_ts()}] 啟動 Bridge...")
            self._ensure_bridge_on_start()

    def _stop_bridge_impl(self, kill_external: bool = False):
        # Stop managed proc first
        if self.proc_bridge:
            try:
                self.proc_bridge.stop()
            except Exception:
                pass
            self.proc_bridge = None

        if kill_external:
            pid = get_listening_pid_windows(self.cfg.bridge_port)
            if pid:
                try:
                    taskkill_tree(pid)
                except Exception:
                    pass

    # ----------------- Profile -----------------
    def on_start_profile(self):
        ch_path = self._get_selected_character_path()
        if not ch_path:
            messagebox.showinfo("提示", "請先選一個角色 yaml。")
            return
        threading.Thread(target=self._start_profile_flow, args=(ch_path,), daemon=True).start()

    def _start_profile_flow(self, ch_path: Path):
        if not port_is_open(self.cfg.bridge_host, self.cfg.bridge_port):
            self.log(f"[{log_ts()}] Bridge 不在，先啟動 Bridge...")
            self._ensure_bridge_on_start()
            if not port_is_open(self.cfg.bridge_host, self.cfg.bridge_port):
                self.log(f"[{log_ts()}] ❌ Bridge 仍未就緒，取消啟動 profile。")
                return

        # 停掉現有 profile
        self.on_stop_profile(silent=True)

        for _ in range(20):
            if (
                not port_is_open(self.cfg.tts_host, self.cfg.tts_port, 0.1)
                and not port_is_open(self.cfg.llm_host, self.cfg.llm_port, 0.1)
            ):
                break
            time.sleep(0.2)

        if port_is_open(self.cfg.tts_host, self.cfg.tts_port):
            self.log(f"[{log_ts()}] ❌ TTS port 仍被占用：{self.cfg.tts_host}:{self.cfg.tts_port}，為了避免沿用舊角色，取消啟動。")
            return
        if port_is_open(self.cfg.llm_host, self.cfg.llm_port):
            self.log(f"[{log_ts()}] ❌ LLM port 仍被占用：{self.cfg.llm_host}:{self.cfg.llm_port}，為了避免沿用舊角色，取消啟動。")
            return

        errors, warnings = validate_profile_assets(self.cfg, ch_path)
        for w in warnings:
            self.log(f"[{log_ts()}] ⚠️ Profile 檢查：{w}")
        if errors:
            self.log(f"[{log_ts()}] ❌ Profile 尚未完整，取消啟動：{ch_path.name}")
            for e in errors:
                self.log(f"[{log_ts()}]   - {e}")
            return

        self.log(f"[{log_ts()}] 使用 runtime conf 啟動，不改寫原始 conf.yaml。")

        # runtime conf
        try:
            runtime_conf, char_cfg = build_runtime_conf(
                open_llm_dir=self.cfg.open_llm_dir,
                character_yaml=ch_path,
                llm_host=self.cfg.llm_host,
                llm_port=self.cfg.llm_port,
                bridge_translate_url=self.cfg.bridge_translate_url,
                llm_provider_env=self.cfg.llm_provider_env,
                llm_default_provider=self.cfg.llm_default_provider,
                openai_model_env=self.cfg.openai_model_env,
                openai_default_model=self.cfg.openai_default_model,
                openai_temp_env=self.cfg.openai_temp_env,
                openai_inject_key_env=self.cfg.openai_inject_key_env,
                openai_api_key_env=self.cfg.openai_api_key_env,
                openai_fallback_key_env=self.cfg.openai_fallback_key_env,
            )
            write_runtime_conf(self.cfg.runtime_conf_path, runtime_conf)

            conf_uid = (char_cfg.get("conf_uid") or "").strip()
            self.log(f"[{log_ts()}] 選取角色：{ch_path.name}")
            self.log(f"[{log_ts()}] runtime conf：{self.cfg.runtime_conf_path}")
            self.log(f"[{log_ts()}] conf_uid：{conf_uid or '(missing)'}（影響 chat_history 分離）")

            # run_id for logs split (LLM/TTS per profile)
            ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            self.current_run_id = f"{ts}_{conf_uid or ch_path.stem}"
            self.log(f"[{log_ts()}] run_id：{self.current_run_id}（影響 launcher_logs 分流）")

        except Exception as e:
            self.log(f"[{log_ts()}] 生成 runtime conf 失敗：{e}")
            return

        # TTS
        try:
            self.proc_tts = start_tts(self.cfg, self.log, character_name=ch_path.stem, logs_root=self.cfg.logs_dir, run_id=self.current_run_id)
        except Exception as e:
            self.log(f"[{log_ts()}] TTS 啟動失敗：{e}")
            return

        for _ in range(50):
            if port_is_open(self.cfg.tts_host, self.cfg.tts_port, 0.2):
                break
            time.sleep(0.2)

        if not port_is_open(self.cfg.tts_host, self.cfg.tts_port):
            self.log(f"[{log_ts()}] TTS 狀態：未就緒（看 tts.err.log）")
            return

        self.log(f"[{log_ts()}] TTS port 已就緒，開始 smoke test...")
        ok, msg = probe_tts(self.cfg, char_cfg, logs_root=self.cfg.logs_dir, run_id=self.current_run_id)
        if ok:
            self.log(f"[{log_ts()}] TTS smoke test：{msg}")
        else:
            self.log(f"[{log_ts()}] ❌ TTS smoke test 失敗：{msg}")
            self.on_stop_profile(silent=True)
            return

        # LLM
        try:
            self.proc_llm = start_llm(self.cfg, self.log, logs_root=self.cfg.logs_dir, run_id=self.current_run_id)
        except Exception as e:
            self.log(f"[{log_ts()}] LLM 啟動失敗：{e}")
            return

        for _ in range(70):
            if port_is_open(self.cfg.llm_host, self.cfg.llm_port, 0.2):
                break
            time.sleep(0.25)

        if port_is_open(self.cfg.llm_host, self.cfg.llm_port):
            self.log(f"[{log_ts()}] LLM 已就緒：{self.cfg.llm_url}")
            self.on_open_electron()
        else:
            self.log(f"[{log_ts()}] ⚠️ LLM 尚未就緒，請看 llm.err.log 或稍後再按『打開桌面版』/『Web UI』。")

    def on_stop_profile(self, silent: bool = False):
        # stop managed procs
        if self.proc_llm:
            try:
                self.proc_llm.stop()
                if not silent:
                    self.log(f"[{log_ts()}] 已停止 LLM")
            except Exception:
                pass
            self.proc_llm = None

        if self.proc_tts:
            try:
                self.proc_tts.stop()
                if not silent:
                    self.log(f"[{log_ts()}] 已停止 TTS")
            except Exception:
                pass
            self.proc_tts = None

        # kill by port as fallback
        pid_llm = get_listening_pid_windows(self.cfg.llm_port)
        if pid_llm:
            try:
                taskkill_tree(pid_llm)
                if not silent:
                    self.log(f"[{log_ts()}] 已 taskkill LLM PID={pid_llm}")
            except Exception:
                pass

        pid_tts = get_listening_pid_windows(self.cfg.tts_port)
        if pid_tts:
            try:
                taskkill_tree(pid_tts)
                if not silent:
                    self.log(f"[{log_ts()}] 已 taskkill TTS PID={pid_tts}")
            except Exception:
                pass

    # ----------------- Actions -----------------
    def on_test_translate(self):
        def _run():
            if not port_is_open(self.cfg.bridge_host, self.cfg.bridge_port):
                self.log(f"[{log_ts()}] ❌ Bridge 未啟動，無法測試。")
                return
            try:
                resp = http_post_json(self.cfg.bridge_debug_url, {"text": "Hello, test translate."}, timeout_s=12)
                self.log(f"[{log_ts()}] translate_debug => {resp}")
            except Exception as e:
                self.log(f"[{log_ts()}] translate_debug 失敗：{e}（看 bridge.err.log）")

        threading.Thread(target=_run, daemon=True).start()
    # UI callback alias (for compatibility with newer UI labels)
    def on_translate_debug(self):
        """Alias of on_test_translate() for the UI button."""
        return self.on_test_translate()


    def on_open_electron(self):
        try:
            if self.cfg.electron_lnk.exists():
                os.startfile(str(self.cfg.electron_lnk))
                self.log(f"[{log_ts()}] 已啟動桌面版：{self.cfg.electron_lnk}")
            else:
                self.log(f"[{log_ts()}] ⚠️ 找不到桌面版捷徑：{self.cfg.electron_lnk}（改用 Web UI）")
                webbrowser.open(self.cfg.llm_url)
        except Exception as e:
            self.log(f"[{log_ts()}] 啟動桌面版失敗：{e}（改用 Web UI）")
            try:
                webbrowser.open(self.cfg.llm_url)
            except Exception:
                pass

    def on_open_logs_dir(self):
        try:
            self.cfg.logs_dir.mkdir(parents=True, exist_ok=True)
            os.startfile(str(self.cfg.logs_dir))
        except Exception:
            self.log(f"[{log_ts()}] 無法打開 logs 資料夾：{self.cfg.logs_dir}")


    def on_open_logs(self):
        """Backward-compatible alias."""
        return self.on_open_logs_dir()



def main():
    here = Path(__file__).parent.resolve()
    cfg_path = here / "kuro_launcher.settings.yaml"

    # Print minimal startup info first (before reading config)
    print(f"[launcher] start: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[launcher] cwd  : {Path.cwd()}")
    print(f"[launcher] here : {here}")
    print(f"[launcher] cfg  : {cfg_path}")

    for env_path, override in ((here / ".env", False), (here / ".env.local", True)):
        try:
            loaded = load_env_file(env_path, override=override)
            if loaded:
                print(f"[launcher] env  : loaded {env_path.name} ({loaded} vars)")
        except Exception as e:
            print(f"[launcher][WARN] failed to load {env_path.name}: {e}")

    # Keep bridge and LLM usable when only one OpenAI key variable is set locally.
    if os.environ.get("OPENAI_LLM_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = os.environ["OPENAI_LLM_API_KEY"]
    if os.environ.get("OPENAI_API_KEY") and not os.environ.get("OPENAI_LLM_API_KEY"):
        os.environ["OPENAI_LLM_API_KEY"] = os.environ["OPENAI_API_KEY"]

    if not cfg_path.exists():
        msg = f"找不到：{cfg_path}\n請確認把 kuro_launcher.settings.yaml 放在 launcher.py 同資料夾。"
        print(f"[launcher][ERROR] {msg}")
        try:
            r = tk.Tk(); r.withdraw()
            messagebox.showerror("缺少設定檔", msg)
            r.destroy()
        except Exception:
            pass
        return

    cfg = load_config(cfg_path)

    # Runtime console tee -> launcher/YYYY/MM/DD/launcher.combined.log (daily aggregate)
    try:
        ldir = build_logs_dir(cfg.logs_dir, "launcher", run_id=None, aggregate_daily=True)
        log_path = _setup_runtime_logging(ldir)
    except Exception:
        log_path = _setup_runtime_logging(cfg.logs_dir)
    print(f"[launcher] log  : {log_path}")
    print(f"[launcher] cfg.logs_dir: {cfg.logs_dir}")

    app = LauncherApp(cfg)
    print("[launcher] UI created, entering mainloop...")
    app.mainloop()

if __name__ == "__main__":
    try:
        main()
    except Exception:
        _write_crash_log()
        import traceback
        traceback.print_exc()
        try:
            r = tk.Tk(); r.withdraw()
            messagebox.showerror(
                "Launcher 崩潰",
                "啟動時發生錯誤，已寫入桌面 crash log 與 console log。\n\n請把錯誤回傳給我。",
            )
            r.destroy()
        except Exception:
            pass
