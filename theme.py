"""
Theme configuration for ROM Duplicate Manager.
Dark theme with orange accents, inspired by VS Code Dark+ / QuoteMachine.
"""


# ── Colour Palette ──────────────────────────────────────────────────────────
COLORS = {
    # Backgrounds
    "bg_primary":       "#1e1e1e",
    "bg_secondary":     "#252526",
    "bg_card":          "#2d2d2d",
    "bg_card_hover":    "#3c3c3c",
    "bg_input":         "#3c3c3c",

    # Accent
    "accent":           "#e09c3a",
    "accent_dark":      "#c4882e",

    # Text
    "text_primary":     "#cccccc",
    "text_secondary":   "#808080",
    "text_heading":     "#e09c3a",

    # Buttons
    "btn_primary":      "#0e639c",
    "btn_primary_hover":"#1177bb",
    "btn_danger":       "#f44747",
    "btn_danger_hover": "#d73333",
    "btn_success":      "#6a9955",

    # Borders
    "border_default":   "#3c3c3c",
    "border_input":     "#555555",

    # Status
    "status_info":      "#569cd6",
    "status_warning":   "#dcdcaa",
    "status_error":     "#f44747",
    "status_success":   "#6a9955",
}

# ── Fonts ────────────────────────────────────────────────────────────────────
FONTS = {
    "app_title":      ("Segoe UI", 22, "bold"),
    "heading_large":  ("Segoe UI", 20, "bold"),
    "heading_medium": ("Segoe UI", 16, "bold"),
    "heading_small":  ("Segoe UI", 14, "bold"),
    "body":           ("Segoe UI", 13),
    "body_small":     ("Segoe UI", 11),
    "mono":           ("Consolas", 11),
    "mono_small":     ("Consolas", 10),
    "status":         ("Segoe UI", 13, "bold"),
    "tiny":           ("Segoe UI", 10),
}

# ── Dimensions ───────────────────────────────────────────────────────────────
RADIUS = {
    "card":   12,
    "button": 6,
    "input":  6,
}

PADDING = {
    "page":  20,
    "card":  12,
    "small": 6,
}
