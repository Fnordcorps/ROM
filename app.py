"""
ROM – main application window.
"""

import os
import sys
import threading
import customtkinter as ctk
from tkinter import filedialog

import webbrowser

from theme import COLORS, FONTS, RADIUS, PADDING

APP_VERSION = "1.0.0"
GITHUB_URL = "https://github.com/Fnordcorps/ROM"
from scanner import scan_roms, ScanResult, RomEntry
from mover import move_roms, delete_roms, get_media_files_for_entries


def _format_size(size_bytes: int) -> str:
    """Human-readable file size."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.0f} KB"
    elif size_bytes < 1024 ** 3:
        return f"{size_bytes / 1024**2:.1f} MB"
    else:
        return f"{size_bytes / 1024**3:.2f} GB"


def _app_base_dir() -> str:
    """Return the directory next to the exe (frozen) or script (dev)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _bundled_dir() -> str | None:
    """Return the PyInstaller _MEIPASS temp dir, or None."""
    return getattr(sys, "_MEIPASS", None)


def _find_asset(filename: str) -> str | None:
    """Find an asset file – checks next to exe/script first, then bundled."""
    path = os.path.join(_app_base_dir(), filename)
    if os.path.isfile(path):
        return path
    meipass = _bundled_dir()
    if meipass:
        path = os.path.join(meipass, filename)
        if os.path.isfile(path):
            return path
    return None


class ProgressOverlay:
    """Semi-transparent overlay with status text and animated spinner."""

    SPINNER_CHARS = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, parent: ctk.CTk):
        self._parent = parent
        self._frame = None
        self._label = None
        self._detail_label = None
        self._spinner_idx = 0
        self._anim_id = None

    def show(self, text: str = "Working...", detail: str = ""):
        if self._frame is not None:
            self.update(text, detail)
            return
        self._frame = ctk.CTkFrame(
            self._parent, fg_color=COLORS["bg_primary"],
            corner_radius=0,
        )
        self._frame.place(relx=0, rely=0, relwidth=1, relheight=1)

        inner = ctk.CTkFrame(self._frame, fg_color=COLORS["bg_card"], corner_radius=RADIUS["card"])
        inner.place(relx=0.5, rely=0.45, anchor="center")

        self._label = ctk.CTkLabel(
            inner, text=f"{self.SPINNER_CHARS[0]}  {text}",
            font=FONTS["heading_medium"], text_color=COLORS["accent"],
        )
        self._label.pack(padx=40, pady=(24, 4))

        self._detail_label = ctk.CTkLabel(
            inner, text=detail,
            font=FONTS["body_small"], text_color=COLORS["text_secondary"],
        )
        self._detail_label.pack(padx=40, pady=(0, 24))

        self._text = text
        self._spinner_idx = 0
        self._animate()

    def update(self, text: str | None = None, detail: str | None = None):
        if text is not None:
            self._text = text
        if detail is not None and self._detail_label:
            self._detail_label.configure(text=detail)

    def hide(self):
        if self._anim_id is not None:
            self._parent.after_cancel(self._anim_id)
            self._anim_id = None
        if self._frame is not None:
            self._frame.destroy()
            self._frame = None

    def _animate(self):
        if self._frame is None or self._label is None:
            return
        self._spinner_idx = (self._spinner_idx + 1) % len(self.SPINNER_CHARS)
        char = self.SPINNER_CHARS[self._spinner_idx]
        self._label.configure(text=f"{char}  {self._text}")
        self._anim_id = self._parent.after(100, self._animate)


class App(ctk.CTk):
    """Main application window."""

    def __init__(self):
        super().__init__()

        # ── Window setup ────────────────────────────────────────────────
        self.title("ROM")
        self.geometry("1100x780")
        self.minsize(900, 600)
        self.configure(fg_color=COLORS["bg_primary"])

        icon_path = _find_asset("icon.ico")
        if icon_path:
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # ── State ───────────────────────────────────────────────────────
        self.rom_root: str | None = None
        self.scan_result: ScanResult | None = None
        self.check_vars: dict[str, ctk.BooleanVar] = {}   # key = file_path
        self.entry_map: dict[str, RomEntry] = {}           # key = file_path
        self.group_widgets: list = []
        self._debug_visible = True
        self._scan_cancel: threading.Event | None = None

        # View mode
        self._view_mode: str = "duplicates"   # "duplicates" or "manage"
        self._scan_done: bool = False
        self._render_mode: str = "duplicates"

        # Pagination state
        self._sorted_groups: list = []         # current (possibly filtered) sorted group list
        self._current_page: int = 0            # current page (0-indexed)
        self._per_page: int = 50               # items per page

        # Search debounce
        self._filter_after_id = None

        # Progress overlay
        self._overlay = ProgressOverlay(self)

        # ── Build UI ────────────────────────────────────────────────────
        self._build_header()
        self._build_stats_bar()
        self._build_game_list()
        self._build_action_bar()
        self._build_debug_panel()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)


    # ================================================================
    # Header (with optional banner image)
    # ================================================================
    def _build_header(self):
        HEADER_H = 80
        self._header_h = HEADER_H
        self._banner_ctk_img = None  # keep reference to prevent GC

        header = ctk.CTkFrame(self, fg_color=COLORS["bg_secondary"], corner_radius=0, height=HEADER_H)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        header.grid_propagate(False)
        self._header_frame = header

        # Banner background label (fills the header, image or plain colour)
        banner_path = _find_asset("banner.png")
        self._banner_pil = None
        if banner_path:
            try:
                from PIL import Image
                self._banner_pil = Image.open(banner_path)
                self._banner_pil.load()
            except Exception as e:
                self._banner_pil = None
                self._banner_load_err = str(e)

        self._banner_bg = ctk.CTkLabel(header, text="", fg_color=COLORS["bg_secondary"])
        self._banner_bg.grid(row=0, column=0, sticky="nsew")
        header.grid_rowconfigure(0, weight=1)

        if self._banner_pil:
            header.bind("<Configure>", self._resize_banner)
            self.after(100, self._resize_banner)

        # Buttons placed directly on banner label (no title – user's banner has it)
        self.folder_btn = ctk.CTkButton(
            self._banner_bg, text="Select Folder", font=FONTS["body"],
            fg_color=COLORS["btn_primary"], hover_color=COLORS["btn_primary_hover"],
            corner_radius=RADIUS["button"], height=36, width=130,
            command=self._on_select_folder,
        )

        self.scan_btn = ctk.CTkButton(
            self._banner_bg, text="Scan", font=FONTS["body"],
            fg_color=COLORS["accent"], hover_color=COLORS["accent_dark"],
            text_color="#000000", text_color_disabled="#000000",
            corner_radius=RADIUS["button"], height=36, width=80,
            command=self._on_scan, state="disabled",
        )

        self.cancel_btn = ctk.CTkButton(
            self._banner_bg, text="Cancel", font=FONTS["body"],
            fg_color=COLORS["btn_danger"], hover_color=COLORS["btn_danger_hover"],
            corner_radius=RADIUS["button"], height=36, width=80,
            command=self._on_cancel_scan,
        )

        self._layout_header_buttons(show_cancel=False)

    def _layout_header_buttons(self, show_cancel: bool = False):
        """Position header buttons flush-right, bottom of header."""
        pad = PADDING["page"]
        if show_cancel:
            self.cancel_btn.place(relx=1.0, rely=1.0, anchor="se", x=-pad, y=-10)
            self.scan_btn.place(relx=1.0, rely=1.0, anchor="se", x=-(pad + 90), y=-10)
            self.folder_btn.place(relx=1.0, rely=1.0, anchor="se", x=-(pad + 180), y=-10)
        else:
            self.cancel_btn.place_forget()
            self.scan_btn.place(relx=1.0, rely=1.0, anchor="se", x=-pad, y=-10)
            self.folder_btn.place(relx=1.0, rely=1.0, anchor="se", x=-(pad + 90), y=-10)

    def _resize_banner(self, event=None):
        """Resize the banner image to fill the header width."""
        w = self._header_frame.winfo_width()
        if w < 10 or self._banner_pil is None:
            return
        try:
            from PIL import Image
            img = self._banner_pil.resize((w, self._header_h), Image.LANCZOS)
            self._banner_ctk_img = ctk.CTkImage(light_image=img, dark_image=img,
                                                 size=(w, self._header_h))
            self._banner_bg.configure(image=self._banner_ctk_img)
        except Exception as e:
            self._debug_log(f"Banner resize error: {e}")

    # ================================================================
    # Stats / Search / Filter bar + Mode tabs
    # ================================================================
    def _build_stats_bar(self):
        # Top border line
        ctk.CTkFrame(self, fg_color=COLORS["border_stats_bar"], corner_radius=0,
                      height=2).grid(row=1, column=0, sticky="ew")

        bar = ctk.CTkFrame(self, fg_color=COLORS["bg_secondary"], corner_radius=0,
                           height=110)
        bar.grid(row=2, column=0, sticky="ew")

        # Bottom border line
        ctk.CTkFrame(self, fg_color=COLORS["border_stats_bar"], corner_radius=0,
                      height=2).grid(row=3, column=0, sticky="ew")
        bar.grid_columnconfigure(0, weight=1)
        bar.grid_propagate(False)
        self._stats_bar = bar

        # ── Row 0: Path + Search / Sort / System (single row) ─────
        filter_row = ctk.CTkFrame(bar, fg_color="transparent")
        filter_row.grid(row=0, column=0, sticky="ew", padx=PADDING["page"], pady=(4, 0))
        filter_row.grid_columnconfigure(3, weight=1)

        self.path_label = ctk.CTkLabel(
            filter_row, text="NO ROMS FOLDER SELECTED",
            font=FONTS["heading_small"],
            text_color=COLORS["text_secondary"], anchor="w",
        )
        self.path_label.grid(row=0, column=0, sticky="w", columnspan=4)

        self._about_btn = ctk.CTkLabel(
            bar, text="ABOUT", font=FONTS["status"],
            text_color=COLORS["accent"], cursor="hand2",
        )
        self._about_btn.place(relx=0.5, y=12, anchor="n")
        self._about_btn.bind("<Button-1>", lambda e: self._show_about_dialog())

        self.stats_label = ctk.CTkLabel(
            filter_row, text="", font=FONTS["body_small"],
            text_color=COLORS["text_secondary"],
        )
        self.stats_label.grid(row=0, column=4, sticky="e", columnspan=4)

        self.search_entry = ctk.CTkEntry(
            filter_row,
            font=FONTS["body_small"], height=28, width=220,
            fg_color=COLORS["bg_input"], border_color=COLORS["border_input"],
            corner_radius=RADIUS["input"], placeholder_text="Search games...",
            placeholder_text_color="#888888",
        )
        self.search_entry.grid(row=1, column=0, sticky="w", pady=(2, 0))
        self.search_entry.bind("<KeyRelease>", lambda e: self._on_filter_changed())

        ctk.CTkLabel(filter_row, text="Sort:", font=FONTS["body_small"],
                      text_color=COLORS["text_secondary"]
        ).grid(row=1, column=1, padx=(12, 6), pady=(2, 0))

        self.sort_var = ctk.StringVar(value="A \u2192 Z")
        self.sort_dropdown = ctk.CTkOptionMenu(
            filter_row, variable=self.sort_var,
            values=["A \u2192 Z", "Z \u2192 A", "Size \u2193", "Size \u2191", "Most copies"],
            font=FONTS["body_small"], dropdown_font=FONTS["body_small"],
            height=28, width=140,
            fg_color=COLORS["bg_input"], button_color=COLORS["border_input"],
            button_hover_color=COLORS["bg_card_hover"],
            dropdown_fg_color=COLORS["bg_card"],
            dropdown_hover_color=COLORS["bg_card_hover"],
            corner_radius=RADIUS["input"],
            command=lambda _: self._apply_filter(),
        )
        self.sort_dropdown.grid(row=1, column=2, pady=(2, 0))

        ctk.CTkLabel(filter_row, text="System:", font=FONTS["body_small"],
                      text_color=COLORS["text_secondary"]
        ).grid(row=1, column=3, padx=(16, 6), sticky="e", pady=(2, 0))

        self.system_var = ctk.StringVar(value="All Systems")
        self.system_dropdown = ctk.CTkComboBox(
            filter_row, variable=self.system_var,
            values=["All Systems"],
            font=FONTS["body_small"], dropdown_font=FONTS["body_small"],
            height=28, width=160,
            fg_color=COLORS["bg_input"], border_color=COLORS["border_input"],
            button_color=COLORS["border_input"],
            button_hover_color=COLORS["bg_card_hover"],
            dropdown_fg_color=COLORS["bg_card"],
            dropdown_hover_color=COLORS["bg_card_hover"],
            corner_radius=RADIUS["input"],
            command=lambda _: self._apply_filter(),
            state="readonly",
        )
        self.system_dropdown.grid(row=1, column=4, pady=(2, 0))

        # "Unscraped only" checkbox (visible in MANAGE mode only)
        self._unscraped_var = ctk.BooleanVar(value=False)
        self._unscraped_cb = ctk.CTkCheckBox(
            filter_row, text="Unscraped only", variable=self._unscraped_var,
            font=FONTS["body_small"], text_color=COLORS["text_secondary"],
            fg_color=COLORS["accent"], hover_color=COLORS["accent_dark"],
            border_color=COLORS["border_input"], corner_radius=4,
            checkbox_width=18, checkbox_height=18,
            command=self._apply_filter,
        )
        self._unscraped_cb.grid(row=1, column=5, padx=(16, 0), pady=(2, 0))
        self._unscraped_cb.grid_remove()  # hidden until MANAGE mode

        # ── Row 1: Mode tabs (left) + Pagination (right) ─────────
        tab_row = ctk.CTkFrame(bar, fg_color="transparent")
        tab_row.grid(row=1, column=0, sticky="ew", padx=PADDING["page"], pady=(2, 2))
        tab_row.grid_columnconfigure(2, weight=1)   # spacer between tabs and pagination

        self._manage_tab_btn = ctk.CTkButton(
            tab_row, text="MANAGE", font=FONTS["status"],
            fg_color=COLORS["bg_card"], hover_color=COLORS["bg_card_hover"],
            text_color=COLORS["text_secondary"],
            corner_radius=RADIUS["button"], height=32, width=120,
            command=lambda: self._switch_mode("manage"),
            state="disabled",
        )
        self._manage_tab_btn.grid(row=0, column=0, padx=(0, 6))

        self._duplicates_tab_btn = ctk.CTkButton(
            tab_row, text="DUPLICATES", font=FONTS["status"],
            fg_color=COLORS["accent"], hover_color=COLORS["accent_dark"],
            text_color="#ffffff",
            corner_radius=RADIUS["button"], height=32, width=120,
            command=lambda: self._switch_mode("duplicates"),
            state="disabled",
        )
        self._duplicates_tab_btn.grid(row=0, column=1)

        # ── Pagination controls (right side of tab row) ──────
        pag_frame = ctk.CTkFrame(tab_row, fg_color="transparent")
        pag_frame.grid(row=0, column=3, sticky="e")
        self._pag_frame = pag_frame

        # Per-page selector
        ctk.CTkLabel(pag_frame, text="Per page:", font=FONTS["body_small"],
                      text_color=COLORS["text_secondary"]
        ).grid(row=0, column=0, padx=(0, 4))

        self._per_page_var = ctk.StringVar(value="50")
        per_page_menu = ctk.CTkOptionMenu(
            pag_frame, variable=self._per_page_var,
            values=["25", "50", "100", "200"],
            font=FONTS["body_small"], dropdown_font=FONTS["body_small"],
            height=28, width=70,
            fg_color=COLORS["bg_input"], button_color=COLORS["border_input"],
            button_hover_color=COLORS["bg_card_hover"],
            dropdown_fg_color=COLORS["bg_card"],
            dropdown_hover_color=COLORS["bg_card_hover"],
            corner_radius=RADIUS["input"],
            command=self._on_per_page_changed,
        )
        per_page_menu.grid(row=0, column=1, padx=(0, 12))

        # Page navigation buttons container
        self._page_nav_frame = ctk.CTkFrame(pag_frame, fg_color="transparent")
        self._page_nav_frame.grid(row=0, column=2)

    # ================================================================
    # Mode switching
    # ================================================================
    def _switch_mode(self, mode: str):
        """Switch between 'duplicates' and 'manage' views."""
        if mode == self._view_mode:
            return
        self._view_mode = mode

        if mode == "manage":
            self._manage_tab_btn.configure(
                fg_color=COLORS["accent"], hover_color=COLORS["accent_dark"],
                text_color="#ffffff",
            )
            self._duplicates_tab_btn.configure(
                fg_color=COLORS["bg_card"], hover_color=COLORS["bg_card_hover"],
                text_color=COLORS["text_secondary"],
            )
            self.sort_dropdown.configure(values=["A \u2192 Z", "Z \u2192 A", "Size \u2193", "Size \u2191"])
            if self.sort_var.get() == "Most copies":
                self.sort_var.set("A \u2192 Z")
            self._unscraped_cb.grid()
        else:
            self._duplicates_tab_btn.configure(
                fg_color=COLORS["accent"], hover_color=COLORS["accent_dark"],
                text_color="#ffffff",
            )
            self._manage_tab_btn.configure(
                fg_color=COLORS["bg_card"], hover_color=COLORS["bg_card_hover"],
                text_color=COLORS["text_secondary"],
            )
            self.sort_dropdown.configure(
                values=["A \u2192 Z", "Z \u2192 A", "Size \u2193", "Size \u2191", "Most copies"]
            )
            self._unscraped_var.set(False)
            self._unscraped_cb.grid_remove()

        self._current_page = 0
        self._populate_system_dropdown()
        self._apply_filter()

    def _populate_system_dropdown(self):
        """Populate the system filter dropdown based on current view mode."""
        if not self.scan_result:
            return

        all_systems = set()
        if self._view_mode == "duplicates":
            for entries in self.scan_result.duplicates.values():
                for e in entries:
                    all_systems.add(e.system)
        else:
            for entries in self.scan_result.all_games.values():
                for e in entries:
                    all_systems.add(e.system)

        system_list = ["All Systems"] + sorted(all_systems, key=str.lower)
        self.system_dropdown.configure(values=system_list)
        self.system_var.set("All Systems")

    # ================================================================
    # Game list (scrollable)
    # ================================================================
    def _build_game_list(self):
        self.list_frame = ctk.CTkScrollableFrame(
            self, fg_color=COLORS["bg_primary"],
            scrollbar_button_color=COLORS["bg_card"],
            scrollbar_button_hover_color=COLORS["bg_card_hover"],
        )
        self.list_frame.grid(row=4, column=0, sticky="nsew", padx=0, pady=0)
        self.list_frame.grid_columnconfigure(0, weight=1)

        self.placeholder = ctk.CTkLabel(
            self.list_frame,
            text="Select a ROM folder and click Scan to begin.",
            font=FONTS["body"], text_color=COLORS["text_secondary"],
        )
        self.placeholder.grid(row=0, column=0, pady=60)

    # ================================================================
    # Action bar
    # ================================================================
    def _build_action_bar(self):
        bar = ctk.CTkFrame(self, fg_color=COLORS["bg_secondary"], corner_radius=0, height=50)
        bar.grid(row=5, column=0, sticky="ew")
        bar.grid_columnconfigure(1, weight=1)

        left = ctk.CTkFrame(bar, fg_color="transparent")
        left.grid(row=0, column=0, padx=PADDING["page"], pady=8)

        self.sel_all_btn = ctk.CTkButton(
            left, text="Select All", font=FONTS["body_small"],
            fg_color=COLORS["bg_card"], hover_color=COLORS["bg_card_hover"],
            corner_radius=RADIUS["button"], height=32, width=100,
            command=self._select_all, state="disabled",
        )
        self.sel_all_btn.grid(row=0, column=0, padx=(0, 6))

        self.desel_btn = ctk.CTkButton(
            left, text="Deselect All", font=FONTS["body_small"],
            fg_color=COLORS["bg_card"], hover_color=COLORS["bg_card_hover"],
            corner_radius=RADIUS["button"], height=32, width=100,
            command=self._deselect_all, state="disabled",
        )
        self.desel_btn.grid(row=0, column=1)

        self.selected_label = ctk.CTkLabel(
            bar, text="0 selected", font=FONTS["body_small"],
            text_color=COLORS["text_secondary"],
        )
        self.selected_label.grid(row=0, column=1, pady=8)

        right = ctk.CTkFrame(bar, fg_color="transparent")
        right.grid(row=0, column=2, padx=PADDING["page"], pady=8)

        self.move_btn = ctk.CTkButton(
            right, text="Move Selected  \u25b6", font=FONTS["status"],
            fg_color=COLORS["btn_primary"], hover_color=COLORS["btn_primary_hover"],
            corner_radius=RADIUS["button"], height=36, width=160,
            command=self._on_move, state="disabled",
        )
        self.move_btn.grid(row=0, column=0, padx=(0, 8))

        self.delete_btn = ctk.CTkButton(
            right, text="Delete Selected  \u2715", font=FONTS["status"],
            fg_color=COLORS["btn_danger"], hover_color=COLORS["btn_danger_hover"],
            corner_radius=RADIUS["button"], height=36, width=170,
            command=self._on_delete, state="disabled",
        )
        self.delete_btn.grid(row=0, column=1)

    # ================================================================
    # Debug panel
    # ================================================================
    def _build_debug_panel(self):
        wrapper = ctk.CTkFrame(self, fg_color=COLORS["bg_secondary"], corner_radius=0)
        wrapper.grid(row=6, column=0, sticky="ew")
        wrapper.grid_columnconfigure(0, weight=1)

        toggle_btn = ctk.CTkButton(
            wrapper, text="\u25bc  Debug Log", font=FONTS["body_small"],
            fg_color="transparent", hover_color=COLORS["bg_card"],
            text_color=COLORS["text_secondary"], anchor="w",
            height=28, command=self._toggle_debug,
        )
        toggle_btn.grid(row=0, column=0, sticky="ew", padx=PADDING["page"], pady=(4, 0))
        self._debug_toggle_btn = toggle_btn

        self.debug_text = ctk.CTkTextbox(
            wrapper, font=FONTS["mono_small"], height=150,
            fg_color=COLORS["bg_primary"], text_color=COLORS["text_secondary"],
            border_color=COLORS["border_default"], border_width=1,
            corner_radius=RADIUS["input"], state="disabled", wrap="word",
        )
        self.debug_text.grid(row=1, column=0, sticky="ew", padx=PADDING["page"], pady=(2, 8))

    def _toggle_debug(self):
        if self._debug_visible:
            self.debug_text.grid_remove()
            self._debug_toggle_btn.configure(text="\u25b6  Debug Log")
        else:
            self.debug_text.grid()
            self._debug_toggle_btn.configure(text="\u25bc  Debug Log")
        self._debug_visible = not self._debug_visible

    def _debug_log(self, msg: str):
        def _append():
            self.debug_text.configure(state="normal")
            self.debug_text.insert("end", msg + "\n")
            self.debug_text.see("end")
            self.debug_text.configure(state="disabled")
        self.after(0, _append)

    # ================================================================
    # About dialog
    # ================================================================
    def _show_about_dialog(self):
        """Show the About dialog with app info and GitHub link."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("About ROM")
        dialog.geometry("360x180")
        dialog.configure(fg_color=COLORS["bg_primary"])
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        self.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 360) // 2
        y = self.winfo_y() + (self.winfo_height() - 180) // 2
        dialog.geometry(f"+{x}+{y}")

        ctk.CTkLabel(
            dialog, text="ROM", font=FONTS["heading_large"],
            text_color=COLORS["accent"],
        ).pack(pady=(24, 2))

        ctk.CTkLabel(
            dialog, text="by FNORDCORPS", font=FONTS["body"],
            text_color=COLORS["text_primary"],
        ).pack(pady=(0, 2))

        ctk.CTkLabel(
            dialog, text=f"v{APP_VERSION}", font=FONTS["body"],
            text_color=COLORS["text_secondary"],
        ).pack(pady=(0, 8))

        link = ctk.CTkLabel(
            dialog, text=GITHUB_URL, font=FONTS["body_small"],
            text_color=COLORS["status_info"], cursor="hand2",
        )
        link.pack(pady=(0, 16))
        link.bind("<Button-1>", lambda e: webbrowser.open(GITHUB_URL))

    # ================================================================
    # Folder selection
    # ================================================================
    def _on_select_folder(self):
        path = filedialog.askdirectory(title="Select ROM Root Folder")
        if path:
            self.rom_root = path
            self.path_label.configure(text=path)
            self.scan_btn.configure(state="normal")
            self._debug_log(f"Selected folder: {path}")

    # ================================================================
    # Pre-scan confirmation popup
    # ================================================================
    def _show_prescan_popup(self, on_continue):
        """Show a reminder to update gamelists before scanning."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Before Scanning")
        dialog.geometry("480x180")
        dialog.configure(fg_color=COLORS["bg_primary"])
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        self.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 480) // 2
        y = self.winfo_y() + (self.winfo_height() - 180) // 2
        dialog.geometry(f"+{x}+{y}")

        ctk.CTkLabel(
            dialog,
            text="FOR BEST RESULTS\nENSURE GAMELISTS ARE UP TO DATE",
            font=FONTS["heading_medium"], text_color=COLORS["accent"],
            justify="center",
        ).pack(padx=20, pady=(28, 20))

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=(0, 16))

        ctk.CTkButton(
            btn_frame, text="Cancel", font=FONTS["body"],
            fg_color=COLORS["bg_card"], hover_color=COLORS["bg_card_hover"],
            corner_radius=RADIUS["button"], height=34, width=100,
            command=dialog.destroy,
        ).grid(row=0, column=0, padx=(0, 12))

        def _continue():
            dialog.destroy()
            on_continue()

        ctk.CTkButton(
            btn_frame, text="Continue", font=FONTS["status"],
            fg_color=COLORS["accent"], hover_color=COLORS["accent_dark"],
            text_color="#ffffff",
            corner_radius=RADIUS["button"], height=34, width=120,
            command=_continue,
        ).grid(row=0, column=1)

    # ================================================================
    # Scan
    # ================================================================
    def _on_scan(self):
        if not self.rom_root:
            return

        # Show pre-scan popup (skip on re-scan after move/delete)
        if self._scan_done:
            self._start_scan()
        else:
            self._show_prescan_popup(self._start_scan)

    def _start_scan(self):
        """Actually begin the scan (called after popup confirmation or on re-scan)."""
        self._scan_cancel = threading.Event()
        self.scan_btn.configure(state="disabled", text="Scanning...")
        self._layout_header_buttons(show_cancel=True)
        self.folder_btn.configure(state="disabled")
        self._clear_game_list()
        self.stats_label.configure(text="Scanning...")

        self._overlay.show("Scanning ROM folders...", "Reading gamelist.xml files across all systems")

        cancel = self._scan_cancel

        def _run():
            result = scan_roms(self.rom_root, on_progress=self._debug_log, cancel_event=cancel)
            if not cancel.is_set():
                self.after(0, lambda: self._on_scan_phase2(result))
            else:
                self.after(0, self._on_scan_cancelled)

        threading.Thread(target=_run, daemon=True).start()

    def _on_scan_phase2(self, result: ScanResult):
        """Scan done – now sort & prepare groups (still show overlay)."""
        self._overlay.update("Analysing duplicates...",
                             f"Found {result.total_duplicate_groups} groups across "
                             f"{result.total_games} games")
        self.scan_result = result

        def _sort():
            sorted_groups = sorted(
                result.duplicates.items(),
                key=lambda kv: kv[1][0].display_name.lower(),
            )
            self.after(0, lambda: self._on_scan_complete(result, sorted_groups))

        threading.Thread(target=_sort, daemon=True).start()

    def _on_scan_complete(self, result: ScanResult, sorted_groups: list):
        self.scan_btn.configure(state="normal", text="Scan")
        # Darken the scan button after first scan
        self.scan_btn.configure(
            fg_color=COLORS["accent_dark"],
            hover_color="#b07a28",
        )
        self._layout_header_buttons(show_cancel=False)
        self.folder_btn.configure(state="normal")
        self.sel_all_btn.configure(state="normal")
        self.desel_btn.configure(state="normal")
        self._scan_cancel = None

        # Enable mode tabs
        self._scan_done = True
        self._manage_tab_btn.configure(state="normal")
        self._duplicates_tab_btn.configure(state="normal")

        # Switch to MANAGE mode on first scan
        if self._view_mode != "manage":
            self._view_mode = "manage"
            self._manage_tab_btn.configure(
                fg_color=COLORS["accent"], hover_color=COLORS["accent_dark"],
                text_color="#ffffff",
            )
            self._duplicates_tab_btn.configure(
                fg_color=COLORS["bg_card"], hover_color=COLORS["bg_card_hover"],
                text_color=COLORS["text_secondary"],
            )
            self.sort_dropdown.configure(values=["A \u2192 Z", "Z \u2192 A", "Size \u2193", "Size \u2191"])
            if self.sort_var.get() == "Most copies":
                self.sort_var.set("A \u2192 Z")
            self._unscraped_cb.grid()

        # Populate system dropdown for current mode
        self._populate_system_dropdown()

        # Update stats
        self.stats_label.configure(
            text=f"{result.total_games} games  \u00b7  "
                 f"{result.total_duplicate_groups} duplicate groups  \u00b7  "
                 f"{result.total_duplicate_files} files across systems"
        )

        self._overlay.update("Loading results...",
                             f"Rendering first {min(self._per_page, len(sorted_groups))} "
                             f"of {len(sorted_groups)} groups")

        self.after(50, self._finish_loading)

    def _finish_loading(self):
        self._apply_filter()
        self._overlay.hide()

    def _on_cancel_scan(self):
        if self._scan_cancel:
            self._scan_cancel.set()
            self._debug_log("Cancelling scan...")

    def _on_scan_cancelled(self):
        self.scan_btn.configure(state="normal", text="Scan")
        self._layout_header_buttons(show_cancel=False)
        self.folder_btn.configure(state="normal")
        self.stats_label.configure(text="Scan cancelled")
        self._scan_cancel = None
        self._overlay.hide()

    # ================================================================
    # Game list population (paginated)
    # ================================================================
    def _clear_game_list(self):
        for w in self.group_widgets:
            w.destroy()
        self.group_widgets.clear()
        self.check_vars.clear()
        self.entry_map.clear()
        self._sorted_groups = []
        self._current_page = 0
        if hasattr(self, "placeholder") and self.placeholder.winfo_exists():
            self.placeholder.destroy()

    def _total_pages(self) -> int:
        if not self._sorted_groups:
            return 1
        return max(1, -(-len(self._sorted_groups) // self._per_page))  # ceil div

    def _populate_game_list(self, sorted_groups: list):
        """Populate with grouped duplicate cards (DUPLICATES mode)."""
        self._clear_game_list()
        self._sorted_groups = sorted_groups
        self._render_mode = "duplicates"

        if not sorted_groups:
            lbl = ctk.CTkLabel(
                self.list_frame, text="No cross-system duplicates found.",
                font=FONTS["body"], text_color=COLORS["text_secondary"],
            )
            lbl.grid(row=0, column=0, pady=60)
            self.group_widgets.append(lbl)
            self._update_page_nav()
            return

        self._render_page()

    def _populate_flat_list(self, entries: list):
        """Populate with flat game rows (MANAGE mode)."""
        self._clear_game_list()
        self._sorted_groups = entries
        self._render_mode = "manage"

        if not entries:
            lbl = ctk.CTkLabel(
                self.list_frame, text="No games found for the selected filters.",
                font=FONTS["body"], text_color=COLORS["text_secondary"],
            )
            lbl.grid(row=0, column=0, pady=60)
            self.group_widgets.append(lbl)
            self._update_page_nav()
            return

        self._render_page()

    def _render_page(self):
        """Render items for the current page only."""
        # Clear current widgets but keep _sorted_groups
        for w in self.group_widgets:
            w.destroy()
        self.group_widgets.clear()
        self.check_vars.clear()
        self.entry_map.clear()

        start = self._current_page * self._per_page
        end = min(start + self._per_page, len(self._sorted_groups))

        if self._render_mode == "duplicates":
            for idx in range(start, end):
                norm_key, entries = self._sorted_groups[idx]
                group_frame = self._create_group_widget(idx, norm_key, entries)
                group_frame.grid(row=idx - start, column=0, sticky="ew", padx=PADDING["page"], pady=(4, 0))
                self.group_widgets.append(group_frame)
        else:
            for idx in range(start, end):
                entry = self._sorted_groups[idx]
                row_frame = self._create_flat_entry_widget(idx, entry)
                row_frame.grid(row=idx - start, column=0, sticky="ew", padx=PADDING["page"], pady=(2, 0))
                self.group_widgets.append(row_frame)

        self._update_page_nav()

        # Scroll to top
        try:
            self.list_frame._parent_canvas.yview_moveto(0)
        except Exception:
            pass

    def _go_to_page(self, page: int):
        """Navigate to a specific page (0-indexed)."""
        total = self._total_pages()
        page = max(0, min(page, total - 1))
        if page == self._current_page:
            return
        self._current_page = page
        self._render_page()

    def _on_per_page_changed(self, value: str):
        """Handle results-per-page dropdown change."""
        self._per_page = int(value)
        self._current_page = 0
        if self._sorted_groups:
            self._render_page()

    def _update_page_nav(self):
        """Rebuild the page navigation buttons."""
        for w in self._page_nav_frame.winfo_children():
            w.destroy()

        total = self._total_pages()
        current = self._current_page

        if total <= 1:
            return

        btn_style = dict(
            font=FONTS["body_small"], corner_radius=RADIUS["button"],
            height=28, width=32,
        )

        # Previous arrow
        prev_btn = ctk.CTkButton(
            self._page_nav_frame, text="\u25c0", **btn_style,
            fg_color=COLORS["bg_card"], hover_color=COLORS["bg_card_hover"],
            text_color=COLORS["text_secondary"],
            command=lambda: self._go_to_page(current - 1),
            state="normal" if current > 0 else "disabled",
        )
        prev_btn.grid(row=0, column=0, padx=1)

        # Build page number list with ellipsis
        pages_to_show = set()
        pages_to_show.add(0)              # first
        pages_to_show.add(total - 1)      # last
        for p in range(max(0, current - 1), min(total, current + 2)):
            pages_to_show.add(p)          # current ± 1

        col = 1
        prev_page = -1
        for page in sorted(pages_to_show):
            if prev_page >= 0 and page - prev_page > 1:
                # Ellipsis
                ctk.CTkLabel(
                    self._page_nav_frame, text="...", font=FONTS["body_small"],
                    text_color=COLORS["text_secondary"], width=24,
                ).grid(row=0, column=col, padx=0)
                col += 1

            is_current = (page == current)
            page_btn = ctk.CTkButton(
                self._page_nav_frame, text=str(page + 1), **btn_style,
                fg_color=COLORS["accent"] if is_current else COLORS["bg_card"],
                hover_color=COLORS["accent_dark"] if is_current else COLORS["bg_card_hover"],
                text_color="#ffffff" if is_current else COLORS["text_secondary"],
                command=(lambda p=page: self._go_to_page(p)),
            )
            page_btn.grid(row=0, column=col, padx=1)
            col += 1
            prev_page = page

        # Next arrow
        next_btn = ctk.CTkButton(
            self._page_nav_frame, text="\u25b6", **btn_style,
            fg_color=COLORS["bg_card"], hover_color=COLORS["bg_card_hover"],
            text_color=COLORS["text_secondary"],
            command=lambda: self._go_to_page(current + 1),
            state="normal" if current < total - 1 else "disabled",
        )
        next_btn.grid(row=0, column=col, padx=1)

    def _create_group_widget(self, idx: int, norm_key: str, entries: list[RomEntry]) -> ctk.CTkFrame:
        """Create a collapsible group card for duplicate ROMs."""
        best_name = max((e.display_name for e in entries), key=len)
        systems = sorted({e.system for e in entries})
        total_size = sum(e.file_size for e in entries)

        card = ctk.CTkFrame(
            self.list_frame, fg_color=COLORS["bg_card"], corner_radius=RADIUS["card"],
        )
        card.grid_columnconfigure(0, weight=1)
        card._expanded = True
        card._content_frame = None

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=PADDING["card"], pady=(PADDING["card"], 4))
        header.grid_columnconfigure(1, weight=1)

        arrow = ctk.CTkLabel(header, text="\u25bc", font=FONTS["body"],
                             text_color=COLORS["text_secondary"], width=20)
        arrow.grid(row=0, column=0, padx=(0, 6))

        name_label = ctk.CTkLabel(
            header, text=best_name, font=FONTS["heading_small"],
            text_color=COLORS["text_heading"], anchor="w",
        )
        name_label.grid(row=0, column=1, sticky="w")

        info_text = f"{len(entries)} copies  \u00b7  {', '.join(systems)}  \u00b7  {_format_size(total_size)}"
        info_label = ctk.CTkLabel(
            header, text=info_text, font=FONTS["body_small"],
            text_color=COLORS["text_secondary"],
        )
        info_label.grid(row=0, column=2, padx=(10, 0))

        def toggle(event=None):
            if card._expanded:
                card._content_frame.grid_remove()
                arrow.configure(text="\u25b6")
            else:
                card._content_frame.grid()
                arrow.configure(text="\u25bc")
            card._expanded = not card._expanded

        for w in (header, arrow, name_label, info_label):
            w.bind("<Button-1>", toggle)
            w.configure(cursor="hand2")

        content = ctk.CTkFrame(card, fg_color="transparent")
        content.grid(row=1, column=0, sticky="ew", padx=PADDING["card"], pady=(0, PADDING["card"]))
        content.grid_columnconfigure(1, weight=1)
        card._content_frame = content

        for i, entry in enumerate(entries):
            var = ctk.BooleanVar(value=False)
            var.trace_add("write", lambda *_: self._update_selected_count())
            self.check_vars[entry.file_path] = var
            self.entry_map[entry.file_path] = entry

            row = ctk.CTkFrame(content, fg_color="transparent")
            row.grid(row=i, column=0, sticky="ew", pady=1)
            row.grid_columnconfigure(1, weight=1)

            ctk.CTkCheckBox(
                row, text="", variable=var, width=24, height=24,
                fg_color=COLORS["btn_primary"], hover_color=COLORS["btn_primary_hover"],
                border_color=COLORS["border_input"], corner_radius=4,
                checkbox_width=20, checkbox_height=20,
            ).grid(row=0, column=0, padx=(12, 8), pady=2)

            ctk.CTkLabel(
                row, text=f"{entry.display_name}  /  {entry.system}",
                font=FONTS["body"], text_color=COLORS["text_primary"], anchor="w",
            ).grid(row=0, column=1, sticky="w")

            ctk.CTkLabel(
                row, text=_format_size(entry.file_size),
                font=FONTS["body_small"], text_color=COLORS["text_secondary"],
            ).grid(row=0, column=2, padx=(10, 12))

        return card

    def _create_flat_entry_widget(self, idx: int, entry: RomEntry) -> ctk.CTkFrame:
        """Create a single-row card for one game (MANAGE mode)."""
        card = ctk.CTkFrame(
            self.list_frame, fg_color=COLORS["bg_card"],
            corner_radius=RADIUS["card"], height=40,
        )
        card.grid_columnconfigure(1, weight=1)

        var = ctk.BooleanVar(value=False)
        var.trace_add("write", lambda *_: self._update_selected_count())
        self.check_vars[entry.file_path] = var
        self.entry_map[entry.file_path] = entry

        ctk.CTkCheckBox(
            card, text="", variable=var, width=24, height=24,
            fg_color=COLORS["btn_primary"], hover_color=COLORS["btn_primary_hover"],
            border_color=COLORS["border_input"], corner_radius=4,
            checkbox_width=20, checkbox_height=20,
        ).grid(row=0, column=0, padx=(PADDING["card"], 8), pady=8)

        ctk.CTkLabel(
            card, text=entry.display_name,
            font=FONTS["body"], text_color=COLORS["text_primary"], anchor="w",
        ).grid(row=0, column=1, sticky="w", pady=8)

        ctk.CTkLabel(
            card, text=entry.system,
            font=FONTS["body_small"], text_color=COLORS["accent"],
            fg_color=COLORS["bg_card_hover"], corner_radius=4,
        ).grid(row=0, column=2, padx=(10, 0), pady=8)

        ctk.CTkLabel(
            card, text=_format_size(entry.file_size),
            font=FONTS["body_small"], text_color=COLORS["text_secondary"],
        ).grid(row=0, column=3, padx=(10, PADDING["card"]), pady=8)

        return card

    # ================================================================
    # Filter / Sort (debounced for text, immediate for dropdowns)
    # ================================================================
    def _on_filter_changed(self):
        """Called on search text change – debounced."""
        if self._filter_after_id is not None:
            self.after_cancel(self._filter_after_id)
        self._filter_after_id = self.after(300, self._apply_filter)

    def _apply_filter(self):
        """Dispatch filtering to the active mode."""
        self._filter_after_id = None
        if not self.scan_result:
            return

        if self._view_mode == "duplicates":
            self._apply_filter_duplicates()
        else:
            self._apply_filter_manage()

    def _apply_filter_duplicates(self):
        """Filter and sort for DUPLICATES mode (grouped cards)."""
        query = self.search_entry.get().lower().strip()
        system_filter = self.system_var.get()
        sort_mode = self.sort_var.get()

        groups = self.scan_result.duplicates

        if system_filter != "All Systems":
            groups = {
                k: v for k, v in groups.items()
                if any(e.system == system_filter for e in v)
            }

        if query:
            groups = {
                k: v for k, v in groups.items()
                if query in k or any(query in e.display_name.lower() for e in v)
            }

        if sort_mode == "Size \u2193":
            sorted_groups = sorted(
                groups.items(),
                key=lambda kv: sum(e.file_size for e in kv[1]),
                reverse=True,
            )
        elif sort_mode == "Size \u2191":
            sorted_groups = sorted(
                groups.items(),
                key=lambda kv: sum(e.file_size for e in kv[1]),
            )
        elif sort_mode == "Most copies":
            sorted_groups = sorted(
                groups.items(),
                key=lambda kv: len(kv[1]),
                reverse=True,
            )
        elif sort_mode == "Z \u2192 A":
            sorted_groups = sorted(
                groups.items(),
                key=lambda kv: kv[1][0].display_name.lower(),
                reverse=True,
            )
        else:
            sorted_groups = sorted(
                groups.items(),
                key=lambda kv: kv[1][0].display_name.lower(),
            )

        total_groups = len(sorted_groups)
        total_files = sum(len(v) for _, v in sorted_groups)
        if query or system_filter != "All Systems":
            self.stats_label.configure(
                text=f"Showing {total_groups} groups ({total_files} files)  \u00b7  "
                     f"of {self.scan_result.total_duplicate_groups} total groups"
            )
        else:
            self.stats_label.configure(
                text=f"{self.scan_result.total_games} games  \u00b7  "
                     f"{self.scan_result.total_duplicate_groups} duplicate groups  \u00b7  "
                     f"{self.scan_result.total_duplicate_files} files across systems"
            )

        self._populate_game_list(sorted_groups)

    def _apply_filter_manage(self):
        """Filter and sort for MANAGE mode (flat game list)."""
        query = self.search_entry.get().lower().strip()
        system_filter = self.system_var.get()
        sort_mode = self.sort_var.get()
        unscraped_only = self._unscraped_var.get()

        flat: list[RomEntry] = []
        for entries in self.scan_result.all_games.values():
            for e in entries:
                if system_filter != "All Systems" and e.system != system_filter:
                    continue
                if query and query not in e.display_name.lower():
                    continue
                if unscraped_only and e.in_gamelist:
                    continue
                flat.append(e)

        if sort_mode == "Size \u2193":
            flat.sort(key=lambda e: e.file_size, reverse=True)
        elif sort_mode == "Size \u2191":
            flat.sort(key=lambda e: e.file_size)
        elif sort_mode == "Z \u2192 A":
            flat.sort(key=lambda e: e.display_name.lower(), reverse=True)
        else:
            flat.sort(key=lambda e: e.display_name.lower())

        total = len(flat)
        has_filter = query or system_filter != "All Systems" or unscraped_only
        if has_filter:
            self.stats_label.configure(text=f"Showing {total} games")
        else:
            unscraped_info = ""
            if self.scan_result.total_unscraped > 0:
                unscraped_info = (f"  \u00b7  {self.scan_result.total_unscraped} "
                                  f"not in gamelists")
            self.stats_label.configure(
                text=f"{self.scan_result.total_games} games across "
                     f"{self.scan_result.total_systems} systems"
                     f"{unscraped_info}"
            )

        self._populate_flat_list(flat)

    # ================================================================
    # Selection helpers
    # ================================================================
    def _get_selected_entries(self) -> list[RomEntry]:
        return [self.entry_map[fp] for fp, var in self.check_vars.items() if var.get()]

    def _update_selected_count(self):
        count = sum(1 for v in self.check_vars.values() if v.get())
        self.selected_label.configure(text=f"{count} selected")
        state = "normal" if count > 0 else "disabled"
        self.move_btn.configure(state=state)
        self.delete_btn.configure(state=state)

    def _select_all(self):
        for var in self.check_vars.values():
            var.set(True)

    def _deselect_all(self):
        for var in self.check_vars.values():
            var.set(False)

    # ================================================================
    # Toast
    # ================================================================
    def _show_toast(self, text: str, color: str, duration: int = 4000):
        toast = ctk.CTkFrame(
            self, fg_color=COLORS["bg_card"], corner_radius=10,
            border_width=2, border_color=color,
        )
        toast.place(relx=1.0, rely=1.0, anchor="se", x=-20, y=-20)
        ctk.CTkLabel(toast, text=text, font=FONTS["status"], text_color=color).pack(padx=16, pady=10)
        self.after(duration, toast.destroy)

    # ================================================================
    # Move
    # ================================================================
    def _on_move(self):
        selected = self._get_selected_entries()
        if not selected or not self.rom_root:
            return

        count = len(selected)
        dialog = ctk.CTkToplevel(self)
        dialog.title("Confirm Move")
        dialog.geometry("420x180")
        dialog.configure(fg_color=COLORS["bg_primary"])
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        self.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 420) // 2
        y = self.winfo_y() + (self.winfo_height() - 180) // 2
        dialog.geometry(f"+{x}+{y}")

        ctk.CTkLabel(
            dialog,
            text=f"Move {count} ROM file(s) to Hidden/ folders?\n\n"
                 f"Files will be moved to:\n"
                 f"  {self.rom_root}/Hidden/<system>/",
            font=FONTS["body"], text_color=COLORS["text_primary"], justify="left",
        ).pack(padx=20, pady=(20, 16))

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=(0, 16))

        ctk.CTkButton(
            btn_frame, text="Cancel", font=FONTS["body"],
            fg_color=COLORS["bg_card"], hover_color=COLORS["bg_card_hover"],
            corner_radius=RADIUS["button"], height=34, width=100, command=dialog.destroy,
        ).grid(row=0, column=0, padx=(0, 10))

        def do_move():
            dialog.destroy()
            self._execute_move(selected)

        ctk.CTkButton(
            btn_frame, text="Move Files", font=FONTS["status"],
            fg_color=COLORS["btn_primary"], hover_color=COLORS["btn_primary_hover"],
            corner_radius=RADIUS["button"], height=34, width=120, command=do_move,
        ).grid(row=0, column=1)

    def _execute_move(self, entries: list[RomEntry]):
        self.move_btn.configure(state="disabled", text="Moving...")
        self.delete_btn.configure(state="disabled")
        self.scan_btn.configure(state="disabled")
        self._overlay.show("Moving files...", f"Moving {len(entries)} ROM(s) to Hidden/")

        def _run():
            result = move_roms(entries, self.rom_root, on_progress=self._debug_log)
            self.after(0, lambda: self._on_action_complete(
                f"Moved {result.moved} file(s)" +
                (f", {result.failed} failed" if result.failed else ""),
                result.failed == 0,
            ))

        threading.Thread(target=_run, daemon=True).start()

    # ================================================================
    # Delete
    # ================================================================
    def _on_delete(self):
        selected = self._get_selected_entries()
        if not selected or not self.rom_root:
            return

        count = len(selected)
        self._debug_log("Looking up associated media files...")
        media_map = get_media_files_for_entries(selected, self.rom_root)
        total_media = sum(len(v) for v in media_map.values())

        dialog = ctk.CTkToplevel(self)
        dialog.title("Confirm Permanent Deletion")
        dialog.configure(fg_color=COLORS["bg_primary"])
        dialog.resizable(True, True)
        dialog.transient(self)
        dialog.grab_set()

        dlg_h = min(620, 280 + count * 18)
        dlg_w = 580
        dialog.geometry(f"{dlg_w}x{dlg_h}")
        self.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - dlg_w) // 2
        y = self.winfo_y() + (self.winfo_height() - dlg_h) // 2
        dialog.geometry(f"+{x}+{y}")
        dialog.minsize(480, 300)
        dialog.grid_columnconfigure(0, weight=1)
        dialog.grid_rowconfigure(2, weight=1)

        warn = ctk.CTkFrame(dialog, fg_color=COLORS["btn_danger"], corner_radius=0)
        warn.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(warn, text="\u26a0  PERMANENT DELETION  \u26a0",
                     font=FONTS["heading_medium"], text_color="#ffffff").pack(pady=10)

        ctk.CTkLabel(
            dialog,
            text=f"The following {count} ROM file(s) will be PERMANENTLY DELETED.\n"
                 f"This action cannot be undone!",
            font=FONTS["body"], text_color=COLORS["btn_danger"], justify="left",
        ).grid(row=1, column=0, sticky="w", padx=20, pady=(12, 6))

        file_list = ctk.CTkScrollableFrame(
            dialog, fg_color=COLORS["bg_secondary"], corner_radius=RADIUS["input"],
        )
        file_list.grid(row=2, column=0, sticky="nsew", padx=20, pady=(4, 8))
        file_list.grid_columnconfigure(0, weight=1)

        for i, entry in enumerate(selected):
            text = f"{entry.display_name}  /  {entry.system}  ({_format_size(entry.file_size)})"
            ctk.CTkLabel(file_list, text=text, font=FONTS["mono_small"],
                         text_color=COLORS["text_primary"], anchor="w",
            ).grid(row=i, column=0, sticky="w", padx=8, pady=1)

        delete_media_var = ctk.BooleanVar(value=False)
        media_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        media_frame.grid(row=3, column=0, sticky="w", padx=20, pady=(4, 4))

        media_cb = ctk.CTkCheckBox(
            media_frame,
            text=f"Also delete artwork, videos & manuals  ({total_media} files found)",
            variable=delete_media_var, font=FONTS["body"],
            text_color=COLORS["text_primary"],
            fg_color=COLORS["btn_danger"], hover_color=COLORS["btn_danger_hover"],
            border_color=COLORS["border_input"], corner_radius=4,
            checkbox_width=20, checkbox_height=20,
        )
        media_cb.pack(anchor="w")
        if total_media == 0:
            media_cb.configure(state="disabled",
                               text="Also delete artwork, videos & manuals  (none found)")

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.grid(row=4, column=0, pady=(4, 16))

        ctk.CTkButton(
            btn_frame, text="Cancel", font=FONTS["body"],
            fg_color=COLORS["bg_card"], hover_color=COLORS["bg_card_hover"],
            corner_radius=RADIUS["button"], height=34, width=100, command=dialog.destroy,
        ).grid(row=0, column=0, padx=(0, 12))

        def do_delete():
            dialog.destroy()
            self._execute_delete(selected, delete_media_var.get())

        ctk.CTkButton(
            btn_frame, text="DELETE PERMANENTLY", font=FONTS["status"],
            fg_color=COLORS["btn_danger"], hover_color=COLORS["btn_danger_hover"],
            corner_radius=RADIUS["button"], height=34, width=200, command=do_delete,
        ).grid(row=0, column=1)

    def _execute_delete(self, entries: list[RomEntry], delete_media: bool):
        self.delete_btn.configure(state="disabled", text="Deleting...")
        self.move_btn.configure(state="disabled")
        self.scan_btn.configure(state="disabled")
        self._overlay.show("Deleting files...", f"Removing {len(entries)} ROM(s) permanently")

        def _run():
            result = delete_roms(entries, self.rom_root, delete_media=delete_media,
                                 on_progress=self._debug_log)
            summary = f"Deleted {result.deleted_roms} ROM(s)"
            if delete_media:
                summary += f", {result.deleted_media} media file(s)"
            if result.failed:
                summary += f", {result.failed} failed"
            self.after(0, lambda: self._on_action_complete(summary, result.failed == 0))

        threading.Thread(target=_run, daemon=True).start()

    # ================================================================
    # Post-action (shared by move & delete)
    # ================================================================
    def _on_action_complete(self, summary: str, success: bool):
        self.move_btn.configure(state="normal", text="Move Selected  \u25b6")
        self.delete_btn.configure(state="normal", text="Delete Selected  \u2715")
        self.scan_btn.configure(state="normal")
        self._overlay.hide()

        color = COLORS["status_success"] if success else COLORS["status_warning"]
        self._show_toast(summary, color)

        self._debug_log("Re-scanning to update list...")
        self._on_scan()
