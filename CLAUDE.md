# ROM

## Overview
Desktop app (Python + CustomTkinter) for managing ROM collections structured in RetroBat or Launchbox format. Scans a ROM root folder, finds cross-system duplicates, and lets users move or delete unwanted copies. Also provides a flat browse-all-games view for general ROM management.

## Architecture

### Files
- **main.py** — Entry point. Sets `os.chdir` for PyInstaller frozen bundles, launches `App`.
- **app.py** — Main UI (~1400 lines). Single `App(ctk.CTk)` class with all widgets, filtering, dialogs.
- **scanner.py** — ROM scanning and duplicate detection. Parses `gamelist.xml` per system folder, normalizes game names, groups duplicates across systems.
- **mover.py** — File operations: `move_roms()` (to Hidden/<system>/), `delete_roms()` (permanent, optional media deletion). Logs to `rom.log`.
- **theme.py** — Color palette, fonts, radii, padding. Dark theme with orange accent (#d6791c), VS Code-inspired.
- **icon.ico** — App icon (user-supplied, 256x256).
- **banner.png** — Header banner image (1920x80 RGB, user-supplied).

### Key Data Model (scanner.py)
- `RomEntry`: display_name, system, file_path, file_size, in_gamelist (bool)
- `ScanResult`: duplicates (cross-system groups), all_games (every game), stats, total_unscraped
- Name normalization: lowercase, strip region tags `(USA)`, disc indicators, apostrophes before punctuation, collapse whitespace

### UI Layout (app.py)
- **Row 0**: Header (80px) — banner.png background, Select Folder + Scan buttons (flush-right)
- **Row 1**: Stats bar (110px fixed) — path label, search/sort/system filters, MANAGE/DUPLICATES mode tabs, pagination, "Unscraped only" checkbox
- **Row 2**: Game list (scrollable, weighted) — paginated with per-page selector (25/50/100/200)
- **Row 3**: Action bar — Select All, Deselect All, Move Selected, Delete Selected
- **Row 4**: Debug panel (collapsible) — real-time log output

### Two View Modes
- **MANAGE** (default after scan): Flat list of ALL games. Sort by alpha/size. System filter shows all scanned systems. "Unscraped only" checkbox filters to games not in gamelist.xml.
- **DUPLICATES**: Grouped expandable cards showing games that exist across 2+ systems. Sort by alpha/size/copies. System filter shows systems in duplicates.

### Asset Loading
- `_find_asset(filename)`: checks next to exe first (user override), then `sys._MEIPASS` (PyInstaller bundle)
- Banner rendered via `CTkImage` on `CTkLabel` — widgets placed directly on the label with `place()` (NOT via a CTkFrame overlay, which would be opaque)

### Important Patterns
- **Threading**: Scan/move/delete run in background threads. `threading.Event` for scan cancellation. UI updates via `self.after(0, callback)`.
- **Pagination**: Page-based navigation with per-page selector (25/50/100/200). Page nav with prev/next arrows and numbered buttons with ellipsis.
- **Debounced search**: 300ms delay on text input before re-filtering.
- **ProgressOverlay**: Full-screen overlay with animated braille spinner for scan/analyse/load/move/delete phases.
- **Pre-scan popup**: First scan shows "FOR BEST RESULTS / ENSURE GAMELISTS ARE UP TO DATE" confirmation. Skipped on re-scans after move/delete.
- **Scan button**: Orange (#d6791c) before first scan, darker (#ba6919) after scan done.

## Build

### Requirements
- Python 3.12+
- `pip install customtkinter pyinstaller Pillow`

### Package as .exe
```bash
cd y:/RomManager
python -m PyInstaller --onefile --windowed --name ROM ^
  --icon="y:/RomManager/icon.ico" ^
  --add-data "y:/RomManager/icon.ico;." ^
  --add-data "y:/RomManager/banner.png;." ^
  --collect-all customtkinter ^
  --distpath ./package --workpath ./build --specpath ./build ^
  main.py
```
Output: `package/ROM.exe` (single file, ~20MB, all assets bundled inside)

### Known Build Issues
- Use absolute paths for `--icon` and `--add-data` (PyInstaller resolves relative to spec dir)
- Use `python -m PyInstaller` not `pyinstaller` directly
- Clean `build/` dir before rebuilding to avoid cached spec issues
- CTkFrame with `fg_color="transparent"` is NOT truly transparent — it inherits parent bg color. Place widgets directly on CTkLabel for banner overlay.

## ROM Folder Structure
```
\\OASTARCADE\roms\          (or any local/network path)
├── ps2/
│   ├── gamelist.xml        (optional — parsed for display names + media paths)
│   ├── Game Name (USA).chd
│   ├── images/             (scraped artwork)
│   └── videos/             (scraped videos)
├── snes/
│   ├── gamelist.xml
│   └── ...
├── Hidden/                 (created by Move — skipped during scan)
│   ├── ps2/
│   └── snes/
└── ...
```

### gamelist.xml Format (EmulationStation)
```xml
<gameList>
  <game>
    <path>./Game Name (USA).chd</path>
    <name>Game Name</name>
    <image>./images/Game Name (USA)-image.png</image>
    <video>./videos/Game Name (USA)-video.mp4</video>
    ...
  </game>
</gameList>
```

## User Preferences
- Dark theme with orange accents
- Windows 10 target platform
- Network ROM storage (\\OASTARCADE\roms\)
