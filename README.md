# ROM

A desktop ROM collection manager for **RetroBat** and **Launchbox** formatted libraries. Scans your ROM folders, detects cross-system duplicates, and lets you move or permanently delete unwanted copies — all from a single dark-themed UI.

![Python](https://img.shields.io/badge/Python-3.12+-blue) ![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey) ![License](https://img.shields.io/badge/License-MIT-green)

## Features

- **Cross-system duplicate detection** — Finds games that exist across multiple systems (e.g. the same game on PS2, GameCube, and Wii) using smart name normalisation that strips region tags, disc numbers, and punctuation
- **Browse & manage all games** — Flat view of every ROM in your collection with search, sort, and system filtering
- **Move to Hidden** — Moves unwanted ROMs to `Hidden/<system>/` folders, keeping them out of your frontend without deleting anything
- **Permanent delete** — Optionally delete ROMs and their associated media (artwork, videos, manuals) in one operation
- **Gamelist-aware** — Reads `gamelist.xml` files (EmulationStation / RetroBat / Launchbox format) for clean display names. Falls back to filenames when no gamelist is available
- **Unscraped filter** — Quickly find games that aren't in any gamelist, so you can identify ROMs that haven't been scraped yet
- **Pagination** — Handles large collections (tested with 48,000+ games) with configurable page sizes
- **Operation logging** — All move and delete operations are logged to `rom.log` in your ROM root folder

## How It Works

### Gamelist-Based Naming

ROM uses `gamelist.xml` files to display clean game names. These are the same XML files used by EmulationStation, RetroBat, and Launchbox to store scraped metadata.

```xml
<gameList>
  <game>
    <path>./Final Fantasy VII (USA) (Disc 1).chd</path>
    <name>Final Fantasy VII</name>
    <image>./images/Final Fantasy VII (USA) (Disc 1)-image.png</image>
    ...
  </game>
</gameList>
```

When a gamelist is present, the `<name>` field is used for display. When it isn't, ROM falls back to the filename with region tags and disc indicators stripped — so `Final Fantasy VII (USA) (Disc 1).chd` still shows as `Final Fantasy VII`.

### Duplicate Detection

Duplicates are detected by normalising game names across all system folders:
1. Strip region tags like `(USA)`, `(Europe)`, `(Japan)`
2. Strip disc indicators like `(Disc 1)`, `CD2`
3. Remove punctuation and collapse whitespace
4. Compare across systems — a game must exist in 2+ different system folders to be flagged as a duplicate

### Folder Structure

ROM expects the standard RetroBat/Launchbox folder layout:

```
your_roms_folder/
├── ps2/
│   ├── gamelist.xml          (optional)
│   ├── Game Name (USA).chd
│   ├── images/
│   └── videos/
├── snes/
│   ├── gamelist.xml          (optional)
│   └── Game Name (USA).zip
├── Hidden/                   (created automatically by Move)
│   ├── ps2/
│   └── snes/
└── rom.log                   (created automatically)
```

Each system has its own subfolder. Gamelists are optional — the app works without them, just with less polished display names.

The `Hidden/` folder is automatically excluded from scans.

## Two View Modes

### MANAGE Mode (default)
A flat list of every game in your collection. Use this for:
- Browsing your full library
- Finding unscraped games (toggle "Unscraped only")
- Searching for specific games
- Sorting by name or file size

### DUPLICATES Mode
Grouped cards showing games that exist across 2+ systems. Use this for:
- Identifying redundant copies
- Deciding which system version to keep
- Bulk-moving or deleting duplicates

## Installation

### Download
Grab the latest `ROM.exe` from the [Releases](../../releases) page. No installation required — just run the exe.

### Build from Source

Requirements:
- Python 3.12+
- Windows 10/11

```bash
pip install customtkinter pyinstaller Pillow
```

Build:
```bash
python -m PyInstaller --onefile --windowed --name ROM ^
  --icon=icon.ico ^
  --add-data "icon.ico;." ^
  --add-data "banner.png;." ^
  --collect-all customtkinter ^
  main.py
```

The exe will be in the `dist/` folder.

## Usage

1. Launch `ROM.exe`
2. Click **Select Folder** and choose your ROM root directory (the folder containing system subfolders like `ps2/`, `snes/`, etc.)
3. Click **Scan** — a reminder will appear to ensure your gamelists are up to date
4. Browse games in **MANAGE** mode or switch to **DUPLICATES** to see cross-system duplicates
5. Use the checkboxes to select ROMs, then:
   - **Move Selected** — relocates files to `Hidden/<system>/`
   - **Delete Selected** — permanently removes files (with optional media cleanup)

## Tips

- **Update gamelists before scanning** — Run your scraper (e.g. via RetroBat or Skraper) before scanning for the best display names
- **Network paths work** — You can point ROM at a network share like `\\SERVER\roms\`
- **Hidden folder** — Moved files go to `Hidden/<system>/` inside your ROM root. These folders are skipped during scans. You can manually move files back if needed
- **Check the log** — All operations are logged to `rom.log` in your ROM root folder for reference
