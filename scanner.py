"""
ROM folder scanner and duplicate detector.
Parses gamelist.xml files and groups games by normalised name across systems.
"""

import os
import re
import threading
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable


# Folders to skip when scanning (case-insensitive check)
SKIP_FOLDERS = {
    "hidden", "newgamelists", "oldgamelists", "oldgamelists2",
    ".claude", "images", "videos", "manuals", "media",
}

# Known media / metadata extensions we never treat as ROMs
MEDIA_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg",
    ".mp4", ".mkv", ".avi", ".webm",
    ".pdf", ".txt", ".xml", ".cfg", ".bak", ".old",
    ".srm", ".state", ".sav",  # save-states
}

# Regex pieces for name cleanup
_REGION_RE = re.compile(
    r"\s*\("
    r"(?:USA|Europe|Japan|World|PAL|NTSC|En|Fr|De|Es|It|Pt|Nl|Sv|No|Da|Fi|"
    r"Ko|Zh|Ja|Ru|Pl|Cs|Hu|Unl|Proto|Beta|Sample|Demo|Rev\s*\d*|"
    r"v[\d.]+|Alt(?:\s*\d+)?|Hack|Virtual Console|"
    r"UE|EU|US|JP|[A-Z]{2}(?:,[A-Z]{2})*)"
    r"\)",
    re.IGNORECASE,
)
_DISC_RE = re.compile(
    r"\s*(?:\(Disc\s*\d+(?:\s*of\s*\d+)?\)|CD[\s-]*\d+|\bDisc\s*\d+)",
    re.IGNORECASE,
)
_PUNC_RE = re.compile(r"[^\w\s]")
_MULTI_SPACE = re.compile(r"\s+")


@dataclass
class RomEntry:
    """One ROM file on disk."""
    display_name: str       # human-readable game name
    system: str             # system folder name (e.g. "ps2")
    file_path: str          # full absolute path to the ROM file
    file_size: int = 0      # bytes
    in_gamelist: bool = True # False if not found in gamelist.xml


@dataclass
class ScanResult:
    """Complete scan output."""
    duplicates: dict = field(default_factory=dict)   # norm_key -> [RomEntry, ...]
    all_games: dict = field(default_factory=dict)     # norm_key -> [RomEntry, ...]
    total_games: int = 0
    total_systems: int = 0
    total_duplicate_groups: int = 0
    total_duplicate_files: int = 0
    total_unscraped: int = 0


def normalize_name(name: str) -> str:
    """Normalise a game name for duplicate matching."""
    s = name
    s = _REGION_RE.sub("", s)
    s = _DISC_RE.sub("", s)
    # Strip file extension if still present
    root, ext = os.path.splitext(s)
    if ext:
        s = root
    s = s.lower()
    # Remove apostrophes before general punc strip so "hawk's" -> "hawks" not "hawk s"
    s = s.replace("'", "").replace("\u2019", "")
    s = _PUNC_RE.sub(" ", s)
    s = _MULTI_SPACE.sub(" ", s).strip()
    return s


def _name_from_filename(filename: str) -> str:
    """Derive a display name from a ROM filename."""
    name = os.path.splitext(filename)[0]
    # Remove common parenthetical tags but keep the core name
    name = _REGION_RE.sub("", name)
    name = _DISC_RE.sub("", name)
    return name.strip()


def _parse_gamelist(xml_path: str) -> dict:
    """Parse a gamelist.xml and return {relative_filename: display_name}."""
    result = {}
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        for game in root.findall("game"):
            path_el = game.find("path")
            name_el = game.find("name")
            if path_el is None or path_el.text is None:
                continue
            # path is like "./Game Name.zip"
            rel_path = path_el.text.lstrip("./\\")
            filename = os.path.basename(rel_path)
            display = name_el.text.strip() if (name_el is not None and name_el.text) else _name_from_filename(filename)
            result[filename.lower()] = display
    except (ET.ParseError, OSError):
        pass
    return result


def _get_file_size(path: str) -> int:
    """Get file size, returning 0 on error."""
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def scan_roms(
    rom_root: str,
    on_progress: Callable[[str], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> ScanResult:
    """
    Scan the ROM root directory and find cross-system duplicates.

    Args:
        rom_root: Path to the top-level ROMs folder.
        on_progress: Optional callback receiving status messages.
        cancel_event: Optional threading.Event; set it to abort the scan.

    Returns:
        ScanResult with duplicate groups and stats.
    """
    def log(msg: str):
        if on_progress:
            on_progress(msg)

    def cancelled() -> bool:
        return cancel_event is not None and cancel_event.is_set()

    all_games: dict[str, list[RomEntry]] = defaultdict(list)
    total_games = 0
    total_unscraped = 0
    systems_scanned = 0

    log(f"Scanning ROM root: {rom_root}")

    try:
        entries = sorted(os.listdir(rom_root))
    except OSError as e:
        log(f"ERROR: Cannot read directory: {e}")
        return ScanResult()

    for folder_name in entries:
        if cancelled():
            log("\nScan cancelled by user.")
            return ScanResult()

        folder_path = os.path.join(rom_root, folder_name)
        if not os.path.isdir(folder_path):
            continue
        if folder_name.lower() in SKIP_FOLDERS or folder_name.startswith("."):
            continue

        systems_scanned += 1
        gamelist_path = os.path.join(folder_path, "gamelist.xml")
        gamelist_map = _parse_gamelist(gamelist_path) if os.path.isfile(gamelist_path) else {}

        # Collect all ROM files in this system folder (non-recursive, top-level only)
        try:
            files = os.listdir(folder_path)
        except OSError:
            log(f"  WARNING: Cannot read {folder_name}/")
            continue

        system_count = 0
        system_unscraped = 0
        for fname in files:
            fpath = os.path.join(folder_path, fname)
            if not os.path.isfile(fpath):
                continue
            # Skip known non-ROM files
            _, ext = os.path.splitext(fname)
            if ext.lower() in MEDIA_EXTENSIONS:
                continue
            # Skip gamelist.xml itself
            if fname.lower() == "gamelist.xml":
                continue

            # Get display name: prefer gamelist.xml, fall back to filename
            display = gamelist_map.get(fname.lower())
            scraped = display is not None
            if not scraped:
                display = _name_from_filename(fname)
            if not display:
                continue

            norm_key = normalize_name(display)
            if not norm_key:
                continue

            entry = RomEntry(
                display_name=display,
                system=folder_name,
                file_path=fpath,
                file_size=_get_file_size(fpath),
                in_gamelist=scraped,
            )
            all_games[norm_key].append(entry)
            system_count += 1
            total_games += 1
            if not scraped:
                system_unscraped += 1
                total_unscraped += 1

        if system_count > 0:
            msg = f"  {folder_name}: {system_count} games"
            if system_unscraped > 0:
                msg += f" ({system_unscraped} not in gamelist)"
            log(msg)

    # Filter to only groups that span multiple systems
    duplicates: dict[str, list[RomEntry]] = {}
    for norm_key, entries in all_games.items():
        systems_in_group = {e.system for e in entries}
        if len(systems_in_group) >= 2:
            # Sort by system name for consistent display
            duplicates[norm_key] = sorted(entries, key=lambda e: e.system.lower())

    dup_groups = len(duplicates)
    dup_files = sum(len(v) for v in duplicates.values())

    log(f"\nScan complete: {total_games} games across {systems_scanned} systems")
    if total_unscraped > 0:
        log(f"  {total_unscraped} games not in any gamelist.xml")
    log(f"Found {dup_groups} duplicate groups ({dup_files} total files)")

    return ScanResult(
        duplicates=duplicates,
        all_games=dict(all_games),
        total_games=total_games,
        total_systems=systems_scanned,
        total_duplicate_groups=dup_groups,
        total_duplicate_files=dup_files,
        total_unscraped=total_unscraped,
    )
