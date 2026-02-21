"""
File mover and deleter with logging.
Moves ROM files to Hidden/<system>/ or permanently deletes them.
"""

import os
import shutil
import datetime
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Callable

from scanner import RomEntry


HIDDEN_FOLDER = "Hidden"
LOG_FILENAME = "rom_duplicate_manager.log"

# gamelist.xml tags that reference media files
MEDIA_TAGS = ("image", "video", "marquee", "thumbnail", "fanart", "manual", "bezel", "boxback")


@dataclass
class MoveResult:
    """Summary of a move batch."""
    moved: int = 0
    failed: int = 0
    errors: list = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


@dataclass
class DeleteResult:
    """Summary of a delete batch."""
    deleted_roms: int = 0
    deleted_media: int = 0
    failed: int = 0
    errors: list = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


def _find_media_files(entry: RomEntry, rom_root: str) -> list[str]:
    """Look up media files for a ROM entry from its system's gamelist.xml."""
    system_dir = os.path.join(rom_root, entry.system)
    gamelist_path = os.path.join(system_dir, "gamelist.xml")
    media_files = []

    if not os.path.isfile(gamelist_path):
        return media_files

    rom_filename = os.path.basename(entry.file_path).lower()

    try:
        tree = ET.parse(gamelist_path)
        root = tree.getroot()
        for game in root.findall("game"):
            path_el = game.find("path")
            if path_el is None or path_el.text is None:
                continue
            rel_path = path_el.text.lstrip("./\\")
            filename = os.path.basename(rel_path).lower()
            if filename == rom_filename:
                for tag in MEDIA_TAGS:
                    el = game.find(tag)
                    if el is not None and el.text:
                        media_rel = el.text.lstrip("./\\")
                        media_abs = os.path.join(system_dir, media_rel)
                        if os.path.isfile(media_abs):
                            media_files.append(media_abs)
                break
    except (ET.ParseError, OSError):
        pass

    return media_files


def get_media_files_for_entries(entries: list[RomEntry], rom_root: str) -> dict[str, list[str]]:
    """Return {file_path: [media_file_paths]} for a list of ROM entries."""
    result = {}
    for entry in entries:
        result[entry.file_path] = _find_media_files(entry, rom_root)
    return result


def move_roms(
    entries: list[RomEntry],
    rom_root: str,
    on_progress: Callable[[str], None] | None = None,
) -> MoveResult:
    """
    Move a list of ROM files to Hidden/<system>/.

    Args:
        entries: ROM entries to move.
        rom_root: Root ROM directory (Hidden/ will be created here).
        on_progress: Optional callback for status messages.

    Returns:
        MoveResult with counts and any errors.
    """
    result = MoveResult()
    log_path = os.path.join(rom_root, LOG_FILENAME)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def log(msg: str):
        if on_progress:
            on_progress(msg)

    log(f"Moving {len(entries)} file(s)...")

    log_lines = []
    log_lines.append(f"\n{'='*60}")
    log_lines.append(f"Move operation: {timestamp}")
    log_lines.append(f"Files to move: {len(entries)}")
    log_lines.append(f"{'='*60}")

    for entry in entries:
        src = entry.file_path
        dest_dir = os.path.join(rom_root, HIDDEN_FOLDER, entry.system)
        dest = os.path.join(dest_dir, os.path.basename(src))

        try:
            os.makedirs(dest_dir, exist_ok=True)
            shutil.move(src, dest)
            result.moved += 1
            msg = f"  MOVED: {entry.display_name} ({entry.system})"
            log(msg)
            log_lines.append(
                f"  [OK]  {entry.display_name}"
                f"\n        From: {src}"
                f"\n        To:   {dest}"
            )
        except OSError as e:
            result.failed += 1
            err_msg = f"  FAILED: {entry.display_name} ({entry.system}) - {e}"
            log(err_msg)
            result.errors.append(err_msg)
            log_lines.append(
                f"  [FAIL] {entry.display_name}"
                f"\n         From: {src}"
                f"\n         Error: {e}"
            )

    log_lines.append(f"\nSummary: {result.moved} moved, {result.failed} failed")
    log_lines.append(f"{'='*60}\n")

    # Append to log file
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write("\n".join(log_lines) + "\n")
        log(f"Log written to {log_path}")
    except OSError as e:
        log(f"WARNING: Could not write log file: {e}")

    log(f"\nDone: {result.moved} moved, {result.failed} failed")
    return result


def delete_roms(
    entries: list[RomEntry],
    rom_root: str,
    delete_media: bool = False,
    on_progress: Callable[[str], None] | None = None,
) -> DeleteResult:
    """
    Permanently delete ROM files and optionally their associated media.

    Args:
        entries: ROM entries to delete.
        rom_root: Root ROM directory (for log file and media lookup).
        delete_media: If True, also delete images/videos/etc from gamelist.xml.
        on_progress: Optional callback for status messages.

    Returns:
        DeleteResult with counts and any errors.
    """
    result = DeleteResult()
    log_path = os.path.join(rom_root, LOG_FILENAME)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def log(msg: str):
        if on_progress:
            on_progress(msg)

    log(f"DELETING {len(entries)} file(s) (media={'YES' if delete_media else 'NO'})...")

    log_lines = []
    log_lines.append(f"\n{'='*60}")
    log_lines.append(f"DELETE operation: {timestamp}")
    log_lines.append(f"Files to delete: {len(entries)}")
    log_lines.append(f"Delete media: {delete_media}")
    log_lines.append(f"{'='*60}")

    for entry in entries:
        # Delete the ROM file
        try:
            os.remove(entry.file_path)
            result.deleted_roms += 1
            log(f"  DELETED: {entry.display_name} ({entry.system})")
            log_lines.append(
                f"  [DEL]  {entry.display_name}"
                f"\n         File: {entry.file_path}"
            )
        except OSError as e:
            result.failed += 1
            err_msg = f"  FAILED: {entry.display_name} ({entry.system}) - {e}"
            log(err_msg)
            result.errors.append(err_msg)
            log_lines.append(
                f"  [FAIL] {entry.display_name}"
                f"\n         File: {entry.file_path}"
                f"\n         Error: {e}"
            )
            continue

        # Delete associated media if requested
        if delete_media:
            media_files = _find_media_files(entry, rom_root)
            for mf in media_files:
                try:
                    os.remove(mf)
                    result.deleted_media += 1
                    log(f"    media: {os.path.basename(mf)}")
                    log_lines.append(f"         Media: {mf}")
                except OSError:
                    pass  # media deletion failures are non-critical

    summary = f"Deleted {result.deleted_roms} ROM(s)"
    if delete_media:
        summary += f", {result.deleted_media} media file(s)"
    if result.failed > 0:
        summary += f", {result.failed} failed"

    log_lines.append(f"\nSummary: {summary}")
    log_lines.append(f"{'='*60}\n")

    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write("\n".join(log_lines) + "\n")
        log(f"Log written to {log_path}")
    except OSError as e:
        log(f"WARNING: Could not write log file: {e}")

    log(f"\nDone: {summary}")
    return result
