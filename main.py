"""
ROM – entry point.
Scans a ROM collection, finds cross-system duplicates,
and lets you move unwanted copies to Hidden/<system>/ folders.
"""

import sys
import os

# Ensure the app directory is on the path so imports work from a PyInstaller bundle
if getattr(sys, "frozen", False):
    os.chdir(os.path.dirname(sys.executable))

from app import App


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
