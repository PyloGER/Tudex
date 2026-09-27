#!/usr/bin/env python3
"""
Tuxdex - grafische Systemverwaltung für Arch Linux: Updates, Paketverwaltung,
Fallback-Speicher (Swap), Firewall und Benutzerübersicht.

Oberfläche: PySide6 (Qt 6), dunkles Theme mit Petrol-Akzent, IBM Plex.
(dunkles Theme, Petrol-Akzent, IBM Plex).

Alles läuft innerhalb des Programmfensters - es wird KEIN externes
Terminal geöffnet. Für privilegierte Aktionen wird beim ersten Mal per
Dialog nach dem sudo-Passwort gefragt; danach bleibt die sudo-Sitzung
für den Rest des Programmlaufs aktiv (kein wiederholtes Eingeben).

Abhängigkeiten (per pacman installieren):
    sudo pacman -S pyside6 sudo pacman-contrib ttf-ibm-plex
    # paru (AUR-Helper) und flatpak nur nötig, wenn diese Bereiche
    # genutzt werden sollen.

Start:
    python3 tuxdex.py      (oder nach der Installation: tuxdex)
"""

import os
import pwd
import re
import shlex
import shutil
import signal
import subprocess
import sys
import json
import select
import tempfile
import threading
import time
from datetime import datetime
from string import Template

PKG_NAME_RE = re.compile(r"^[A-Za-z0-9@_.+-]+$")
PATH_RE = re.compile(r"^/[A-Za-z0-9_./-]+$")


# --------------------------------------------------------------------------
# Fehlerbehandlung, falls PySide6 selbst fehlt
# --------------------------------------------------------------------------

def _show_fatal_error(title, message):
    log_path = os.path.expanduser("~/tuxdex_error.log")
    try:
        with open(log_path, "a") as f:
            f.write(f"\n--- {datetime.now().isoformat()} | {title} ---\n{message}\n")
    except Exception:
        pass
    full_msg = f"{message}\n\n(Details auch in {log_path})"
    for tool, args in (
        ("kdialog", ["--title", title, "--error", full_msg]),
        ("zenity", ["--error", "--title", title, "--text", full_msg]),
        ("notify-send", ["-u", "critical", title, message]),
    ):
        if shutil.which(tool):
            try:
                subprocess.run([tool] + args, timeout=15)
                return
            except Exception:
                continue
    print(f"{title}: {message}", file=sys.stderr)


try:
    from PySide6.QtCore import QObject, Qt, Signal, Slot, QTimer, QSize, QRectF
    from PySide6.QtGui import (QColor, QFont, QFontDatabase, QPainter, QPainterPath, QPen, QTextCharFormat,
                               QTextCursor, QIcon, QPixmap)
    from PySide6.QtWidgets import (
        QApplication, QWidget, QFrame, QLabel, QPushButton, QHBoxLayout, QVBoxLayout,
        QGridLayout, QStackedWidget, QPlainTextEdit, QLineEdit, QCheckBox, QComboBox,
        QListWidget, QAbstractItemView, QTableWidget, QTableWidgetItem, QHeaderView,
        QTreeWidget, QTreeWidgetItem, QLayout,
        QSlider, QDialog, QMessageBox, QScrollArea, QSizePolicy,
    )
except Exception as e:
    _show_fatal_error(
        "Tuxdex - Start fehlgeschlagen",
        "PySide6 konnte nicht geladen werden. Vermutlich fehlt das Paket 'pyside6'.\n\n"
        "Installieren mit: sudo pacman -S pyside6\n\n"
        f"Fehlermeldung: {e}",
    )
    sys.exit(1)


# --------------------------------------------------------------------------
# Design-Tokens (Theme „Dunkel“)
# --------------------------------------------------------------------------

COLORS = {
    "bg0": "#0e1113",          # bg-000  Fenster
    "bg1": "#151a1d",          # bg-100  Kopfleiste, Tabs, Log
    "bg2": "#1c2327",          # bg-200  Panels, Tabellen
    "bg3": "#253036",          # bg-300  Hover, Ghost-Button
    "bg3h": "#2f3c43",         # Ghost-Hover
    "line": "#2a353b",         # line
    "line_strong": "#5f717a",  # line-strong (Eingaben)
    "ink": "#e6edf0",
    "muted": "#9aa9b0",
    "accent": "#2fb3a3",
    "accent_h": "#4fcfbf",
    "on_accent": "#07201d",
    "focus": "#7fe3d6",
    "ok": "#4cc38a",
    "warn": "#e8a33d",
    "danger": "#f0726a",
    "danger_h": "#f58d86",
    "on_danger": "#2a0906",
    "info": "#5aa6f0",
}

# Modul-Kennfarben
MODULES = [
    ("update", "Updates", "#2fb3a3"),
    ("software", "Software", "#5aa6f0"),
    ("flatpak", "Flatpak", "#8fa8ff"),
    ("disks", "Datenträger", "#d9b95c"),
    ("storage", "Speicher", "#56c2d6"),
    ("swap", "Swap", "#6cc56f"),
    ("tasks", "Taskmanager", "#b5d86b"),
    ("antivirus", "Antivirus", "#a98bf0"),
    ("security", "Sicherheit", "#f08a4b"),
    ("users", "Benutzer", "#e87fa8"),
]

FONTS = {"sans": "Sans Serif", "mono": "Monospace"}

APP_ID = "tuxdex"
APP_VERSION = "1.5.5"
SYSTEM_INSTALL = os.path.abspath(__file__).startswith("/usr/")

# App-Logo (Kachel mit drei Reglern) – Taskleiste, Kopfzeile, Starter
LOGO_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">
  <title>Tuxdex</title>
  <!-- Kachel: bg-100 (#151a1d) mit line-Rand (#2a353b) -->
  <rect x="8" y="8" width="496" height="496" rx="116" fill="#151a1d"/>
  <rect x="13" y="13" width="486" height="486" rx="111" fill="none" stroke="#2a353b" stroke-width="10"/>
  <!-- drei Regler = „steuern & verwalten“: Spur bg-300, Füllung accent (Petrol) -->
  <g stroke-linecap="round" stroke-width="56">
    <line x1="112" y1="148" x2="400" y2="148" stroke="#27343a"/>
    <line x1="112" y1="256" x2="400" y2="256" stroke="#27343a"/>
    <line x1="112" y1="364" x2="400" y2="364" stroke="#27343a"/>
    <line x1="112" y1="148" x2="300" y2="148" stroke="#2fb3a3"/>
    <line x1="112" y1="256" x2="196" y2="256" stroke="#2fb3a3"/>
    <line x1="112" y1="364" x2="352" y2="364" stroke="#2fb3a3"/>
  </g>
  <!-- Knöpfe als abgerundete Quadrate – das Kachel-Motiv im Kleinen -->
  <g fill="#e6edf0" stroke="#151a1d" stroke-width="14">
    <rect x="252" y="100" width="96" height="96" rx="28"/>
    <rect x="148" y="208" width="96" height="96" rx="28"/>
    <rect x="304" y="316" width="96" height="96" rx="28"/>
  </g>
</svg>"""


def logo_pixmap(size, dpr=1.0):
    from PySide6.QtSvg import QSvgRenderer
    from PySide6.QtCore import QByteArray
    px = QPixmap(int(size * dpr), int(size * dpr))
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    QSvgRenderer(QByteArray(LOGO_SVG.encode())).render(p, QRectF(0, 0, size * dpr, size * dpr))
    p.end()
    px.setDevicePixelRatio(dpr)
    return px


def logo_icon():
    icon = QIcon()
    for s in (16, 22, 24, 32, 48, 64, 128, 256, 512):
        icon.addPixmap(logo_pixmap(s))
    return icon


def migrate_legacy():
    """Übernimmt Daten der früheren Namensversion „arch-manager“ (einmalig, ohne root)."""
    home = os.path.expanduser("~")
    moves = [(os.path.join(home, ".cache", "arch-manager"), os.path.join(home, ".cache", "tuxdex")),
             (os.path.join(home, ".local", "share", "arch-manager"), os.path.join(home, ".local", "share", "tuxdex")),
             (os.path.join(home, "arch_manager_error.log"), os.path.join(home, "tuxdex_error.log"))]
    for old, new in moves:
        try:
            if os.path.exists(old) and not os.path.exists(new):
                shutil.move(old, new)
        except Exception:
            pass
    share = os.environ.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share")
    old_desk = os.path.join(share, "applications", "arch-manager.desktop")
    try:
        with open(old_desk) as f:
            txt = f.read()
        if "X-Arch-Manager-Generated=true" in txt or "Exec=python3" in txt:
            os.remove(old_desk)
            old_icon = os.path.join(share, "icons", "hicolor", "scalable", "apps", "arch-manager.svg")
            if os.path.exists(old_icon):
                os.remove(old_icon)
    except Exception:
        pass


def install_desktop_entry():
    """Legt Icon + Starter im Benutzerprofil ab, damit Taskleiste/Dock (auch unter
    Wayland) und das Anwendungsmenü das Logo zeigen. Nur wenn nötig, ohne root."""
    try:
        share = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
        icon_path = os.path.join(share, "icons", "hicolor", "scalable", "apps", f"{APP_ID}.svg")
        desk_path = os.path.join(share, "applications", f"{APP_ID}.desktop")
        if SYSTEM_INSTALL:
            # Als Paket installiert: der System-Starter gilt; alte selbst angelegte Einträge entfernen,
            # sonst würden sie den System-Starter überdecken.
            try:
                with open(desk_path) as f:
                    old = f.read()
                if "X-Tuxdex-Generated=true" in old:
                    os.remove(desk_path)
                    if os.path.exists(icon_path):
                        os.remove(icon_path)
            except FileNotFoundError:
                pass
            return
        script = os.path.abspath(sys.argv[0])
        desktop = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=Tuxdex\n"
            "GenericName=Systemverwaltung für Arch Linux\n"
            "Comment=Updates, Software, Datenträger, Speicher, Taskmanager, Antivirus, Firewall und Benutzer\n"
            f"Exec=python3 {shlex.quote(script)}\n"
            f"Icon={APP_ID}\n"
            "Terminal=false\n"
            "Categories=System;Monitor;\n"
            "X-Tuxdex-Generated=true\n"
        )
        changed = False
        def _read(p):
            try:
                with open(p) as f:
                    return f.read()
            except Exception:
                return ""
        if _read(icon_path) != LOGO_SVG:
            os.makedirs(os.path.dirname(icon_path), exist_ok=True)
            with open(icon_path, "w") as f:
                f.write(LOGO_SVG)
            changed = True
        if _read(desk_path) != desktop:
            os.makedirs(os.path.dirname(desk_path), exist_ok=True)
            with open(desk_path, "w") as f:
                f.write(desktop)
            changed = True
        if changed and which("update-desktop-database"):
            subprocess.run(["update-desktop-database", os.path.dirname(desk_path)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    except Exception:
        pass

QSS = Template("""
* { outline: none; }
QWidget { color: $ink; font-size: 10pt; }
QMainWindow, #Root, #Page, QScrollArea, QScrollArea > QWidget > QWidget { background: $bg0; }
QToolTip { background: $bg2; color: $ink; border: 1px solid $line; padding: 4px 8px; }

/* Kopfleiste & Tabs */
#Topbar { background: $bg1; }
#AppTitle { font-size: 15pt; font-weight: 600; }
#TabBar { background: $bg1; border-bottom: 1px solid $line; }
#Tab { background: transparent; border-top-left-radius: 6px; border-top-right-radius: 6px; }
#Tab[selected="true"] { background: $bg0; }
#Tab:hover { background: $bg2; }
#Tab[selected="true"]:hover { background: $bg0; }
#TabText { color: $muted; font-weight: 600; background: transparent; }
#Tab[selected="true"] #TabText, #Tab:hover #TabText { color: $ink; }
#Statusbar { background: $bg0; border-top: 1px solid $line; }
#StatusText { color: $muted; font-size: 9pt; }

/* Typografie */
#PageTitle { font-size: 15pt; font-weight: 600; }
#Muted { color: $muted; }
#Small { color: $muted; font-size: 9pt; }
#Error { color: $danger; }
#FieldLabel { color: $muted; font-size: 8pt; font-weight: 600; }
#Value { font-family: "$mono"; font-weight: 600; }

/* Panels */
#Panel { background: $bg2; border: 1px solid $line; border-radius: 10px; }
#PanelTitle { font-weight: 600; background: transparent; }
#Panel QLabel, #Panel QCheckBox { background: transparent; }

/* Buttons */
QPushButton {
    background: $bg3; color: $ink; border: 0; border-radius: 6px;
    padding: 7px 16px; font-weight: 600;
}
QPushButton:hover { background: $bg3h; }
QPushButton:focus { border: 2px solid $focus; padding: 5px 14px; }
QPushButton[variant="primary"] { background: $accent; color: $on_accent; }
QPushButton[variant="primary"]:hover { background: $accent_h; }
QPushButton[variant="danger"] { background: $danger; color: $on_danger; }
QPushButton[variant="danger"]:hover { background: $danger_h; }
QPushButton:disabled, QPushButton[variant="primary"]:disabled, QPushButton[variant="danger"]:disabled {
    background: transparent; color: $line_strong; border: 1px solid $line; padding: 6px 15px;
}
QPushButton[variant="icon"] { padding: 6px 10px; min-width: 16px; }

/* Status-Badges */
#Badge { border: 1px solid; border-radius: 3px; padding: 2px 8px; font-size: 9pt; font-weight: 600; background: $bg2; }
#Badge[tone="ok"] { color: $ok; border-color: $ok; }
#Badge[tone="warn"] { color: $warn; border-color: $warn; }
#Badge[tone="danger"] { color: $danger; border-color: $danger; }
#Badge[tone="info"] { color: $info; border-color: $info; }
#Badge[tone="off"] { color: $muted; border-color: $muted; }

/* Eingaben */
QLineEdit, QComboBox {
    background: $bg0; color: $ink; border: 1px solid $line_strong; border-radius: 6px;
    padding: 6px 10px; selection-background-color: $accent; selection-color: $on_accent;
    min-height: 22px;
}
QLineEdit:focus, QComboBox:focus, QComboBox:on { border: 2px solid $focus; padding: 5px 9px; }
QLineEdit[mono="true"] { font-family: "$mono"; }
QComboBox::drop-down { border: 0; width: 28px; }
QComboBox::down-arrow { image: url("$arrow"); width: 12px; height: 12px; }
QComboBox QAbstractItemView {
    background: $bg2; color: $ink; border: 1px solid $line; border-radius: 6px; padding: 4px;
    selection-background-color: $accent; selection-color: $on_accent; outline: 0;
}

QCheckBox { spacing: 8px; background: transparent; }
QCheckBox::indicator {
    width: 16px; height: 16px; border: 1.5px solid $line_strong; border-radius: 3px; background: $bg0;
}
QCheckBox::indicator:checked { background: $accent; border-color: $accent; image: url("$check"); }
QCheckBox::indicator:focus { border-color: $focus; }
QCheckBox:disabled { color: $muted; }
QCheckBox::indicator:disabled { background: $bg3; border-color: $bg3; }

QSlider::groove:horizontal { height: 8px; background: $bg3; border-radius: 3px; }
QSlider::sub-page:horizontal { background: $accent; border-radius: 3px; }
QSlider::handle:horizontal {
    background: $ink; width: 16px; height: 16px; margin: -4px 0; border-radius: 8px;
}
QSlider::handle:horizontal:hover { background: $focus; }

/* Listen & Tabellen */
QListWidget, QTableWidget, QTreeWidget {
    background: $bg1; color: $ink; border: 1px solid $line; border-radius: 6px;
    font-family: "$mono"; alternate-background-color: $bg1;
}
QListWidget::item { padding: 4px 8px; border: 0; }
QListWidget::item:hover, QTableWidget::item:hover { background: $bg3; }
QListWidget::item:selected, QTableWidget::item:selected, QTreeWidget::item:selected {
    background: $accent; color: $on_accent;
}
QTreeWidget::item { padding: 5px 4px; }
QTreeWidget::item:hover { background: $bg3; }
QTableWidget { gridline-color: $line; }
QTableWidget::item { padding: 4px 10px; border-bottom: 1px solid $line; }
QHeaderView::section {
    background: $bg1; color: $muted; border: 0; border-bottom: 1px solid $line;
    padding: 8px 10px; font-family: "$sans"; font-size: 8pt; font-weight: 600;
}
QTableCornerButton::section { background: $bg1; border: 0; }

/* Log */
#Log {
    background: $bg1; color: $ink; border: 1px solid $line; border-radius: 6px;
    padding: 6px 8px; font-family: "$mono";
    selection-background-color: $accent; selection-color: $on_accent;
}

/* Scrollbars */
QScrollBar:vertical { background: transparent; width: 12px; margin: 2px; }
QScrollBar:horizontal { background: transparent; height: 12px; margin: 2px; }
QScrollBar::handle { background: $bg3; border-radius: 4px; min-height: 24px; min-width: 24px; }
QScrollBar::handle:hover { background: $line_strong; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

/* Dialoge */
QDialog, QMessageBox { background: $bg2; }
QMessageBox QLabel { background: transparent; }
#DialogTitle { font-size: 14pt; font-weight: 600; }
#Warn { color: $warn; }
#Changed { color: $accent; font-size: 8pt; font-weight: 600; border: 1px solid $accent; border-radius: 3px; padding: 0 5px; }
QListWidget#AppList { font-family: "$sans"; }
QListWidget#AppList::item { padding: 6px 6px; border-radius: 6px; }
QTableWidget::indicator, QListWidget::indicator {
    width: 16px; height: 16px; border: 1.5px solid $line_strong; border-radius: 3px; background: $bg0;
}
QTableWidget::indicator:checked { background: $accent; border-color: $accent; image: url("$check"); }
QPushButton#SysHint { background: transparent; color: $warn; border: 1px solid $warn; padding: 2px 10px;
    font-size: 9pt; }
QPushButton#SysHint[tone="danger"] { color: $danger; border-color: $danger; }
QPushButton#SysHint:hover { background: $bg2; }
QPushButton#UpdHint { background: transparent; color: $warn; border: 1px solid $warn; padding: 2px 10px;
    font-size: 9pt; }
QPushButton#UpdHint:hover { background: $bg2; }
QPushButton#Gear { background: transparent; border: 0; border-radius: 6px; padding: 5px; min-width: 0; }
QPushButton#Gear:hover { background: $bg2; }
QPushButton#Gear:checked { background: $bg3; }
#MidValue { font-family: "$mono"; font-size: 15pt; font-weight: 600; }
#Segmented { background: $bg1; border: 1px solid $line; border-radius: 8px; }
QPushButton#Seg { background: transparent; color: $muted; padding: 5px 14px; border-radius: 6px; }
QPushButton#Seg:hover { color: $ink; background: $bg2; }
QPushButton#Seg:checked { background: $bg3; color: $ink; }
#BigValue { font-family: "$mono"; font-size: 20pt; font-weight: 600; }
#Danger { color: $danger; font-weight: 600; }
#Hint { color: $muted; font-size: 9pt; }
""")


def _write_asset(name, svg):
    d = os.path.join(tempfile.gettempdir(), f"tuxdex-{os.getuid()}")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, name)
    with open(path, "w") as f:
        f.write(svg)
    return path


def apply_theme(app):
    families = set(QFontDatabase.families())

    def pick(cands, fallback):
        for c in cands:
            if c in families:
                return c
        return fallback

    FONTS["sans"] = pick(["IBM Plex Sans", "Noto Sans", "DejaVu Sans", "Cantarell"], app.font().family())
    FONTS["mono"] = pick(["IBM Plex Mono", "JetBrains Mono", "Noto Sans Mono", "DejaVu Sans Mono"],
                         QFontDatabase.systemFont(QFontDatabase.FixedFont).family())
    font = QFont(FONTS["sans"], 10)
    font.setHintingPreference(QFont.PreferNoHinting)
    app.setFont(font)

    check = _write_asset("check.svg", (
        '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">'
        f'<path d="M3.5 8.5l3 3 6-7" fill="none" stroke="{COLORS["on_accent"]}" stroke-width="2.2" '
        'stroke-linecap="round" stroke-linejoin="round"/></svg>'))
    arrow = _write_asset("arrow.svg", (
        '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 12 12">'
        f'<path d="M2.5 4.5l3.5 3.5 3.5-3.5" fill="none" stroke="{COLORS["ink"]}" stroke-width="1.6" '
        'stroke-linecap="round" stroke-linejoin="round"/></svg>'))
    app.setStyle("Fusion")
    app.setStyleSheet(QSS.substitute(COLORS, check=check, arrow=arrow, sans=FONTS["sans"], mono=FONTS["mono"]))


def short_path(p):
    """Home-Ordner als ~ anzeigen, damit kein Benutzername im Bild steht."""
    home = os.path.expanduser("~")
    p = str(p)
    return "~" + p[len(home):] if home not in ("", "/") and (p == home or p.startswith(home + "/")) else p


def repolish(w):
    w.style().unpolish(w)
    w.style().polish(w)
    w.update()


# --------------------------------------------------------------------------
# Hilfsfunktionen: Prozesse
# --------------------------------------------------------------------------

def which(cmd):
    return shutil.which(cmd) is not None


def valid_pkg_tokens(text):
    tokens = text.split()
    if not tokens:
        return None
    for t in tokens:
        if not PKG_NAME_RE.match(t):
            return None
    return tokens


def quoted(tokens):
    return " ".join(shlex.quote(t) for t in tokens)


class _Invoker(QObject):
    """Führt Funktionen aus Worker-Threads im GUI-Thread aus."""
    call = Signal(object)

    def __init__(self):
        super().__init__()
        self.call.connect(self._run, Qt.QueuedConnection)

    @Slot(object)
    def _run(self, fn):
        try:
            fn()
        except Exception:
            import traceback
            tb = traceback.format_exc()
            print(tb, file=sys.stderr)
            try:
                with open(os.path.expanduser("~/tuxdex_error.log"), "a") as f:
                    f.write(f"\n--- {datetime.now().isoformat()} ---\n{tb}")
            except Exception:
                pass
            win = QApplication.activeWindow()
            if hasattr(win, "set_status"):
                win.set_status("Interner Fehler – Details in ~/tuxdex_error.log")


def kernel_modules_missing():
    """True, wenn der laufende Kernel nach einem Update keine Module mehr hat (Neustart nötig)."""
    return not os.path.isdir(f"/usr/lib/modules/{os.uname().release}")


def usb_storage_devices():
    """USB-Massenspeicher auf USB-Ebene: [(Name, Treiber geladen?)] – auch wenn kein Laufwerk entsteht."""
    found = []
    base = "/sys/bus/usb/devices"
    try:
        entries = os.listdir(base)
    except Exception:
        return found
    for e in entries:
        if ":" not in e:
            continue
        iface = os.path.join(base, e)
        try:
            with open(os.path.join(iface, "bInterfaceClass")) as f:
                if f.read().strip() != "08":
                    continue
        except Exception:
            continue
        dev = os.path.join(base, e.split(":")[0])
        name = []
        for fn in ("manufacturer", "product"):
            try:
                with open(os.path.join(dev, fn)) as f:
                    name.append(f.read().strip())
            except Exception:
                pass
        found.append((" ".join(name) or e, os.path.exists(os.path.join(iface, "driver"))))
    return found


_INVOKER = None


def ui(fn):
    _INVOKER.call.emit(fn)


def run_capture_async(args, callback, needs_sudo=False, timeout=60):
    """Führt args (optional mit 'sudo -n' Präfix) im Hintergrund aus.
    callback(rc, stdout, stderr) läuft im GUI-Thread. 'sudo -n' fragt NIE
    nach einem Passwort - schlägt einfach fehl, wenn keine gültige
    Sitzung existiert."""
    full_args = (["sudo", "-n"] + args) if needs_sudo else args

    def worker():
        try:
            p = subprocess.run(full_args, capture_output=True, text=True, timeout=timeout)
            rc, out, err = p.returncode, p.stdout, p.stderr
        except Exception as e:
            rc, out, err = 1, "", str(e)
        ui(lambda: callback(rc, out, err))

    threading.Thread(target=worker, daemon=True).start()


ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07|\x1b[()][A-Za-z0-9]|\x1b[=>]")
# Eine „offene“ letzte Zeile, die auf eine Eingabe wartet (pacman, paru, sudo …)
PROMPT_END_RE = re.compile(r"(\[[^\[\]]{1,40}\]|[:?]|==>)\s*$")


class ProcessRun:
    """Startet einen Prozess und streamt die Ausgabe ins LogView.

    interactive=True: der Prozess läuft in einem Pseudo-Terminal (über
    'script'), damit pacman/paru Fortschritt anzeigen und Rückfragen stellen.
    Wartet der Prozess auf eine Eingabe, erscheint ein Dialog; die Antwort
    wird an den Prozess geschickt."""

    def __init__(self, cmd, log, needs_sudo=False, on_done=None, interactive=False, on_line=None, cwd=None):
        self.log = log
        self.cwd = cwd
        self.on_done = on_done
        self.on_line = on_line   # optional: pro vollständiger Zeile (GUI-Thread)
        self.proc = None
        self.cancelled = False
        self.interactive = interactive and which("script")
        if self.interactive:
            inner = ["script", "-qefc", " ".join(shlex.quote(c) for c in cmd), "/dev/null"]
        else:
            inner = cmd
        self.full_cmd = (["sudo", "-n"] + inner) if needs_sudo else inner
        threading.Thread(target=self._worker, daemon=True).start()

    # -- Steuerung (GUI-Thread) --
    def send(self, text):
        try:
            self.proc.stdin.write(text.encode())
            self.proc.stdin.flush()
        except Exception:
            pass

    def cancel(self):
        self.cancelled = True
        if self.proc and self.proc.poll() is None:
            if self.interactive:
                self.send("\x03")
                QTimer.singleShot(3000, self._kill)
            else:
                self._kill()

    def _kill(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except Exception:
                pass

    # -- Hintergrund --
    def _worker(self):
        env = {**os.environ, "COLUMNS": "110", "LINES": "40"}
        try:
            self.proc = subprocess.Popen(
                self.full_cmd, stdin=subprocess.PIPE if self.interactive else subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, cwd=self.cwd)
        except Exception as e:
            msg = f"Fehler beim Start: {e}\n"
            if self.log is not None:
                ui(lambda m=msg: self.log.append_text(m))
            if self.on_done:
                ui(lambda: self.on_done(1))
            return
        fd = self.proc.stdout.fileno()
        tail = ""          # aktuelle, noch nicht abgeschlossene Zeile
        asked_for = None   # Prompt, für den schon ein Dialog offen ist
        self.answered = threading.Event()
        while True:
            ready, _, _ = select.select([fd], [], [], 0.5)
            if ready:
                data = os.read(fd, 8192)
                if not data:
                    break
                text = data.decode(errors="replace")
                if self.log is not None:
                    ui(lambda t=text: self.log.write_raw(t))
                clean = ANSI_RE.sub("", text).replace("\r\n", "\n")
                if self.on_line:
                    self._linebuf = getattr(self, "_linebuf", "") + clean
                    *full, self._linebuf = self._linebuf.split("\n")
                    for ln in full:
                        ui(lambda l=ln: self.on_line(l))
                tail = (tail + clean).rsplit("\n", 1)[-1].rsplit("\r", 1)[-1]
                if asked_for is not None and tail != asked_for:
                    asked_for = None
            elif self.interactive and tail.strip() and asked_for != tail and PROMPT_END_RE.search(tail):
                # Prozess ist still und die letzte Zeile sieht nach einer Frage aus
                asked_for = tail
                self.answered.clear()
                ui(lambda t=tail: self._ask(t))
                self.answered.wait()
            elif self.proc.poll() is not None:
                break
        rc = self.proc.wait()
        if self.on_done:
            ui(lambda: self.on_done(rc))

    def _ask(self, prompt):
        try:
            if self.cancelled:
                return
            answer = ask_process_prompt(self.log.window(), prompt, self.log.last_lines(14))
            if answer is None:
                self.log.write_raw("\n[Abgebrochen]\n")
                self.cancel()
            else:
                self.send(answer + "\n")
        finally:
            self.answered.set()


def run_streaming(cmd, log, needs_sudo=False, on_done=None, clear_first=True, interactive=False, on_line=None,
                  cwd=None):
    """Führt cmd aus und streamt die Ausgabe live in das LogView - alles
    innerhalb des Programmfensters, kein externes Terminal. Gibt ein
    ProcessRun-Objekt zurück (u. a. zum Abbrechen)."""
    if clear_first:
        log.set_text("")
    return ProcessRun(cmd, log, needs_sudo=needs_sudo, on_done=on_done, interactive=interactive,
                      on_line=on_line, cwd=cwd)


class SequenceRun:
    """Mehrere Schritte nacheinander; cancel() stoppt den laufenden Schritt und alle weiteren."""

    def __init__(self, steps, log, on_all_done=None):
        self.steps, self.log, self.on_all_done = steps, log, on_all_done
        self.i = 0
        self.current = None
        self.cancelled = False
        log.set_text("")
        self._next()

    def _next(self):
        if self.cancelled or self.i >= len(self.steps):
            if self.on_all_done:
                self.on_all_done()
            return
        step = self.steps[self.i]
        self.i += 1
        self.log.append_text(f"\n$ {step['label']}\n")

        def done(rc):
            self.log.append_text(f"\n[Exit-Code {rc}]\n")
            self._next()

        self.current = run_streaming(step["cmd"], self.log, needs_sudo=step["needs_sudo"], on_done=done,
                                     clear_first=False, interactive=step.get("interactive", False),
                                     cwd=step.get("cwd"))

    def cancel(self):
        self.cancelled = True
        if self.current:
            self.current.cancel()


def run_sequence(steps, log, on_all_done=None):
    """Führt mehrere Schritte nacheinander aus. steps: Liste von Dicts
    {'cmd': [...], 'needs_sudo': bool, 'label': str, 'interactive': bool}."""
    return SequenceRun(steps, log, on_all_done)


# --------------------------------------------------------------------------
# Bausteine aus dem Design-System
# --------------------------------------------------------------------------

def Button(text, variant="ghost", on_click=None, tooltip=None):
    b = QPushButton(text)
    b.setProperty("variant", variant)
    b.setCursor(Qt.PointingHandCursor)
    b.setFocusPolicy(Qt.TabFocus)  # Fokusring nur bei Tastatur-Navigation
    if on_click:
        b.clicked.connect(on_click)
    if tooltip:
        b.setToolTip(tooltip)
    return b


def Label(text="", name=None, wrap=False):
    lbl = QLabel(text)
    if name:
        lbl.setObjectName(name)
    lbl.setWordWrap(wrap)
    return lbl


class StatusBadge(QLabel):
    GLYPH = {"ok": "●", "warn": "▲", "danger": "✕", "info": "●", "off": "○"}

    def __init__(self, tone="off", text=""):
        super().__init__()
        self.setObjectName("Badge")
        self.set(tone, text)

    def set(self, tone, text):
        self.setProperty("tone", tone)
        self.setText(f"{self.GLYPH.get(tone, '○')}  {text}")
        repolish(self)


class Panel(QFrame):
    """Karte auf bg-200 mit Titelzeile (Titel links, Aktionen rechts)."""

    def __init__(self, title=None, actions=()):
        super().__init__()
        self.setObjectName("Panel")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 16)
        outer.setSpacing(12)
        if title or actions:
            head = QHBoxLayout()
            head.setSpacing(8)
            if title:
                head.addWidget(Label(title, "PanelTitle"))
            head.addStretch(1)
            for a in actions:
                head.addWidget(a)
            outer.addLayout(head)
        self.body = QVBoxLayout()
        self.body.setSpacing(8)
        outer.addLayout(self.body)


def Field(label, widget):
    box = QVBoxLayout()
    box.setSpacing(4)
    box.addWidget(Label(label.upper(), "FieldLabel"))
    box.addWidget(widget)
    return box


def LineEdit(text="", placeholder="", mono=False, width=None):
    e = QLineEdit(text)
    if placeholder:
        e.setPlaceholderText(placeholder)
    if mono:
        e.setProperty("mono", True)
    if width:
        e.setMinimumWidth(width)
    e.setMinimumHeight(38)
    return e


class LogView(QPlainTextEdit):
    """Panel „Ausgabe“: Monospace, farbige Zeilen je nach Inhalt."""
    RE_EXIT = re.compile(r"^\[Exit-Code (-?\d+)\]")

    def __init__(self, min_height=140):
        super().__init__()
        self.setObjectName("Log")
        self.setReadOnly(True)
        self.setMinimumHeight(min_height)
        self.setFont(QFont(FONTS["mono"], 10))
        self._fmts = {}
        for tag, key in (("cmd", "accent"), ("head", "info"), ("ok", "ok"), ("warn", "warn"),
                         ("err", "danger"), ("muted", "muted"), (None, "ink")):
            f = QTextCharFormat()
            f.setForeground(QColor(COLORS[key]))
            self._fmts[tag] = f

    def _tag(self, line):
        s = line.strip()
        if not s:
            return None
        m = self.RE_EXIT.match(s)
        if m:
            return "ok" if m.group(1) == "0" else "err"
        if s.startswith("$ "):
            return "cmd"
        if s.startswith(("==", "::")):
            return "head"
        low = s.lower()
        if low.startswith(("error", "fehler", "e:")) or "fehlgeschlagen" in low or "failed" in low:
            return "err"
        if low.startswith(("warning", "warnung", "w:")):
            return "warn"
        return None

    def set_text(self, s):
        self.clear()
        self.append_text(s)

    def append_text(self, s):
        self.write_raw(s)

    def write_raw(self, s):
        """Schreibt Terminal-Ausgabe: entfernt Farbcodes, \\r überschreibt die
        aktuelle Zeile (Fortschrittsbalken), Zeilen werden nach Inhalt eingefärbt."""
        s = ANSI_RE.sub("", s)
        if getattr(self, "_pending_cr", False):
            s = "\r" + s
        self._pending_cr = s.endswith("\r")
        if self._pending_cr:
            s = s[:-1]
        s = s.replace("\r\n", "\n")
        cur = self.textCursor()
        cur.movePosition(QTextCursor.End)
        for part in re.split(r"(\n|\r)", s):
            if part == "\n":
                cur.insertText("\n")
            elif part == "\r":
                cur.movePosition(QTextCursor.StartOfBlock, QTextCursor.KeepAnchor)
                cur.removeSelectedText()
            elif part:
                cur.insertText(part, self._fmts[self._tag(cur.block().text() + part)])
        self.setTextCursor(cur)
        self.ensureCursorVisible()

    def last_lines(self, n):
        lines = [l for l in self.toPlainText().splitlines() if l.strip()]
        return "\n".join(lines[-n:])


class UsageBar(QWidget):
    """Belegung (Swap/Datenträger): Name, Wert, Prozent, Balken. Ab 80 % warn, ab 90 % danger."""

    def __init__(self, label, used, total, unit="GiB"):
        super().__init__()
        self.label, self.used, self.total, self.unit = label, used, total, unit
        self.setMinimumHeight(36)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def sizeHint(self):
        return QSize(320, 36)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pct = 0 if not self.total else max(0, min(100, round(self.used / self.total * 100)))
        mono = QFont(FONTS["mono"], 10)
        p.setFont(mono)
        p.setPen(QColor(COLORS["ink"]))
        w = self.width()
        p.drawText(QRectF(0, 0, w, 20), Qt.AlignLeft | Qt.AlignVCenter, self.label)
        g = 1024 ** 3 if self.unit == "GiB" else 1
        val = f"{fmt_bytes(self.used * g)} / {fmt_bytes(self.total * g)}   {pct} %"
        bold = QFont(FONTS["mono"], 10)
        bold.setWeight(QFont.DemiBold)
        p.setFont(bold)
        p.drawText(QRectF(0, 0, w, 20), Qt.AlignRight | Qt.AlignVCenter, val)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(COLORS["bg3"]))
        p.drawRoundedRect(QRectF(0, 26, w, 8), 3, 3)
        color = COLORS["danger"] if pct >= 90 else COLORS["warn"] if pct >= 80 else COLORS["accent"]
        p.setBrush(QColor(color))
        if pct:
            p.drawRoundedRect(QRectF(0, 26, max(w * pct / 100, 6), 8), 3, 3)
        p.end()


class ProgressBar(QWidget):
    """Fortschrittsbalken; value=None zeigt einen wandernden Balken (unbestimmt)."""

    def __init__(self):
        super().__init__()
        self.value, self.text, self._phase = 0, "", 0
        self.setFixedHeight(22)
        self._t = QTimer(self)
        self._t.timeout.connect(self._anim)

    def set(self, value, text=""):
        self.value, self.text = value, text
        if value is None and not self._t.isActive():
            self._t.start(60)
        elif value is not None:
            self._t.stop()
        self.update()

    def _anim(self):
        self._phase = (self._phase + 2) % 100
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), 10
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(COLORS["bg3"]))
        p.drawRoundedRect(QRectF(0, 6, w - 70, h), 5, 5)
        p.setBrush(QColor(COLORS["accent"]))
        if self.value is None:
            seg = (w - 70) * 0.25
            x = (w - 70 + seg) * self._phase / 100 - seg
            p.setClipRect(QRectF(0, 6, w - 70, h))
            p.drawRoundedRect(QRectF(x, 6, seg, h), 5, 5)
            p.setClipping(False)
        elif self.value > 0:
            p.drawRoundedRect(QRectF(0, 6, max(10, (w - 70) * self.value / 100), h), 5, 5)
        f = QFont(FONTS["mono"], 10)
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        p.setPen(QColor(COLORS["ink"]))
        p.drawText(QRectF(w - 64, 0, 64, 22), Qt.AlignRight | Qt.AlignVCenter,
                   self.text if self.value is not None else "…")
        p.end()


def page_header(title, *right):
    row = QHBoxLayout()
    row.setSpacing(8)
    row.addWidget(Label(title, "PageTitle"))
    row.addStretch(1)
    for w in right:
        row.addWidget(w)
    return row


class Page(QScrollArea):
    """Seite eines Moduls: scrollbar, 24px Rand, 16px zwischen Blöcken."""

    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        inner.setObjectName("Page")
        self.setWidget(inner)
        self.lay = QVBoxLayout(inner)
        self.lay.setContentsMargins(24, 20, 24, 20)
        self.lay.setSpacing(16)


# --------------------------------------------------------------------------
# Dialoge
# --------------------------------------------------------------------------

def _msg(parent, icon, title, text, buttons):
    box = QMessageBox(parent)
    box.setIcon(icon)
    box.setWindowTitle(title)
    box.setText(text)
    result = {}
    for label, variant, value in buttons:
        b = box.addButton(label, QMessageBox.AcceptRole if value else QMessageBox.RejectRole)
        b.setProperty("variant", variant)
        result[b] = value
        if value:
            box.setDefaultButton(b)
    box.exec()
    return result.get(box.clickedButton(), False)


def ask_confirm(parent, title, text, confirm="Bestätigen", danger=False):
    return _msg(parent, QMessageBox.Question, title, text,
                [("Abbrechen", "ghost", False), (confirm, "danger" if danger else "primary", True)])


def show_info(parent, title, text):
    _msg(parent, QMessageBox.Information, title, text, [("OK", "primary", True)])


def show_warning(parent, title, text):
    _msg(parent, QMessageBox.Warning, title, text, [("OK", "primary", True)])


def show_error(parent, title, text):
    _msg(parent, QMessageBox.Critical, title, text, [("OK", "primary", True)])


class PasswordDialog(QDialog):
    def __init__(self, parent, title="Administrator-Passwort"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(440)
        lay = QVBoxLayout(self)
        lay.setSizeConstraint(QLayout.SetMinimumSize)
        spacer = QWidget()
        spacer.setFixedSize(380, 0)
        lay.addWidget(spacer)
        lay.setContentsMargins(32, 28, 32, 24)
        lay.setSpacing(12)
        lay.addWidget(Label("sudo-Passwort eingeben", "DialogTitle"))
        lay.addWidget(Label("Wird für die Dauer des Programmlaufs gemerkt – "
                            "du musst es danach nicht erneut eingeben.", "Small", wrap=True))
        self.entry = LineEdit()
        self.entry.setEchoMode(QLineEdit.Password)
        self.entry.setMinimumHeight(42)
        f = self.entry.font()
        f.setPointSize(12)
        self.entry.setFont(f)
        self.error = Label("", "Error")
        self.error.hide()
        lay.addLayout(Field("Passwort", self.entry))
        lay.addWidget(self.error)
        btns = QHBoxLayout()
        btns.addStretch(1)
        btns.addWidget(Button("Abbrechen", "ghost", self.reject))
        ok = Button("Anmelden", "primary", self.accept)
        ok.setDefault(True)
        btns.addWidget(ok)
        lay.addSpacing(8)
        lay.addLayout(btns)
        self.entry.returnPressed.connect(self.accept)
        self.entry.setFocus()


def ask_password(parent, title="Administrator-Passwort", error=None):
    dlg = PasswordDialog(parent, title)
    if error:
        dlg.error.setText(error)
        dlg.error.show()
    if dlg.exec() == QDialog.Accepted:
        return dlg.entry.text()
    return None


class PromptDialog(QDialog):
    """Rückfrage eines laufenden Prozesses (pacman/paru) als Fenster."""

    def __init__(self, parent, prompt, context, mode, yes_char="j", default_yes=True):
        super().__init__(parent)
        self.setWindowTitle("Rückfrage")
        self.answer = None
        lay = QVBoxLayout(self)
        lay.setSizeConstraint(QLayout.SetMinimumSize)
        lay.setContentsMargins(28, 24, 28, 20)
        lay.setSpacing(12)
        spacer = QWidget()
        spacer.setFixedSize(560, 0)
        lay.addWidget(spacer)
        lay.addWidget(Label("Der Vorgang wartet auf deine Antwort", "DialogTitle"))
        ctx = QPlainTextEdit(context)
        ctx.setObjectName("Log")
        ctx.setReadOnly(True)
        ctx.setFont(QFont(FONTS["mono"], 9))
        ctx.setMinimumHeight(180)
        ctx.moveCursor(QTextCursor.End)
        lay.addWidget(ctx)
        q = Label(prompt.strip(), "Value", wrap=True)
        lay.addWidget(q)
        btns = QHBoxLayout()
        btns.setSpacing(8)
        stop = Button("Vorgang abbrechen", "danger", self.reject)
        btns.addWidget(stop)
        btns.addStretch(1)
        if mode == "yesno":
            no = Button("Nein", "ghost", lambda: self._done("n"))
            yes = Button("Ja", "primary", lambda: self._done(yes_char))
            btns.addWidget(no)
            btns.addWidget(yes)
            (yes if default_yes else no).setDefault(True)
            (yes if default_yes else no).setFocus()
        else:
            self.entry = LineEdit(mono=True, placeholder="leer lassen = Standard")
            lay.insertWidget(lay.count(), self.entry)
            btns.addWidget(Button("Standard übernehmen", "ghost", lambda: self._done("")))
            ok = Button("Senden", "primary", lambda: self._done(self.entry.text()))
            ok.setDefault(True)
            btns.addWidget(ok)
            self.entry.returnPressed.connect(lambda: self._done(self.entry.text()))
            self.entry.setFocus()
        lay.addLayout(btns)

    def _done(self, answer):
        self.answer = answer
        self.accept()


def ask_process_prompt(parent, prompt, context):
    """Gibt die Antwort (ohne Zeilenumbruch) zurück oder None = Vorgang abbrechen."""
    if re.search(r"passw|kennwort", prompt, re.I):
        return ask_password(parent, "Passwort angefragt")
    m = re.search(r"\[([JjYy])/([Nn])\]|\[([Nn])/([JjYy])\]", prompt)
    if m:
        if m.group(1):
            dlg = PromptDialog(parent, prompt, context, "yesno", m.group(1).lower(), m.group(1).isupper())
        else:
            dlg = PromptDialog(parent, prompt, context, "yesno", m.group(4).lower(), m.group(4).isupper())
    else:
        dlg = PromptDialog(parent, prompt, context, "text")
    if dlg.exec() == QDialog.Accepted:
        return dlg.answer
    return None


class PrivilegeManager:
    """Fragt bei Bedarf einmal per Dialog nach dem sudo-Passwort und hält
    die sudo-Sitzung danach über 'sudo -v' aktiv. Weitere Aufrufe nutzen
    'sudo -n' (nie interaktiv) und profitieren automatisch vom Cache -
    das gilt auch für interne sudo-Aufrufe von 'paru'."""

    def __init__(self, root, on_change=None):
        self.root = root
        self.on_change = on_change

    def is_authenticated(self):
        try:
            r = subprocess.run(["sudo", "-n", "-v"], capture_output=True, text=True, timeout=10)
            return r.returncode == 0
        except Exception:
            return False

    def is_authenticated_nonblocking(self):
        """Prüft ohne die Sitzung zu verlängern, ob sudo ohne Passwort geht."""
        try:
            r = subprocess.run(["sudo", "-n", "true"], capture_output=True, text=True, timeout=10)
            return r.returncode == 0
        except Exception:
            return False

    def _notify(self, ok):
        if self.on_change:
            self.on_change(ok)

    def ensure(self, parent=None):
        """Blockiert kurz (GUI-Thread!) und zeigt bei Bedarf den Passwort-
        Dialog. Gibt True zurück, wenn eine gültige sudo-Sitzung besteht."""
        if self.is_authenticated():
            self._notify(True)
            return True

        widget = parent or self.root
        error = None
        for attempt in range(3):
            pw = ask_password(widget, error=error)
            if pw is None:
                return False
            try:
                r = subprocess.run(
                    ["sudo", "-S", "-p", "", "-v"],
                    input=pw + "\n", capture_output=True, text=True, timeout=15,
                )
            except Exception as e:
                show_error(widget, "Fehler", f"Authentifizierung fehlgeschlagen: {e}")
                self._notify(False)
                return False
            finally:
                pw = None
            if r.returncode == 0:
                self._notify(True)
                return True
            left = 2 - attempt
            error = (f"Falsches Passwort – noch {left} Versuch{'e' if left != 1 else ''}."
                     if left else None)
        show_error(widget, "Fehler", "Passwort falsch oder Authentifizierung fehlgeschlagen.")
        self._notify(False)
        return False

    def logout(self):
        try:
            subprocess.run(["sudo", "-k"], timeout=10)
        except Exception:
            pass
        self._notify(False)


# --------------------------------------------------------------------------
# Modul: Updates (inkl. Update-Informationen)
# --------------------------------------------------------------------------

CACHE_DIR = os.path.join(os.path.expanduser("~/.cache"), "tuxdex")
UPDATE_CACHE = os.path.join(CACHE_DIR, "updates.json")

# Pakete, deren Update besondere Aufmerksamkeit verdient (Kernel, Boot, Basis-System, Grafik)
CRITICAL_PKGS = {
    "linux", "linux-lts", "linux-zen", "linux-hardened", "linux-rt", "linux-firmware",
    "systemd", "systemd-libs", "glibc", "gcc-libs", "grub", "mkinitcpio", "pacman", "sudo",
    "filesystem", "openssl", "mesa", "nvidia", "nvidia-open", "nvidia-dkms", "nvidia-utils",
    "nvidia-lts", "xorg-server", "wayland", "plasma-workspace", "kwin", "gnome-shell", "mutter",
    "python", "efibootmgr", "systemd-boot", "shim",
}
REBOOT_PKGS = {"linux", "linux-lts", "linux-zen", "linux-hardened", "linux-rt", "linux-firmware",
               "systemd", "glibc", "nvidia", "nvidia-open", "nvidia-dkms", "nvidia-utils",
               "nvidia-lts", "mesa"}

# Programme, die ihre Hauptversion routinemäßig hochzählen – dort ist ein Sprung kein „Major“
RAPID_RELEASE = {"firefox", "firefox-developer-edition", "librewolf", "chromium", "google-chrome",
                 "brave-bin", "vivaldi", "opera", "thunderbird", "microsoft-edge-stable-bin",
                 "zen-browser-bin", "ungoogled-chromium", "discord", "signal-desktop", "spotify"}
# Hier zählt schon ein Sprung der zweiten Stelle als Major (z. B. Python 3.12 → 3.13)
MINOR_IS_MAJOR = {"python", "perl", "ruby", "php", "llvm", "llvm-libs", "qt6-base", "qt5-base",
                  "boost", "boost-libs", "icu", "protobuf"}

UPDATE_RE = re.compile(r"^(\S+)\s+(\S+)\s+->\s+(\S+)")


def _version_key(v, depth=1):
    epoch, rest = v.split(":", 1) if ":" in v else ("0", v)
    nums = re.findall(r"\d+", rest.split("-")[0])[:depth]
    return epoch, (tuple(int(n) for n in nums) if nums else None)


def classify_update(name, old, new):
    """'major' = Hauptversion/Epoch springt, 'system' = kritisches Paket, '' = normal."""
    if old and new and old != "—" and name not in RAPID_RELEASE:
        depth = 2 if name in MINOR_IS_MAJOR else 1
        e1, m1 = _version_key(old, depth)
        e2, m2 = _version_key(new, depth)
        if e1 != e2 or (m1 is not None and m2 is not None and m1 != m2):
            return "major"
    if name in CRITICAL_PKGS:
        return "system"
    return ""


def fmt_ago(ts):
    d = max(0, int(time.time() - ts))
    if d < 60:
        return "gerade eben"
    if d < 3600:
        return f"vor {d // 60} Min."
    if d < 86400:
        return f"vor {d // 3600} Std."
    return datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")


class UpdaterTab(Page):
    COLS = [("Paket", 220), ("Quelle", 90), ("Installiert", 170), ("Neu", 170), ("Hinweis", 160)]

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.checking = False
        self.updates = []
        self.checked_at = None

        self.badge = StatusBadge("off", "Noch nicht geprüft")
        self.lay.addLayout(page_header("System-Update", self.badge))

        row = QHBoxLayout()
        row.setSpacing(16)

        src = Panel("Quellen")
        self.cb_pacman = QCheckBox("Pacman")
        self.cb_pacman.setChecked(True)
        self.cb_aur = QCheckBox("AUR (paru)" if which("paru") else "AUR (paru nicht installiert)")
        self.cb_aur.setChecked(which("paru"))
        self.cb_aur.setEnabled(which("paru"))
        self.cb_flatpak = QCheckBox("Flatpak" if which("flatpak") else "Flatpak (nicht installiert)")
        self.cb_flatpak.setChecked(which("flatpak"))
        self.cb_flatpak.setEnabled(which("flatpak"))
        for cb in (self.cb_pacman, self.cb_flatpak, self.cb_aur):
            src.body.addWidget(cb)
        src.body.addSpacing(8)
        self.btn_update = Button("Update starten", "primary", self.start_update)
        src.body.addWidget(self.btn_update)
        self.btn_check = Button("Auf Updates prüfen", "ghost", self.check_updates)
        src.body.addWidget(self.btn_check)
        self.btn_cancel = Button("Update abbrechen", "danger", self.cancel_update)
        self.btn_cancel.hide()
        src.body.addWidget(self.btn_cancel)
        self.run = None
        src.body.addStretch(1)
        src.setFixedWidth(260)
        row.addWidget(src)

        info = Panel("Update-Informationen",
                     [Button("↻", "icon", self.load_last_update_times, "Aktualisieren")])
        self.info_grid = QGridLayout()
        self.info_grid.setHorizontalSpacing(24)
        self.info_grid.setVerticalSpacing(12)
        info.body.addLayout(self.info_grid)
        self.major_note = Label("", "Danger", wrap=True)
        self.major_note.hide()
        info.body.addWidget(self.major_note)
        info.body.addStretch(1)
        row.addWidget(info, 1)
        self.lay.addLayout(row)

        lst = Panel("Verfügbare Updates")
        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels([c[0].upper() for c in self.COLS])
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        for i, (_, w) in enumerate(self.COLS):
            self.table.setColumnWidth(i, w)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setMinimumHeight(200)
        self.empty_label = Label("Noch nicht geprüft – „Auf Updates prüfen“ klicken.", "Muted")
        lst.body.addWidget(self.empty_label)
        lst.body.addWidget(self.table)
        self.table.hide()
        self.lay.addWidget(lst, 1)

        out = Panel("Ausgabe")
        self.log = LogView(180)
        out.body.addWidget(self.log)
        self.lay.addWidget(out, 1)

        self.load_last_update_times()
        self._load_cache()
        # Beim App-Start nach System-Updates suchen (pacman, AUR, Flatpak) – abschaltbar in den Einstellungen
        if load_settings().get("sys_check_on_start", True):
            QTimer.singleShot(1500, lambda: self.check_updates(silent=True))

    # ---- Anzeige --------------------------------------------------------

    def _info_item(self, row, label, value):
        self.info_grid.addLayout(Field(label, Label(value, "Value", wrap=True)), row // 2, row % 2)

    def load_last_update_times(self):
        while self.info_grid.count():
            item = self.info_grid.takeAt(0)
            lay = item.layout()
            if lay:
                while lay.count():
                    w = lay.takeAt(0).widget()
                    if w:
                        w.deleteLater()
        last_pacman = "keine Angabe gefunden"
        try:
            with open("/var/log/pacman.log", errors="ignore") as f:
                content = f.read()
            matches = re.findall(r"\[([^\]]+)\][^\n]*starting full system upgrade", content)
            if matches:
                last_pacman = matches[-1]
        except Exception:
            pass
        self._info_item(0, "Letztes vollständiges Update", last_pacman)
        self._info_item(1, "Zuletzt geprüft",
                        fmt_ago(self.checked_at) if self.checked_at else "noch nie")
        if which("flatpak"):
            try:
                mtime = os.path.getmtime("/var/lib/flatpak")
                fp = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
            except Exception:
                fp = "nicht ermittelbar"
            self._info_item(2, "Letzte Änderung Flatpak (Näherung)", fp)

    def _render(self):
        ups = sorted(self.updates, key=lambda u: ({"major": 0, "system": 1}.get(u["kind"], 2), u["name"]))
        self.table.setRowCount(0)
        danger = QColor(COLORS["danger"])
        warn = QColor(COLORS["warn"])
        for u in ups:
            r = self.table.rowCount()
            self.table.insertRow(r)
            hint = {"major": "▲ Major-Version", "system": "▲ System/Kernel"}.get(u["kind"], "")
            if u["name"] in REBOOT_PKGS:
                hint = (hint + " · Neustart") if hint else "Neustart nötig"
            for c, v in enumerate((u["name"], u["source"], u["old"], u["new"], hint)):
                it = QTableWidgetItem(v)
                if u["kind"] == "major" and c in (0, 3, 4):
                    it.setForeground(danger)
                elif u["kind"] == "system" and c in (0, 4):
                    it.setForeground(warn)
                self.table.setItem(r, c, it)

        n = len(ups)
        important = [u for u in ups if u["kind"]]
        if self.checked_at is not None and hasattr(self.app, "show_sys_updates"):
            self.app.show_sys_updates(n, len(important))
        majors = [u for u in ups if u["kind"] == "major"]
        reboot = [u["name"] for u in ups if u["name"] in REBOOT_PKGS]
        if self.checked_at is None:
            self.badge.set("off", "Noch nicht geprüft")
        elif n == 0:
            self.badge.set("ok", "System aktuell")
        elif important:
            self.badge.set("danger", f"{n} Updates · {len(important)} wichtig")
        else:
            self.badge.set("warn", f"{n} Updates verfügbar")

        def names(lst):
            return ", ".join(lst[:8]) + (" …" if len(lst) > 8 else "")
        lines = []
        if majors:
            lines.append(f'<span style="color:{COLORS["danger"]}">▲ Major-Updates: '
                         f'{names([u["name"] for u in majors])} – vorher die Arch-News lesen '
                         f'(archlinux.org/news).</span>')
        sys_ups = [u["name"] for u in important if u["kind"] == "system"]
        if sys_ups:
            lines.append(f'<span style="color:{COLORS["warn"]}">▲ System-Pakete: {names(sys_ups)}</span>')
        if kernel_modules_missing():
            lines.append(f'<span style="color:{COLORS["danger"]}">✕ Kernel aktualisiert – bitte neu starten '
                         f'(sonst werden z. B. USB-Sticks nicht erkannt).</span>')
        if reboot:
            lines.append(f'<span style="color:{COLORS["muted"]}">Nach dem Update ist ein Neustart nötig '
                         f'({names(reboot)}).</span>')
        self.major_note.setTextFormat(Qt.RichText)
        self.major_note.setText("<br>".join(lines))
        self.major_note.setVisible(bool(lines))
        self.table.setMinimumHeight(min(max(n, 3), 12) * 30 + 44)

        self.table.setVisible(n > 0)
        self.empty_label.setVisible(n == 0)
        if self.checked_at is not None and n == 0:
            self.empty_label.setText("Keine Updates verfügbar – das System ist aktuell.")
        self.load_last_update_times()

    # ---- Cache ----------------------------------------------------------

    def _load_cache(self):
        try:
            with open(UPDATE_CACHE) as f:
                data = json.load(f)
            self.updates = data.get("updates", [])
            self.checked_at = float(data["checked_at"])
        except Exception:
            self.updates, self.checked_at = [], None
        self._render()

    def _save_cache(self):
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(UPDATE_CACHE, "w") as f:
                json.dump({"checked_at": self.checked_at, "updates": self.updates}, f)
        except Exception:
            pass

    # ---- Aktionen -------------------------------------------------------

    def check_updates(self, silent=False):
        if self.checking:
            return
        self.checking = True
        self.btn_check.setEnabled(False)
        self.btn_check.setText("Prüfe …")
        if not silent:
            self.log.set_text("Prüfe auf Updates…\n")
        self.badge.set("info", "Prüfe …")

        def worker():
            parts, found = [], []
            if which("checkupdates"):
                r = subprocess.run(["checkupdates"], capture_output=True, text=True)
                for line in r.stdout.splitlines():
                    m = UPDATE_RE.match(line)
                    if m:
                        found.append(("Pacman",) + m.groups())
                parts.append("== Pacman ==\n" + (r.stdout.strip() or "Keine Updates verfügbar."))
            else:
                parts.append("== Pacman ==\ncheckupdates (Paket pacman-contrib) nicht installiert.")

            if which("paru"):
                r = subprocess.run(["paru", "-Qua"], capture_output=True, text=True)
                for line in r.stdout.splitlines():
                    m = UPDATE_RE.match(line)
                    if m:
                        found.append(("AUR",) + m.groups())
                parts.append("== AUR ==\n" + (r.stdout.strip() or "Keine Updates verfügbar."))
            else:
                parts.append("== AUR ==\nparu nicht installiert.")

            if which("flatpak"):
                r = subprocess.run(["flatpak", "remotes", "--columns=name"], capture_output=True, text=True)
                remotes = [l.strip() for l in r.stdout.splitlines() if l.strip()]
                fp_parts = []
                for remote in remotes:
                    r2 = subprocess.run(["flatpak", "remote-ls", "--updates", "--columns=application,version",
                                         remote], capture_output=True, text=True)
                    if r2.stdout.strip():
                        fp_parts.append(f"[{remote}]\n{r2.stdout.strip()}")
                        for line in r2.stdout.splitlines():
                            cols = line.split("\t")
                            if cols and cols[0].strip():
                                new = cols[1].strip() if len(cols) > 1 and cols[1].strip() else "—"
                                found.append(("Flatpak", cols[0].strip(), "—", new))
                parts.append("== Flatpak ==\n" + ("\n".join(fp_parts) if fp_parts else "Keine Updates verfügbar."))
            else:
                parts.append("== Flatpak ==\nflatpak nicht installiert.")

            text = "\n\n".join(parts)
            ups = [{"source": s, "name": n, "old": o, "new": nw, "kind": classify_update(n, o, nw)}
                   for s, n, o, nw in found]

            def show():
                self.checking = False
                self.btn_check.setEnabled(True)
                self.btn_check.setText("Auf Updates prüfen")
                if not silent:
                    self.log.set_text(text)
                self.updates = ups
                self.checked_at = time.time()
                self._save_cache()
                self._render()
            ui(show)

        threading.Thread(target=worker, daemon=True).start()

    def start_update(self):
        pacman = self.cb_pacman.isChecked()
        aur = self.cb_aur.isChecked() and which("paru")
        flatpak = self.cb_flatpak.isChecked() and which("flatpak")

        if not (pacman or aur or flatpak):
            show_info(self, "Nichts ausgewählt", "Bitte mindestens eine Quelle auswählen.")
            return
        text = "System jetzt aktualisieren?"
        majors = [u["name"] for u in self.updates if u["kind"] == "major"]
        if majors:
            text += ("\n\nAchtung, Major-Updates: " + ", ".join(majors[:10])
                     + "\nLies vorher die Arch-News (archlinux.org/news).")
        if not ask_confirm(self, "Update starten", text, "Update starten"):
            return
        if (pacman or aur) and not self.app.priv.ensure(self):
            return

        steps = []
        if pacman and aur:
            steps.append({"cmd": ["paru", "-Syu"], "needs_sudo": False, "interactive": True,
                          "label": "paru -Syu  (Repos + AUR)"})
        elif pacman:
            steps.append({"cmd": ["pacman", "-Syu"], "needs_sudo": True, "interactive": True,
                          "label": "sudo pacman -Syu"})
        elif aur:
            steps.append({"cmd": ["paru", "-Sua"], "needs_sudo": False, "interactive": True,
                          "label": "paru -Sua"})
        if flatpak:
            steps.append({"cmd": ["flatpak", "update", "-y"], "needs_sudo": False, "interactive": True,
                          "label": "flatpak update"})

        self.btn_update.setEnabled(False)
        self.btn_update.setText("Läuft …")
        self.btn_cancel.show()
        self.badge.set("info", "Update läuft")

        def all_done():
            cancelled = self.run.cancelled
            self.run = None
            self.btn_cancel.hide()
            self.btn_update.setEnabled(True)
            self.btn_update.setText("Update starten")
            self.app.set_status("Update abgebrochen." if cancelled else "Update abgeschlossen.")
            self.check_updates(silent=True)   # Liste & gespeicherten Stand auffrischen

        self.run = run_sequence(steps, self.log, on_all_done=all_done)
        self.app.set_status("Update läuft … Rückfragen erscheinen als Fenster.")

    def cancel_update(self):
        if self.run and ask_confirm(self, "Update abbrechen", "Laufendes Update wirklich abbrechen?\n\n"
                                    "Pacman bricht sauber ab, solange noch nichts installiert wird.",
                                    "Abbrechen", danger=True):
            self.run.cancel()


# --------------------------------------------------------------------------
# Modul: Software (Übersicht + Install/Uninstall)
# --------------------------------------------------------------------------

_DEC_UNITS = {"B": 1, "kB": 1000, "KB": 1000, "MB": 1000 ** 2, "GB": 1000 ** 3, "TB": 1000 ** 4,
              "KiB": 1024, "MiB": 1024 ** 2, "GiB": 1024 ** 3, "TiB": 1024 ** 4, "bytes": 1}


def parse_size(text):
    m = re.search(r"([\d.,]+)\s*([A-Za-z]+)", text or "")
    if not m:
        return 0
    try:
        return int(float(m.group(1).replace(",", ".")) * _DEC_UNITS.get(m.group(2), 1))
    except ValueError:
        return 0


def pacman_infos(names=None):
    """{name: {version, desc, size, date, url, reason, required_by, depends}} über LC_ALL=C pacman -Qi"""
    cmd = ["pacman", "-Qi"] + (list(names) if names else [])
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, "LC_ALL": "C"},
                             timeout=120).stdout
    except Exception:
        return {}
    res = {}
    for block in out.split("\n\n"):
        d, key = {}, None
        for line in block.splitlines():
            if not line.strip():
                continue
            if line[:1] != " " and ":" in line:
                key, _, val = line.partition(":")
                key = key.strip()
                d[key] = val.strip()
            elif key:
                d[key] += " " + line.strip()
        if "Name" not in d:
            continue
        try:
            date = parse_c_date(d.get("Install Date", "")).timestamp()
        except Exception:
            date = 0
        res[d["Name"]] = {
            "version": d.get("Version", ""), "desc": d.get("Description", ""),
            "size": parse_size(d.get("Installed Size", "")), "date": date, "url": d.get("URL", ""),
            "reason": d.get("Install Reason", ""),
            "required_by": [x for x in d.get("Required By", "").split() if x != "None"],
            "depends": [x for x in d.get("Depends On", "").split() if x != "None"],
        }
    return res


def pacman_repos():
    """{paket: repo} aus den Sync-Datenbanken"""
    try:
        out = subprocess.run(["pacman", "-Sl"], capture_output=True, text=True, timeout=60).stdout
    except Exception:
        return {}
    m = {}
    for line in out.splitlines():
        p = line.split()
        if len(p) >= 2:
            m.setdefault(p[1], p[0])
    return m


def pacman_desktop_icons():
    """{paket: (icon, anzeigename)} über die .desktop-Dateien, die ein Paket mitbringt"""
    res = {}
    try:
        proc = subprocess.Popen(["pacman", "-Ql"], stdout=subprocess.PIPE, text=True,
                                stderr=subprocess.DEVNULL)
    except Exception:
        return res
    for line in proc.stdout:
        if "/usr/share/applications/" not in line or not line.rstrip().endswith(".desktop"):
            continue
        pkg, _, path = line.rstrip().partition(" ")
        if pkg in res:
            continue
        icon = name = None
        nodisplay = False
        in_main = False
        for l in _read(path).splitlines():
            if l.startswith("["):
                in_main = l.strip() == "[Desktop Entry]"
            elif in_main and l.startswith("Icon=") and icon is None:
                icon = l[5:].strip()
            elif in_main and l.startswith("Name=") and name is None:
                name = l[5:].strip()
            elif in_main and l.strip() == "NoDisplay=true":
                nodisplay = True
        if icon and not nodisplay:
            res[pkg] = (icon, name or pkg)
    proc.wait()
    return res


def flatpak_apps():
    """[{id, name, version, branch, origin, installation, size, date, path, desc}]"""
    if not which("flatpak"):
        return []
    try:
        out = subprocess.run(["flatpak", "list", "--app",
                              "--columns=application,name,version,branch,origin,installation,size,description"],
                             capture_output=True, text=True, timeout=60).stdout
    except Exception:
        return []
    apps = []
    for line in out.splitlines():
        c = line.split("\t")
        if len(c) < 7 or not c[0].strip():
            continue
        inst = c[5].strip()
        base = os.path.expanduser("~/.local/share/flatpak") if inst == "user" else "/var/lib/flatpak"
        path = os.path.join(base, "app", c[0].strip())
        try:
            date = os.path.getmtime(os.path.realpath(os.path.join(path, "current", "active")))
        except Exception:
            date = 0
        apps.append({"id": c[0].strip(), "name": c[1].strip() or c[0].strip(), "version": c[2].strip(),
                     "branch": c[3].strip(), "origin": c[4].strip(), "installation": inst,
                     "size": parse_size(c[6]), "date": date, "path": path,
                     "desc": c[7].strip() if len(c) > 7 else ""})
    return apps


class DateItem(QTableWidgetItem):
    def __init__(self, ts):
        super().__init__(datetime.fromtimestamp(ts).strftime("%d.%m.%Y") if ts else "—")
        self.setData(Qt.UserRole, ts or 0)

    def __lt__(self, other):
        return (self.data(Qt.UserRole) or 0) < (other.data(Qt.UserRole) or 0)


class SoftwareTab(Page):
    CATEGORIES = ["Programme (selbst installiert)", "AUR / Fremd-Pakete", "Flatpak",
                  "Alle Pakete (inkl. Abhängigkeiten)"]
    COLS = [("Name", 260), ("Version", 150), ("Größe", 110), ("Quelle · Ort", 190),
            ("Installiert am", 110), ("Beschreibung", 300)]

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.items = []          # [{key, label, icon, version, size, source, where, date, desc, kind, ...}]
        self.loading = False

        self.count_badge = StatusBadge("off", "Lade …")
        self.lay.addLayout(page_header("Software", self.count_badge))

        pk = Panel("Installierte Software")
        top = QHBoxLayout()
        top.setSpacing(8)
        self.cat_cb = QComboBox()
        self.cat_cb.addItems(self.CATEGORIES)
        self.cat_cb.setMinimumWidth(270)
        self.cat_cb.currentIndexChanged.connect(lambda _: self.refresh_list())
        top.addLayout(Field("Anzeigen", self.cat_cb))
        self.search = LineEdit(placeholder="Name oder Beschreibung …")
        self.search.textChanged.connect(lambda _: self.apply_filter())
        top.addLayout(Field("Suche", self.search), 1)
        refresh_box = QVBoxLayout()
        refresh_box.addStretch(1)
        refresh_box.addWidget(Button("↻", "icon", self.refresh_list, "Liste neu laden"))
        top.addLayout(refresh_box)
        pk.body.addLayout(top)

        selrow = QHBoxLayout()
        selrow.setSpacing(12)
        self.cb_all = QCheckBox("Alle sichtbaren auswählen")
        self.cb_all.clicked.connect(self._check_all)
        selrow.addWidget(self.cb_all)
        self.sel_count = Label("Nichts ausgewählt", "Muted")
        selrow.addWidget(self.sel_count, 1)
        self.b_uninst = Button("Auswahl deinstallieren", "danger", self.uninstall)
        self.b_uninst.setEnabled(False)
        selrow.addWidget(self.b_uninst)
        pk.body.addLayout(selrow)

        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels([c[0].upper() for c in self.COLS])
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setIconSize(QSize(22, 22))
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(32)
        hh = self.table.horizontalHeader()
        hh.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        hh.setStretchLastSection(True)
        for i, (_, w) in enumerate(self.COLS):
            self.table.setColumnWidth(i, w)
        self.table.setSortingEnabled(True)
        self.table.setMinimumHeight(360)
        self.table.itemChanged.connect(self._item_changed)
        self.table.currentCellChanged.connect(lambda *a: self._show_details())
        self.table.cellDoubleClicked.connect(self._toggle_row)
        pk.body.addWidget(self.table)
        pk.body.addWidget(Label("Kästchen anklicken (oder Doppelklick auf die Zeile) wählt aus – "
                                "kein Strg nötig.", "Hint"))

        self.details = Label("", "Muted", wrap=True)
        self.details.setTextFormat(Qt.RichText)
        self.details.setOpenExternalLinks(True)
        self.details.setTextInteractionFlags(Qt.TextBrowserInteraction)
        pk.body.addWidget(self.details)
        self.lay.addWidget(pk, 2)

        act = Panel("Installieren")
        row = QHBoxLayout()
        row.setSpacing(8)
        self.install_edit = LineEdit(placeholder="z. B. firefox htop  ·  bei Flatpak: org.gimp.GIMP", mono=True)
        self.install_edit.returnPressed.connect(self.install)
        row.addLayout(Field("Paketname(n)", self.install_edit), 1)
        self.inst_src = QComboBox()
        self.inst_src.addItems(["Offizielle Paketquellen (pacman)", "AUR (paru)", "Flatpak (Flathub)"])
        self.inst_src.setMinimumWidth(240)
        row.addLayout(Field("Woher", self.inst_src))
        btns = QVBoxLayout()
        btns.addStretch(1)
        btns.addWidget(Button("Installieren", "primary", self.install))
        row.addLayout(btns)
        act.body.addLayout(row)
        self.cb_user_flatpak = QCheckBox("Flatpak: nur für mich installieren (--user, ohne Passwort)")
        act.body.addWidget(self.cb_user_flatpak)
        self.lay.addWidget(act)

        out = Panel("Ausgabe")
        self.log = LogView(140)
        out.body.addWidget(self.log)
        self.lay.addWidget(out, 1)

        self.refresh_list()

    # ---- Laden --------------------------------------------------------------

    def refresh_list(self):
        if self.loading:
            return
        self.loading = True
        cat = self.cat_cb.currentIndex()
        self.count_badge.set("info", "Lade …")
        self.details.setText("")

        def worker():
            items, err = [], None
            try:
                if cat == 2:
                    if not which("flatpak"):
                        err = "flatpak ist nicht installiert"
                    for a in flatpak_apps():
                        items.append({"key": a["id"], "label": a["name"], "icon": a["id"], "version": a["version"],
                                      "size": a["size"], "date": a["date"], "desc": a["desc"], "kind": "flatpak",
                                      "source": f"Flatpak · {'nur ich' if a['installation'] == 'user' else 'System'}",
                                      "where": a["path"], "installation": a["installation"],
                                      "extra": f"{a['origin']} · Zweig {a['branch']}"})
                else:
                    flag = {0: "-Qeq", 1: "-Qmq", 3: "-Qq"}[cat]
                    names = subprocess.run(["pacman", flag], capture_output=True, text=True).stdout.split()
                    infos = pacman_infos(names)
                    repos = pacman_repos()
                    icons = pacman_desktop_icons()
                    for n in names:
                        i = infos.get(n, {})
                        repo = repos.get(n, "AUR / lokal")
                        ic = icons.get(n)
                        items.append({"key": n, "label": n, "app_name": ic[1] if ic else "",
                                      "icon": ic[0] if ic else None, "version": i.get("version", ""),
                                      "size": i.get("size", 0), "date": i.get("date", 0), "desc": i.get("desc", ""),
                                      "kind": "pacman", "source": f"{repo} · /usr", "repo": repo, "where": "/usr",
                                      "url": i.get("url", ""), "reason": i.get("reason", ""),
                                      "required_by": i.get("required_by", []), "depends": i.get("depends", [])})
            except Exception as e:
                err = str(e)
            ui(lambda: self._fill(items, err))
        threading.Thread(target=worker, daemon=True).start()

    def _fill(self, items, err):
        self.loading = False
        self.items = items
        if err and not items:
            self.count_badge.set("danger" if "nicht installiert" not in err else "off", err)
        else:
            total = sum(i["size"] for i in items)
            self.count_badge.set("ok", f"{len(items)} Pakete · {fmt_bytes(total)}")
        self.apply_filter()

    def apply_filter(self):
        q = self.search.text().lower().strip()
        self.table.blockSignals(True)
        self.table.setSortingEnabled(False)
        rows = [i for i in self.items
                if not q or q in f"{i['label']} {i.get('app_name', '')} {i['key']} {i['desc']}".lower()]
        self.table.setRowCount(len(rows))
        mono = QFont(FONTS["mono"], 10)
        for r, it in enumerate(rows):
            label = it["label"] + (f"  ·  {it['app_name']}" if it.get("app_name") and it["app_name"].lower() != it["label"].lower() else "")
            name = QTableWidgetItem(label)
            name.setData(Qt.UserRole, it["key"])
            name.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
            name.setCheckState(Qt.Checked if it.get("checked") else Qt.Unchecked)
            if it.get("icon"):
                ic = themed_icon(it["icon"])
                name.setIcon(ic if not ic.isNull() else letter_icon(it["label"]))
            else:
                name.setIcon(letter_icon(it["label"]))
            cells = [name, QTableWidgetItem(it["version"]), NumItem(fmt_bytes(it["size"]) if it["size"] else "—",
                                                                    it["size"]),
                     QTableWidgetItem(it["source"]), DateItem(it["date"]), QTableWidgetItem(it["desc"])]
            for c, cell in enumerate(cells):
                if c in (1, 2):
                    cell.setFont(mono)
                if c == 2:
                    cell.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if c:
                    cell.setToolTip(it["desc"])
                self.table.setItem(r, c, cell)
        self.table.setSortingEnabled(True)
        self.table.blockSignals(False)
        self._update_sel()

    # ---- Auswahl ------------------------------------------------------------

    def _by_key(self, key):
        return next((i for i in self.items if i["key"] == key), None)

    def _item_changed(self, cell):
        if cell.column() != 0:
            return
        it = self._by_key(cell.data(Qt.UserRole))
        if it is not None:
            it["checked"] = cell.checkState() == Qt.Checked
        self._update_sel()

    def _toggle_row(self, row, col):
        cell = self.table.item(row, 0)
        if cell:
            cell.setCheckState(Qt.Unchecked if cell.checkState() == Qt.Checked else Qt.Checked)

    def _check_all(self, on):
        self.table.blockSignals(True)
        for r in range(self.table.rowCount()):
            cell = self.table.item(r, 0)
            cell.setCheckState(Qt.Checked if on else Qt.Unchecked)
            it = self._by_key(cell.data(Qt.UserRole))
            if it is not None:
                it["checked"] = on
        self.table.blockSignals(False)
        self._update_sel()

    def checked(self):
        return [i for i in self.items if i.get("checked")]

    def _update_sel(self):
        sel = self.checked()
        self.b_uninst.setEnabled(bool(sel))
        if sel:
            self.sel_count.setText(f"{len(sel)} ausgewählt · {fmt_bytes(sum(i['size'] for i in sel))} werden frei")
        else:
            self.sel_count.setText("Nichts ausgewählt")

    def _show_details(self):
        row = self.table.currentRow()
        cell = self.table.item(row, 0) if row >= 0 else None
        it = self._by_key(cell.data(Qt.UserRole)) if cell else None
        if not it:
            self.details.setText("")
            return
        parts = [f"<b>{it['label']}</b> {it['version']} – {it['desc']}"]
        where = it["where"]
        parts.append(f"Ort: <code>{short_path(where)}</code> · Quelle: {it['source'].split(' · ')[0]}"
                     + (f" · {it['extra']}" if it.get("extra") else ""))
        if it.get("reason"):
            parts.append("Installiert " + ("von dir" if it["reason"].startswith("Explicitly") else
                                           "als Abhängigkeit"))
        if it.get("required_by"):
            parts.append("Wird benötigt von: " + ", ".join(it["required_by"][:12])
                         + (" …" if len(it["required_by"]) > 12 else ""))
        if it.get("url"):
            parts.append(f'<a style="color:{COLORS["accent"]}" href="{it["url"]}">{it["url"]}</a>')
        self.details.setText("<br>".join(parts))

    # ---- Aktionen -----------------------------------------------------------

    def install(self):
        pkgs = valid_pkg_tokens(self.install_edit.text())
        if not pkgs:
            show_warning(self, "Ungültige Eingabe",
                         "Bitte gültige(n) Paketnamen eingeben (Leerzeichen-getrennt für mehrere).")
            return
        src = self.inst_src.currentIndex()
        if src == 0:
            if not self.app.priv.ensure(self):
                return
            cmd, needs_sudo, label = ["pacman", "-S", "--"] + pkgs, True, "sudo pacman -S " + quoted(pkgs)
        elif src == 1:
            if not which("paru"):
                show_error(self, "paru fehlt", "paru ist nicht installiert.")
                return
            if not self.app.priv.ensure(self):
                return
            cmd, needs_sudo, label = ["paru", "-S", "--"] + pkgs, False, "paru -S " + quoted(pkgs)
        else:
            if not which("flatpak"):
                show_error(self, "flatpak fehlt", "flatpak ist nicht installiert – im Tab „Flatpak“ einrichten.")
                return
            scope_user = self.cb_user_flatpak.isChecked()
            if not scope_user and not self.app.priv.ensure(self):
                return
            cmd = ["flatpak", "install"] + (["--user"] if scope_user else []) + ["-y", "flathub", "--"] + pkgs
            needs_sudo, label = not scope_user, "flatpak install " + quoted(pkgs)

        self.log.set_text(f"$ {label}\n")

        def done(rc):
            self.log.append_text(f"\n[Exit-Code {rc}]\n")
            self.refresh_list()
            self.app.set_status(f"Installation beendet (Exit {rc}).")

        run_streaming(cmd, self.log, needs_sudo=needs_sudo, clear_first=False, on_done=done, interactive=True)
        self.install_edit.clear()

    def uninstall(self):
        sel = self.checked()
        if not sel:
            return
        names = [i["key"] for i in sel]
        needed = [f"{i['key']} (benötigt von {', '.join(i['required_by'][:3])})" for i in sel
                  if i.get("required_by") and not set(i["required_by"]) <= set(names)]
        text = f"{len(sel)} Paket(e) deinstallieren? ({fmt_bytes(sum(i['size'] for i in sel))})\n\n" \
               + "\n".join(names[:25]) + ("\n…" if len(names) > 25 else "")
        if needed:
            text += "\n\n▲ Werden noch gebraucht – pacman entfernt dann auch die abhängigen Pakete oder bricht ab:\n" \
                    + "\n".join(needed[:8])
        if not ask_confirm(self, "Deinstallieren", text, "Deinstallieren", danger=True):
            return
        steps = []
        pac = [i["key"] for i in sel if i["kind"] == "pacman"]
        fp_sys = [i["key"] for i in sel if i["kind"] == "flatpak" and i.get("installation") != "user"]
        fp_user = [i["key"] for i in sel if i["kind"] == "flatpak" and i.get("installation") == "user"]
        if (pac or fp_sys) and not self.app.priv.ensure(self):
            return
        if pac:
            steps.append({"cmd": ["pacman", "-Rns", "--"] + pac, "needs_sudo": True, "interactive": True,
                          "label": "sudo pacman -Rns " + quoted(pac)})
        if fp_sys:
            steps.append({"cmd": ["flatpak", "uninstall", "--system", "-y", "--"] + fp_sys, "needs_sudo": True,
                          "label": "sudo flatpak uninstall " + quoted(fp_sys)})
        if fp_user:
            steps.append({"cmd": ["flatpak", "uninstall", "--user", "-y", "--"] + fp_user, "needs_sudo": False,
                          "label": "flatpak uninstall --user " + quoted(fp_user)})
        run_sequence(steps, self.log, on_all_done=lambda: (self.refresh_list(),
                                                           self.app.set_status("Deinstallation beendet.")))


# --------------------------------------------------------------------------
# Modul: Flatpak (Apps & Berechtigungen – wie Flatseal)
# --------------------------------------------------------------------------

class Switch(QPushButton):
    """Kippschalter (an/aus) im Stil des Design-Systems."""

    def __init__(self):
        super().__init__()
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)
        self.setFixedSize(42, 24)
        self.setObjectName("Switch")

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        on = self.isChecked()
        track = QColor(COLORS["accent"] if on else COLORS["bg3"])
        if not self.isEnabled():
            track = QColor(COLORS["line"])
        p.setPen(Qt.NoPen if on else QPen(QColor(COLORS["line_strong"]), 1))
        p.setBrush(track)
        p.drawRoundedRect(QRectF(1, 2, 40, 20), 10, 10)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(COLORS["on_accent"] if on else COLORS["muted"]) if self.isEnabled()
                   else QColor(COLORS["line_strong"]))
        x = 23 if on else 5
        p.drawEllipse(QRectF(x, 5, 14, 14))
        if self.hasFocus():
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(COLORS["focus"]), 2))
            p.drawRoundedRect(QRectF(1, 2, 40, 20), 10, 10)
        p.end()


FLATPAK_OVERRIDE_DIR = os.path.expanduser("~/.local/share/flatpak/overrides")
FLATPAK_SYS_OVERRIDE_DIR = "/var/lib/flatpak/overrides"

# (Gruppe, Schlüssel, Name, Titel, Beschreibung, Risiko)  – Risiko: "" | "warn" | "danger"
FLATPAK_PERMS = [
    ("Netzwerk", "shared", "network", "Internet & Netzwerk", "Darf Verbindungen ins Internet und lokale Netz aufbauen.", ""),
    ("Netzwerk", "shared", "ipc", "Gemeinsamer Speicher (IPC)", "Nötig für viele X11-Programme; teilt Speicher mit dem System.", ""),
    ("Anzeige & Ton", "sockets", "wayland", "Wayland-Fenster", "Moderne, abgeschottete Fensterdarstellung.", ""),
    ("Anzeige & Ton", "sockets", "x11", "X11-Fenster", "Ältere Fensterdarstellung – X11-Programme können Tastatur und Bildschirm anderer Programme mitlesen.", "warn"),
    ("Anzeige & Ton", "sockets", "fallback-x11", "X11 nur als Ausweichlösung", "X11 nur benutzen, wenn kein Wayland läuft.", ""),
    ("Anzeige & Ton", "sockets", "pulseaudio", "Ton & Mikrofon", "Wiedergabe und Aufnahme über PulseAudio/PipeWire.", ""),
    ("Anzeige & Ton", "devices", "dri", "Grafikbeschleunigung (GPU)", "Direkter Zugriff auf die Grafikkarte für 3D und Video.", ""),
    ("Geräte", "devices", "all", "Alle Geräte", "Webcam, Controller, USB-Geräte usw. – sehr weitreichend.", "danger"),
    ("Geräte", "devices", "kvm", "Virtualisierung (KVM)", "Für virtuelle Maschinen und Emulatoren.", ""),
    ("Geräte", "devices", "shm", "Gemeinsamer Gerätespeicher (/dev/shm)", "Für manche Spiele und Kommunikations-Apps nötig.", ""),
    ("Geräte", "features", "bluetooth", "Bluetooth", "Direkter Bluetooth-Zugriff.", ""),
    ("Geräte", "sockets", "cups", "Drucken", "Zugriff auf den Druckdienst.", ""),
    ("Geräte", "sockets", "pcsc", "Smartcards", "Chipkartenleser, z. B. für den Personalausweis.", ""),
    ("Geräte", "sockets", "gpg-agent", "GPG-Schlüssel", "Darf deinen GPG-Agenten zum Signieren nutzen.", "warn"),
    ("Geräte", "sockets", "ssh-auth", "SSH-Schlüssel", "Darf deinen SSH-Agenten für Anmeldungen nutzen.", "warn"),
    ("Dateien", "filesystems", "host", "Alle Dateien", "Vollzugriff auf das ganze Dateisystem – hebt die Abschottung weitgehend auf.", "danger"),
    ("Dateien", "filesystems", "host-os", "Systemdateien", "Lesezugriff auf Programme und Bibliotheken des Systems.", "warn"),
    ("Dateien", "filesystems", "host-etc", "Systemeinstellungen (/etc)", "Zugriff auf die Konfiguration des Systems.", "warn"),
    ("Dateien", "filesystems", "home", "Persönlicher Ordner", "Zugriff auf alle deine Dateien im Home-Ordner.", "warn"),
    ("Dateien", "filesystems", "xdg-download", "Downloads", "", ""),
    ("Dateien", "filesystems", "xdg-documents", "Dokumente", "", ""),
    ("Dateien", "filesystems", "xdg-pictures", "Bilder", "", ""),
    ("Dateien", "filesystems", "xdg-music", "Musik", "", ""),
    ("Dateien", "filesystems", "xdg-videos", "Videos", "", ""),
    ("Dateien", "filesystems", "xdg-desktop", "Schreibtisch", "", ""),
    ("System & Entwicklung", "sockets", "session-bus", "Kompletter Sitzungs-Bus", "Darf mit allen Programmen deiner Sitzung sprechen.", "danger"),
    ("System & Entwicklung", "sockets", "system-bus", "Kompletter System-Bus", "Darf mit allen Systemdiensten sprechen.", "danger"),
    ("System & Entwicklung", "features", "devel", "Entwickler-Funktionen", "z. B. Debugger (ptrace) erlauben.", "warn"),
    ("System & Entwicklung", "features", "multiarch", "32-Bit-Programme", "Nötig für manche Spiele (Steam, Wine).", ""),
    ("System & Entwicklung", "features", "per-app-dev-shm", "Eigener /dev/shm", "Trennt gemeinsamen Speicher zwischen Apps.", ""),
]
FS_MODES = [("rw", "Lesen & Schreiben"), ("ro", "Nur lesen"), ("create", "Lesen, Schreiben & Anlegen")]


def read_keyfile(text):
    """{section: {key: value}} – einfacher GKeyFile-Leser"""
    data, sec = {}, None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            sec = line[1:-1]
            data.setdefault(sec, {})
        elif sec is not None and "=" in line:
            k, _, v = line.partition("=")
            data[sec][k.strip()] = v.strip()
    return data


def write_keyfile(data):
    out = []
    for sec, kv in data.items():
        kv = {k: v for k, v in kv.items() if v not in ("", None)}
        if not kv:
            continue
        out.append(f"[{sec}]")
        out += [f"{k}={v}" for k, v in kv.items()]
        out.append("")
    return "\n".join(out)


def _tokens(value):
    return [t for t in (value or "").split(";") if t]


def _fs_parse(tok):
    neg = tok.startswith("!")
    tok = tok[1:] if neg else tok
    name, _, mode = tok.partition(":")
    return name, (mode or "rw"), neg


class FlatpakTab(Page):
    ALL = "__global__"

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.apps = []
        self.cur = None           # App-ID oder ALL
        self.meta = {}            # Standardrechte der App ([Context])
        self.rows = {}            # (kind, name) -> (switch, changed_label, mode_combo)
        self._building = False

        self.badge = StatusBadge("off", "Lade …")
        self.lay.addLayout(page_header("Flatpak", self.badge, Button("↻", "icon", self.refresh, "Neu laden")))

        self.setup = Panel()
        self.setup_text = Label("", "Muted", wrap=True)
        self.setup_text.setTextFormat(Qt.RichText)
        self.setup.body.addWidget(self.setup_text)
        sb = QHBoxLayout()
        self.b_install_fp = Button("Flatpak installieren", "primary", self.install_flatpak)
        self.b_flathub = Button("Flathub hinzufügen", "primary", self.add_flathub)
        self.b_unused = Button("Ungenutzte Laufzeiten entfernen", "ghost", self.remove_unused)
        for b in (self.b_install_fp, self.b_flathub, self.b_unused):
            sb.addWidget(b)
        sb.addStretch(1)
        self.setup.body.addLayout(sb)
        self.lay.addWidget(self.setup)

        main = QHBoxLayout()
        main.setSpacing(16)
        # --- Liste links ---
        left = Panel("Apps")
        left.setFixedWidth(320)
        self.search = LineEdit(placeholder="App suchen …")
        self.search.textChanged.connect(lambda _: self._fill_list())
        left.body.addWidget(self.search)
        self.list = QListWidget()
        self.list.setObjectName("AppList")
        self.list.setIconSize(QSize(32, 32))
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setTextElideMode(Qt.ElideMiddle)
        self.list.setWordWrap(False)
        self.list.setMinimumHeight(560)
        self.list.currentItemChanged.connect(lambda cur, prev: self._select(cur.data(Qt.UserRole) if cur else None))
        left.body.addWidget(self.list, 1)
        main.addWidget(left, 0, Qt.AlignTop)

        # --- Details rechts ---
        right = QVBoxLayout()
        right.setSpacing(16)
        head = Panel()
        hl = QHBoxLayout()
        hl.setSpacing(16)
        self.h_icon = QLabel()
        self.h_icon.setFixedSize(64, 64)
        hl.addWidget(self.h_icon, 0, Qt.AlignTop)
        ht = QVBoxLayout()
        ht.setSpacing(2)
        self.h_name = Label("", "PageTitle")
        self.h_id = Label("", "Value")
        self.h_id.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.h_meta = Label("", "Hint", wrap=True)
        for w in (self.h_name, self.h_id, self.h_meta):
            ht.addWidget(w)
        hl.addLayout(ht, 1)
        head.body.addLayout(hl)
        ab = QHBoxLayout()
        ab.setSpacing(8)
        self.b_run = Button("Starten", "primary", self.run_app)
        self.b_restart = Button("Neu starten", "ghost", self.restart_app, "App beenden und neu starten – "
                                "damit geänderte Rechte gelten")
        self.b_update = Button("Aktualisieren", "ghost", self.update_app)
        self.b_data = Button("Datenordner", "ghost", self.open_data)
        self.b_reset = Button("Rechte zurücksetzen", "ghost", self.reset_overrides)
        self.b_remove = Button("Deinstallieren …", "danger", self.uninstall_app)
        for b in (self.b_run, self.b_restart, self.b_update, self.b_data, self.b_reset):
            ab.addWidget(b)
        ab.addStretch(1)
        ab.addWidget(self.b_remove)
        head.body.addLayout(ab)
        self.h_note = Label("", "Warn", wrap=True)
        self.h_note.hide()
        head.body.addWidget(self.h_note)
        right.addWidget(head)

        # Berechtigungs-Karten
        groups = []
        for g, *_ in FLATPAK_PERMS:
            if g not in groups:
                groups.append(g)
        self.cards = {}
        grid = QGridLayout()
        grid.setSpacing(16)
        for i, g in enumerate(groups):
            card = Panel(g)
            self.cards[g] = card
            for (gg, kind, name, title, desc, risk) in FLATPAK_PERMS:
                if gg == g:
                    self._perm_row(card, kind, name, title, desc, risk)
            if g == "Dateien":
                self._custom_paths_ui(card)
            grid.addWidget(card, i, 0)
        grid.setColumnStretch(0, 1)
        right.addLayout(grid)

        env = Panel("Umgebungsvariablen")
        self.env_table = QTableWidget(0, 2)
        self.env_table.setHorizontalHeaderLabels(["VARIABLE", "WERT"])
        self.env_table.verticalHeader().setVisible(False)
        self.env_table.setShowGrid(False)
        self.env_table.setColumnWidth(0, 220)
        self.env_table.horizontalHeader().setStretchLastSection(True)
        self.env_table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.env_table.setMaximumHeight(160)
        self.env_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.env_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        env.body.addWidget(self.env_table)
        er = QHBoxLayout()
        er.setSpacing(8)
        self.env_key = LineEdit(placeholder="NAME", mono=True)
        self.env_val = LineEdit(placeholder="Wert", mono=True)
        er.addWidget(self.env_key)
        er.addWidget(self.env_val, 1)
        er.addWidget(Button("Setzen", "ghost", self.env_add))
        er.addWidget(Button("Entfernen", "ghost", self.env_del))
        env.body.addLayout(er)
        right.addWidget(env)

        portal = Panel("Freigaben über Portale", [Button("Zurücksetzen", "ghost", self.reset_portals,
                                                          "Alle gespeicherten Freigaben (Kamera, Ort, Bildschirm …) "
                                                          "dieser App vergessen")])
        self.portal_label = Label("", "Muted", wrap=True)
        portal.body.addWidget(self.portal_label)
        right.addWidget(portal)
        self.portal_panel = portal
        self.env_panel = env
        right.addStretch(1)
        main.addLayout(right, 1)
        self.lay.addLayout(main)

        out = Panel("Ausgabe")
        self.log = LogView(120)
        out.body.addWidget(self.log)
        self.lay.addWidget(out)

        self._select(None)
        QTimer.singleShot(300, self.refresh)

    # ---- Aufbau ---------------------------------------------------------------

    def _perm_row(self, card, kind, name, title, desc, risk):
        row = QHBoxLayout()
        row.setSpacing(12)
        sw = Switch()
        sw.clicked.connect(lambda on, k=kind, n=name: self._toggle(k, n, on))
        row.addWidget(sw, 0, Qt.AlignTop)
        txt = QVBoxLayout()
        txt.setSpacing(0)
        t = QHBoxLayout()
        t.setSpacing(8)
        t.addWidget(Label(title, "PanelTitle"))
        if risk:
            rb = StatusBadge(risk, "riskant" if risk == "danger" else "Vorsicht")
            t.addWidget(rb)
        ch = Label("geändert", "Changed")
        ch.setToolTip("Weicht von der Voreinstellung der App ab")
        ch.hide()
        t.addWidget(ch)
        t.addStretch(1)
        txt.addLayout(t)
        if desc:
            txt.addWidget(Label(desc, "Hint", wrap=True))
        row.addLayout(txt, 1)
        mode = None
        if kind == "filesystems":
            mode = QComboBox()
            for m, lab in FS_MODES:
                mode.addItem(lab, m)
            mode.setMinimumHeight(34)
            mode.setFixedWidth(210)
            mode.activated.connect(lambda _, n=name: self._fs_mode(n))
            row.addWidget(mode, 0, Qt.AlignTop)
        card.body.addLayout(row)
        self.rows[(kind, name)] = (sw, ch, mode)

    def _custom_paths_ui(self, card):
        card.body.addWidget(Label("WEITERE ORDNER", "FieldLabel"))
        self.custom_box = QVBoxLayout()
        self.custom_box.setSpacing(6)
        card.body.addLayout(self.custom_box)
        cr = QHBoxLayout()
        cr.setSpacing(8)
        self.custom_path = LineEdit(placeholder="z. B. ~/Spiele oder /mnt/daten", mono=True)
        cr.addWidget(self.custom_path, 1)
        cr.addWidget(Button("…", "icon", self._pick_folder, "Ordner auswählen"))
        cr.addWidget(Button("Freigeben", "ghost", self._add_custom))
        card.body.addLayout(cr)

    # ---- Daten ----------------------------------------------------------------

    def refresh(self):
        def worker():
            installed = which("flatpak")
            apps = flatpak_apps() if installed else []
            remotes = ""
            if installed:
                remotes = subprocess.run(["flatpak", "remotes", "--columns=name"], capture_output=True,
                                         text=True).stdout
            ui(lambda: self._loaded(installed, apps, remotes))
        threading.Thread(target=worker, daemon=True).start()

    def _loaded(self, installed, apps, remotes):
        self.apps = sorted(apps, key=lambda a: a["name"].lower())
        has_flathub = "flathub" in remotes.split()
        self.b_install_fp.setVisible(not installed)
        self.b_flathub.setVisible(installed and not has_flathub)
        self.b_unused.setVisible(installed)
        if not installed:
            self.badge.set("off", "Nicht installiert")
            self.setup_text.setText("Flatpak ist nicht installiert. Flatpak-Apps laufen abgeschottet vom System – "
                                    "hier legst du fest, was jede App darf.")
        elif not has_flathub:
            self.badge.set("warn", "Flathub fehlt")
            self.setup_text.setText("Flatpak ist installiert, aber <b>Flathub</b> (die große App-Quelle) ist noch "
                                    "nicht eingerichtet.")
        else:
            self.badge.set("ok", f"{len(self.apps)} Apps · {fmt_bytes(sum(a['size'] for a in self.apps))}")
            self.setup_text.setText("Rechte ändern gilt für dich (Benutzer-Einstellung, kein Passwort nötig) und "
                                    "wirkt beim <b>nächsten Start</b> der App.")
        self._fill_list()

    def _override_path(self, appid):
        return os.path.join(FLATPAK_OVERRIDE_DIR, "global" if appid == self.ALL else appid)

    def _n_changes(self, appid):
        d = read_keyfile(_read(self._override_path(appid)))
        return sum(len(_tokens(v)) for v in d.get("Context", {}).values()) + len(d.get("Environment", {}))

    def _fill_list(self):
        q = self.search.text().strip().lower()
        cur = self.cur
        self.list.blockSignals(True)
        self.list.clear()
        from PySide6.QtWidgets import QListWidgetItem
        n = self._n_changes(self.ALL)
        it = QListWidgetItem(svg_icon(GEAR_SVG.replace("{c}", COLORS["accent"]), 32),
                             "Alle Apps" + (f"  ·  {n} Regel{'n' if n != 1 else ''}" if n else ""))
        it.setData(Qt.UserRole, self.ALL)
        it.setToolTip("Regeln, die für alle Flatpak-Apps gelten")
        self.list.addItem(it)
        select = 0
        for a in self.apps:
            if q and q not in f"{a['name']} {a['id']}".lower():
                continue
            n = self._n_changes(a["id"])
            ic = themed_icon(a["id"])
            li = QListWidgetItem(ic if not ic.isNull() else letter_icon(a["name"]),
                                 a["name"] + (f"  ✎{n}" if n else ""))
            li.setData(Qt.UserRole, a["id"])
            li.setToolTip(a["id"])
            self.list.addItem(li)
            if a["id"] == cur:
                select = self.list.count() - 1
        self.list.blockSignals(False)
        if self.list.count():
            self.list.setCurrentRow(select)

    def _app(self, appid):
        return next((a for a in self.apps if a["id"] == appid), None)

    def _select(self, appid):
        self.cur = appid
        enabled = appid is not None
        for (sw, ch, mode) in self.rows.values():
            sw.setEnabled(enabled)
            if mode:
                mode.setEnabled(enabled)
        is_app = enabled and appid != self.ALL
        for b in (self.b_run, self.b_restart, self.b_update, self.b_data, self.b_remove):
            b.setVisible(is_app)
        self.b_reset.setVisible(enabled)
        self.portal_panel.setVisible(is_app)
        if not enabled:
            self.h_name.setText("Keine App ausgewählt")
            self.h_id.setText("")
            self.h_meta.setText("")
            self.h_icon.clear()
            return
        if appid == self.ALL:
            self.h_name.setText("Alle Apps")
            self.h_id.setText("Globale Regeln")
            self.h_meta.setText("Was du hier einstellst, gilt für jede Flatpak-App – einzelne Apps können es "
                                "wieder überschreiben.")
            self.h_icon.setPixmap(svg_icon(GEAR_SVG.replace("{c}", COLORS["accent"]), 64).pixmap(64, 64))
            self.meta = {}
            self._apply_state()
            return
        a = self._app(appid)
        ic = themed_icon(appid)
        self.h_icon.setPixmap((ic if not ic.isNull() else letter_icon(a["name"] if a else appid)).pixmap(64, 64))
        self.h_name.setText(a["name"] if a else appid)
        self.h_id.setText(appid)
        if a:
            self.h_meta.setText(f"Version {a['version'] or '—'} · Zweig {a['branch']} · Quelle {a['origin']} · "
                                f"{'nur für dich' if a['installation'] == 'user' else 'systemweit'} installiert · "
                                f"{fmt_bytes(a['size'])}"
                                + (f" · seit {datetime.fromtimestamp(a['date']).strftime('%d.%m.%Y')}" if a["date"] else "")
                                + (f"\n{a['desc']}" if a["desc"] else ""))

        def worker():
            meta = subprocess.run(["flatpak", "info", "--show-metadata", appid], capture_output=True,
                                  text=True).stdout
            perms = subprocess.run(["flatpak", "permission-show", appid], capture_output=True, text=True).stdout
            ui(lambda: self._meta_loaded(appid, meta, perms))
        threading.Thread(target=worker, daemon=True).start()

    def _meta_loaded(self, appid, meta, perms):
        if appid != self.cur:
            return
        self.meta = read_keyfile(meta).get("Context", {})
        lines = [l for l in perms.splitlines()[1:] if l.strip()]
        if lines:
            txt = []
            for l in lines:
                c = l.split("\t") if "\t" in l else l.split()
                if len(c) >= 4:
                    txt.append(f"{c[0]} / {c[1]}: {c[3]}")
            self.portal_label.setText("\n".join(txt) or "Keine gespeicherten Freigaben.")
        else:
            self.portal_label.setText("Keine gespeicherten Freigaben (Kamera, Standort, Bildschirmaufnahme …).")
        self._apply_state()

    # ---- Berechtigungen: Zustand berechnen ------------------------------------

    def _layers(self, include_app=True):
        """Standard der App → System-Overrides → globale Benutzer-Regeln → App-Regeln.
        include_app=False liefert den Zustand ohne die gerade bearbeitete Ebene."""
        is_app = self.cur not in (None, self.ALL)
        layers = [self.meta]
        paths = [os.path.join(FLATPAK_SYS_OVERRIDE_DIR, "global")]
        if is_app:
            paths.append(os.path.join(FLATPAK_SYS_OVERRIDE_DIR, self.cur))
        if is_app or include_app:
            paths.append(self._override_path(self.ALL))
        if is_app and include_app:
            paths.append(self._override_path(self.cur))
        for p in paths:
            layers.append(read_keyfile(_read(p)).get("Context", {}))
        return layers

    def _state(self, kind, name, include_app=True):
        on, mode = False, "rw"
        for layer in self._layers(include_app):
            for tok in _tokens(layer.get(kind)):
                if kind == "filesystems":
                    n, m, neg = _fs_parse(tok)
                    if n == name:
                        on, mode = (not neg), (m if not neg else mode)
                else:
                    if tok == name:
                        on = True
                    elif tok == "!" + name:
                        on = False
        return on, mode

    def _apply_state(self):
        self._building = True
        ov = read_keyfile(_read(self._override_path(self.cur))).get("Context", {}) if self.cur else {}
        for (kind, name), (sw, ch, mode) in self.rows.items():
            on, m = self._state(kind, name)
            sw.setChecked(on)
            sw.update()
            touched = any((_fs_parse(t)[0] == name) if kind == "filesystems" else t.lstrip("!") == name
                          for t in _tokens(ov.get(kind)))
            ch.setVisible(touched)
            if mode:
                mode.setCurrentIndex(max(0, [x for x, _ in FS_MODES].index(m) if m in dict(FS_MODES) else 0))
                mode.setVisible(on)
        self._render_custom(ov)
        self._render_env()
        self._building = False
        n = self._n_changes(self.cur) if self.cur else 0
        self.b_reset.setEnabled(n > 0)

    # ---- Berechtigungen: ändern -----------------------------------------------

    def _edit(self, fn):
        path = self._override_path(self.cur)
        data = read_keyfile(_read(path))
        fn(data)
        text = write_keyfile(data)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if text.strip():
                with open(path, "w") as f:
                    f.write(text)
            elif os.path.exists(path):
                os.remove(path)
        except Exception as e:
            show_error(self, "Fehler", f"Einstellung konnte nicht gespeichert werden: {e}")
        self._apply_state()
        self._fill_list_keep()
        name = "allen Apps" if self.cur == self.ALL else (self._app(self.cur) or {}).get("name", self.cur)
        self.app.set_status(f"Gespeichert – gilt beim nächsten Start von {name}.")
        if self.cur != self.ALL:
            self.h_note.setText("▲ Änderungen wirken beim nächsten Start der App – „Neu starten“ übernimmt sie sofort.")
            self.h_note.show()

    def _fill_list_keep(self):
        row = self.list.currentRow()
        for i in range(self.list.count()):
            it = self.list.item(i)
            aid = it.data(Qt.UserRole)
            n = self._n_changes(aid)
            base = "Alle Apps" if aid == self.ALL else (self._app(aid) or {}).get("name", aid)
            it.setText(base + (f"  ✎{n}" if n else ""))
            it.setToolTip(f"{aid}\n{n} eigene Einstellung(en)" if n else aid)
        self.list.setCurrentRow(row)

    def _toggle(self, kind, name, on):
        if self._building or not self.cur:
            return
        risky = next((r for (_, k, n, _, _, r) in FLATPAK_PERMS if k == kind and n == name), "")
        if on and risky == "danger":
            title = next(t for (_, k, n, t, _, _) in FLATPAK_PERMS if k == kind and n == name)
            if not ask_confirm(self, "Riskante Berechtigung", f"„{title}“ erlauben?\n\nDas schwächt die "
                               "Abschottung der App deutlich. Nur für vertrauenswürdige Apps.", "Erlauben"):
                self._apply_state()
                return
        mode_combo = self.rows[(kind, name)][2]
        mode = mode_combo.currentData() if mode_combo else "rw"
        self._set_perm(kind, name, on, mode)

    def _set_perm(self, kind, name, on, mode="rw"):
        base_on, base_mode = self._state(kind, name, include_app=False)

        def fn(data):
            ctx = data.setdefault("Context", {})
            toks = [t for t in _tokens(ctx.get(kind))
                    if ((_fs_parse(t)[0] != name) if kind == "filesystems" else t.lstrip("!") != name)]
            if on != base_on or (on and kind == "filesystems" and mode != base_mode):
                if kind == "filesystems":
                    toks.append(name + ("" if mode == "rw" else f":{mode}") if on else "!" + name)
                else:
                    toks.append(name if on else "!" + name)
            ctx[kind] = ";".join(toks) + (";" if toks else "")
        self._edit(fn)

    def _fs_mode(self, name):
        sw, ch, mode = self.rows[("filesystems", name)]
        if sw.isChecked():
            self._set_perm("filesystems", name, True, mode.currentData())

    # --- eigene Ordner ---
    def _render_custom(self, ov):
        TaskTab._clear(self.custom_box)
        known = {n for (_, k, n, *_r) in FLATPAK_PERMS if k == "filesystems"}
        entries = {}
        for layer_name, layer in (("app", self.meta), ("ov", ov)):
            for tok in _tokens(layer.get("filesystems")):
                n, m, neg = _fs_parse(tok)
                if n in known:
                    continue
                entries[n] = (not neg, m, layer_name)
        if not entries:
            self.custom_box.addWidget(Label("Keine weiteren Ordner freigegeben.", "Hint"))
        for n, (on, m, src) in sorted(entries.items()):
            r = QHBoxLayout()
            r.setSpacing(8)
            r.addWidget(StatusBadge("ok" if on else "off", "frei" if on else "gesperrt"))
            r.addWidget(Label(n, "Value"), 1)
            r.addWidget(Label(dict(FS_MODES).get(m, m) if on else "", "Hint"))
            if on:
                r.addWidget(Button("Sperren", "ghost", lambda _=False, p=n: self._set_perm("filesystems", p, False)))
            else:
                r.addWidget(Button("Freigeben", "ghost", lambda _=False, p=n: self._set_perm("filesystems", p, True)))
            if src == "ov":
                r.addWidget(Button("↺", "icon", lambda _=False, p=n: self._forget_custom(p), "Eigene Regel entfernen"))
            self.custom_box.addLayout(r)

    def _forget_custom(self, name):
        def fn(data):
            ctx = data.setdefault("Context", {})
            toks = [t for t in _tokens(ctx.get("filesystems")) if _fs_parse(t)[0] != name]
            ctx["filesystems"] = ";".join(toks) + (";" if toks else "")
        self._edit(fn)

    def _pick_folder(self):
        from PySide6.QtWidgets import QFileDialog
        d = QFileDialog.getExistingDirectory(self, "Ordner freigeben", os.path.expanduser("~"))
        if d:
            home = os.path.expanduser("~")
            self.custom_path.setText("~" + d[len(home):] if d.startswith(home) else d)

    def _add_custom(self):
        p = self.custom_path.text().strip()
        if not p or ";" in p or not (p.startswith(("/", "~", "xdg-"))):
            show_warning(self, "Ordner", "Bitte einen Pfad wie ~/Spiele oder /mnt/daten angeben.")
            return
        self.custom_path.clear()
        self._set_perm("filesystems", p.rstrip("/"), True, "rw")

    # --- Umgebungsvariablen ---
    def _render_env(self):
        ov = read_keyfile(_read(self._override_path(self.cur))).get("Environment", {}) if self.cur else {}
        self.env_table.setRowCount(len(ov))
        for r, (k, v) in enumerate(sorted(ov.items())):
            a, b = QTableWidgetItem(k), QTableWidgetItem(v)
            a.setFont(QFont(FONTS["mono"], 10))
            b.setFont(QFont(FONTS["mono"], 10))
            self.env_table.setItem(r, 0, a)
            self.env_table.setItem(r, 1, b)

    def env_add(self):
        k, v = self.env_key.text().strip(), self.env_val.text()
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", k) or "\n" in v:
            show_warning(self, "Variable", "Name nur aus Buchstaben, Ziffern und _ (z. B. GDK_SCALE).")
            return
        self.env_key.clear()
        self.env_val.clear()
        self._edit(lambda d: d.setdefault("Environment", {}).__setitem__(k, v))

    def env_del(self):
        rows = sorted({i.row() for i in self.env_table.selectedIndexes()})
        keys = [self.env_table.item(r, 0).text() for r in rows]
        if keys:
            self._edit(lambda d: [d.setdefault("Environment", {}).pop(k, None) for k in keys])

    # ---- Aktionen ---------------------------------------------------------------

    def reset_overrides(self):
        name = "alle Apps" if self.cur == self.ALL else (self._app(self.cur) or {}).get("name", self.cur)
        if not ask_confirm(self, "Zurücksetzen", f"Alle eigenen Rechte-Einstellungen für {name} entfernen?\n"
                           "Danach gelten wieder die Voreinstellungen der App.", "Zurücksetzen"):
            return
        try:
            os.remove(self._override_path(self.cur))
        except FileNotFoundError:
            pass
        self._apply_state()
        self._fill_list_keep()

    def reset_portals(self):
        if self.cur and ask_confirm(self, "Portal-Freigaben", "Gespeicherte Freigaben dieser App vergessen? "
                                    "Sie fragt beim nächsten Mal erneut.", "Zurücksetzen"):
            run_streaming(["flatpak", "permission-reset", self.cur], self.log,
                          on_done=lambda rc: self._select(self.cur))

    def run_app(self):
        subprocess.Popen(["flatpak", "run", self.cur], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        self.app.set_status(f"{self.cur} wird gestartet …")

    def restart_app(self):
        subprocess.run(["flatpak", "kill", self.cur], capture_output=True)
        QTimer.singleShot(800, self.run_app)
        self.h_note.hide()

    def open_data(self):
        p = os.path.expanduser(f"~/.var/app/{self.cur}")
        if os.path.isdir(p) and which("xdg-open"):
            subprocess.Popen(["xdg-open", p], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            show_info(self, "Datenordner", f"Die App hat noch keinen Datenordner ({short_path(p)}).")

    def _scope(self):
        a = self._app(self.cur)
        return "user" if a and a["installation"] == "user" else "system"

    def update_app(self):
        user = self._scope() == "user"
        if not user and not self.app.priv.ensure(self):
            return
        self.log.set_text(f"$ flatpak update {self.cur}\n")
        run_streaming(["flatpak", "update", "--user" if user else "--system", "-y", self.cur], self.log,
                      needs_sudo=not user, clear_first=False, interactive=True,
                      on_done=lambda rc: (self.log.append_text(f"[Exit-Code {rc}]\n"), self.refresh()))

    def uninstall_app(self):
        a = self._app(self.cur)
        if not a:
            return
        box = QMessageBox(self)
        box.setWindowTitle("Deinstallieren")
        box.setText(f"{a['name']} deinstallieren?")
        box.setInformativeText("Persönliche Daten der App (~/.var/app) können mit gelöscht werden.")
        keep = box.addButton("Deinstallieren, Daten behalten", QMessageBox.AcceptRole)
        wipe = box.addButton("Mit Daten löschen", QMessageBox.DestructiveRole)
        wipe.setProperty("variant", "danger")
        keep.setProperty("variant", "primary")
        cancel = box.addButton("Abbrechen", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() not in (keep, wipe):
            return
        user = a["installation"] == "user"
        if not user and not self.app.priv.ensure(self):
            return
        cmd = ["flatpak", "uninstall", "--user" if user else "--system", "-y"] + \
            (["--delete-data"] if box.clickedButton() is wipe else []) + [a["id"]]
        self.log.set_text("$ " + " ".join(cmd) + "\n")
        run_streaming(cmd, self.log, needs_sudo=not user, clear_first=False,
                      on_done=lambda rc: (self.log.append_text(f"[Exit-Code {rc}]\n"), self.refresh()))

    def install_flatpak(self):
        if not self.app.priv.ensure(self):
            return
        steps = [{"cmd": ["pacman", "-S", "flatpak"], "needs_sudo": True, "interactive": True,
                  "label": "sudo pacman -S flatpak"}]
        run_sequence(steps, self.log, on_all_done=self.refresh)

    def add_flathub(self):
        if not self.app.priv.ensure(self):
            return
        self.log.set_text("$ sudo flatpak remote-add --if-not-exists flathub …\n")
        run_streaming(["flatpak", "remote-add", "--if-not-exists", "flathub",
                       "https://dl.flathub.org/repo/flathub.flatpakrepo"], self.log, needs_sudo=True,
                      clear_first=False, on_done=lambda rc: (self.log.append_text(f"[Exit-Code {rc}]\n"),
                                                             self.refresh()))

    def remove_unused(self):
        if not self.app.priv.ensure(self):
            return
        self.log.set_text("$ sudo flatpak uninstall --unused -y\n")
        run_streaming(["flatpak", "uninstall", "--unused", "-y"], self.log, needs_sudo=True, clear_first=False,
                      on_done=lambda rc: (self.log.append_text(f"[Exit-Code {rc}]\n"), self.refresh()))


# --------------------------------------------------------------------------
# Modul: Fallback-Speicher (Swap)
# --------------------------------------------------------------------------

class SwapTab(Page):
    def __init__(self, app):
        super().__init__()
        self.app = app

        self.badge = StatusBadge("off", "Lade …")
        self.lay.addLayout(page_header("Fallback-Speicher", self.badge))

        grid = QGridLayout()
        grid.setSpacing(16)

        status = Panel("Aktueller Status", [Button("↻", "icon", self.refresh_status, "Status aktualisieren")])
        self.status_box = QVBoxLayout()
        self.status_box.setSpacing(12)
        status.body.addLayout(self.status_box)
        self.swappiness_info = Label("", "Small")
        status.body.addWidget(self.swappiness_info)
        status.body.addStretch(1)
        grid.addWidget(status, 0, 0)

        sf = Panel("Swapfile anlegen / ersetzen")
        r = QHBoxLayout()
        r.setSpacing(8)
        self.path_edit = LineEdit("/swapfile", mono=True)
        self.size_edit = LineEdit("4", mono=True)
        self.size_edit.setFixedWidth(90)
        r.addLayout(Field("Pfad", self.path_edit), 1)
        r.addLayout(Field("Größe (GB)", self.size_edit))
        sf.body.addLayout(r)
        b = QHBoxLayout()
        b.addWidget(Button("Swapfile erstellen && aktivieren", "primary", self.create_swapfile))
        b.addStretch(1)
        sf.body.addLayout(b)
        sf.body.addStretch(1)
        grid.addWidget(sf, 0, 1)

        sw = Panel("Swappiness")
        r = QHBoxLayout()
        r.setSpacing(12)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.setValue(60)
        self.swap_value = Label("60", "Value")
        self.swap_value.setFixedWidth(32)
        self.swap_value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.slider.valueChanged.connect(lambda v: self.swap_value.setText(str(v)))
        r.addWidget(self.slider, 1)
        r.addWidget(self.swap_value)
        sw.body.addLayout(r)
        sw.body.addWidget(Label("Niedrig = RAM bevorzugen, hoch = früher auslagern.", "Small"))
        b = QHBoxLayout()
        b.addWidget(Button("Swappiness setzen (dauerhaft)", "primary", self.set_swappiness))
        b.addStretch(1)
        sw.body.addLayout(b)
        grid.addWidget(sw, 1, 0)

        off = Panel("Swap deaktivieren")
        self.cb_remove = QCheckBox("Datei zusätzlich löschen und Eintrag aus /etc/fstab entfernen")
        off.body.addWidget(self.cb_remove)
        b = QHBoxLayout()
        b.addWidget(Button("Swap deaktivieren", "danger", self.disable_swap))
        b.addStretch(1)
        off.body.addLayout(b)
        off.body.addStretch(1)
        grid.addWidget(off, 1, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        self.lay.addLayout(grid)

        out = Panel("Ausgabe")
        self.log = LogView(160)
        out.body.addWidget(self.log)
        self.lay.addWidget(out, 1)

        self.refresh_status()

    def refresh_status(self):
        def worker():
            devices = []
            try:
                with open("/proc/swaps") as f:
                    for line in f.read().splitlines()[1:]:
                        p = line.split()
                        if len(p) >= 4:
                            devices.append((p[0], int(p[3]) / 1048576, int(p[2]) / 1048576))
            except Exception:
                pass
            try:
                with open("/proc/sys/vm/swappiness") as f:
                    swappiness = f.read().strip()
            except Exception:
                swappiness = "unbekannt"
            ui(lambda: self._show_status(devices, swappiness))
        threading.Thread(target=worker, daemon=True).start()

    def _show_status(self, devices, swappiness):
        while self.status_box.count():
            w = self.status_box.takeAt(0).widget()
            if w:
                w.deleteLater()
        if devices:
            for name, used, total in devices:
                self.status_box.addWidget(UsageBar(name, used, total))
            total = sum(d[2] for d in devices)
            self.badge.set("ok", f"Aktiv · {total:.1f} GiB")
        else:
            self.status_box.addWidget(Label("Kein aktiver Swap gefunden.", "Muted"))
            self.badge.set("off", "Kein Swap aktiv")
        self.swappiness_info.setText(f"Aktuelle Swappiness: {swappiness}")
        if swappiness.isdigit():
            self.slider.setValue(int(swappiness))

    def create_swapfile(self):
        path = self.path_edit.text().strip()
        size = self.size_edit.text().strip()
        if not PATH_RE.match(path) or not re.match(r"^\d+$", size) or int(size) <= 0:
            show_warning(self, "Ungültige Eingabe",
                         "Bitte einen einfachen absoluten Pfad (keine Leerzeichen/Sonderzeichen) "
                         "und eine positive Größe in GB angeben.")
            return
        if not ask_confirm(self, "Bestätigen",
                           f"Swapfile {path} mit {size} GB anlegen bzw. ersetzen und in /etc/fstab eintragen?",
                           "Anlegen"):
            return
        if not self.app.priv.ensure(self):
            return

        p = shlex.quote(path)
        script = (
            f"swapoff {p} 2>/dev/null; "
            f"fallocate -l {size}G {p} || dd if=/dev/zero of={p} bs=1M count=$(({size}*1024)) status=progress; "
            f"chmod 600 {p} && "
            f"mkswap {p} && "
            f"swapon {p} && "
            f"(grep -qF {p} /etc/fstab || echo '{path} none swap defaults 0 0' >> /etc/fstab)"
        )
        self._run_root(script)

    def set_swappiness(self):
        val = int(self.slider.value())
        if not self.app.priv.ensure(self):
            return
        script = f"sysctl vm.swappiness={val} && echo 'vm.swappiness={val}' > /etc/sysctl.d/99-swappiness.conf"
        self._run_root(script)

    def disable_swap(self):
        path = self.path_edit.text().strip()
        if not PATH_RE.match(path):
            show_warning(self, "Ungültige Eingabe", "Bitte einen gültigen Pfad angeben.")
            return
        if not ask_confirm(self, "Bestätigen", f"Swap {path} deaktivieren?", "Deaktivieren", danger=True):
            return
        if not self.app.priv.ensure(self):
            return

        p = shlex.quote(path)
        script = f"swapoff {p}"
        if self.cb_remove.isChecked():
            script += f"; rm -f {p}; grep -vF {p} /etc/fstab > /etc/fstab.tmp; mv /etc/fstab.tmp /etc/fstab"
        self._run_root(script)

    def _run_root(self, script):
        self.log.set_text(f"$ (root) {script}\n\n")

        def done(rc):
            self.log.append_text(f"\n[Exit-Code {rc}]\n")
            self.refresh_status()

        run_streaming(["bash", "-c", script], self.log, needs_sudo=True, clear_first=False, on_done=done)


# --------------------------------------------------------------------------
# Modul: Benutzer
# --------------------------------------------------------------------------

class UsersTab(Page):
    COLS = [("Benutzer", 140), ("UID", 70), ("Home", 180), ("Shell", 150), ("Letzter Login", 240)]

    def __init__(self, app):
        super().__init__()
        self.app = app

        self.lay.addLayout(page_header(
            "Registrierte Benutzer",
            Button("Aktualisieren (mit Login-Zeiten)", "ghost", self.refresh_with_auth)))

        p = Panel()
        self.tree = QTableWidget(0, len(self.COLS))
        self.tree.setHorizontalHeaderLabels([c[0].upper() for c in self.COLS])
        self.tree.verticalHeader().setVisible(False)
        self.tree.setShowGrid(False)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tree.verticalHeader().setDefaultSectionSize(32)
        hh = self.tree.horizontalHeader()
        hh.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        for i, (_, w) in enumerate(self.COLS):
            self.tree.setColumnWidth(i, w)
        hh.setStretchLastSection(True)
        self.tree.setMinimumHeight(320)
        p.body.addWidget(self.tree)
        p.body.addWidget(Label("Login-Zeiten benötigen root-Rechte – Klick auf „Aktualisieren“ fragt "
                               "bei Bedarf einmal nach dem Passwort.", "Small", wrap=True))
        self.lay.addWidget(p, 1)

        self.load_users()

    def load_users(self):
        self.tree.setRowCount(0)
        try:
            with open("/etc/passwd") as f:
                lines = f.readlines()
        except Exception:
            return

        users = []
        for line in lines:
            parts = line.strip().split(":")
            if len(parts) < 7:
                continue
            name, _, uid, _, _, home, shell = parts[:7]
            try:
                uid_i = int(uid)
            except ValueError:
                continue
            if 1000 <= uid_i < 60000 and "nologin" not in shell and "false" not in shell:
                users.append((name, uid, home, shell))

        for name, uid, home, shell in users:
            r = self.tree.rowCount()
            self.tree.insertRow(r)
            for c, v in enumerate((name, uid, home, shell, "—")):
                self.tree.setItem(r, c, QTableWidgetItem(v))

        # Unaufgefordert (ohne Passwort-Dialog!) versuchen - klappt nur,
        # wenn bereits eine sudo-Sitzung aus einer anderen Aktion aktiv ist.
        def cb(rc, out, err):
            if rc != 0:
                return
            self._apply_lastlog(out)
        run_capture_async(["lastlog"], cb, needs_sudo=True)

    def refresh_with_auth(self):
        self.app.priv.ensure(self)
        self.load_users()

    def _apply_lastlog(self, out):
        logins = {}
        for line in out.splitlines()[1:]:
            if not line.strip():
                continue
            uname = line.split(None, 1)[0]
            rest = line[len(uname):].strip()
            logins[uname] = rest if rest else "nie"
        for r in range(self.tree.rowCount()):
            name = self.tree.item(r, 0).text()
            self.tree.setItem(r, 4, QTableWidgetItem(logins.get(name, "unbekannt")))


# --------------------------------------------------------------------------
# Modul: Datenträger (Einhängen, Umbenennen, Formatieren, Prüfen, Auswerfen)
# --------------------------------------------------------------------------

def fmt_bytes(n):
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "—"
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(n) < 1024 or unit == "TiB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


# Mountpoints, die nie über die App ausgehängt/formatiert werden dürfen
SYSTEM_MOUNTS = {"/", "/boot", "/boot/efi", "/efi", "/home", "/usr", "/var", "[SWAP]"}

# Label-Werkzeuge: (Befehl-Builder, max. Länge, muss ausgehängt sein, Paket)
LABEL_TOOLS = {
    "ext2": (lambda d, l, mp: ["e2label", d, l], 16, False, "e2fsprogs"),
    "ext3": (lambda d, l, mp: ["e2label", d, l], 16, False, "e2fsprogs"),
    "ext4": (lambda d, l, mp: ["e2label", d, l], 16, False, "e2fsprogs"),
    "btrfs": (lambda d, l, mp: ["btrfs", "filesystem", "label", mp or d, l], 255, False, "btrfs-progs"),
    "vfat": (lambda d, l, mp: ["fatlabel", d, l.upper()], 11, True, "dosfstools"),
    "exfat": (lambda d, l, mp: ["exfatlabel", d, l], 15, True, "exfatprogs"),
    "ntfs": (lambda d, l, mp: ["ntfslabel", d, l], 32, True, "ntfs-3g"),
    "xfs": (lambda d, l, mp: ["xfs_admin", "-L", l, d], 12, True, "xfsprogs"),
    "swap": (lambda d, l, mp: ["swaplabel", "-L", l, d], 16, False, "util-linux"),
}

# Formatieren: Anzeigename → (Befehl-Builder, max. Label-Länge, Paket)
FORMATS = {
    "ext4 (Linux)": (lambda d, l: ["mkfs.ext4", "-F"] + (["-L", l] if l else []) + [d], 16, "e2fsprogs"),
    "btrfs (Linux)": (lambda d, l: ["mkfs.btrfs", "-f"] + (["-L", l] if l else []) + [d], 255, "btrfs-progs"),
    "xfs (Linux)": (lambda d, l: ["mkfs.xfs", "-f"] + (["-L", l] if l else []) + [d], 12, "xfsprogs"),
    "exFAT (USB-Sticks, alle Systeme)": (lambda d, l: ["mkfs.exfat"] + (["-L", l] if l else []) + [d], 15, "exfatprogs"),
    "FAT32 (maximal kompatibel)": (lambda d, l: ["mkfs.fat", "-F", "32"] + (["-n", l.upper()] if l else []) + [d], 11, "dosfstools"),
    "NTFS (Windows)": (lambda d, l: ["mkfs.ntfs", "-f"] + (["-L", l] if l else []) + [d], 32, "ntfs-3g"),
}

CHECK_TOOLS = {
    "ext2": ["e2fsck", "-f", "-n"], "ext3": ["e2fsck", "-f", "-n"], "ext4": ["e2fsck", "-f", "-n"],
    "btrfs": ["btrfs", "check", "--readonly"], "vfat": ["fsck.fat", "-n"],
    "exfat": ["fsck.exfat", "-n"], "ntfs": ["ntfsfix", "-n"], "xfs": ["xfs_repair", "-n"],
}

LABEL_RE = re.compile(r"^[A-Za-z0-9 _.-]{1,255}$")


def _mounts(node):
    mps = node.get("mountpoints")
    if mps is None:
        mps = [node.get("mountpoint")]
    return [m for m in mps if m]


def _all_mounts(node):
    out = list(_mounts(node))
    for ch in node.get("children") or []:
        out += _all_mounts(ch)
    return out


class RenameDialog(QDialog):
    def __init__(self, parent, dev, current, maxlen):
        super().__init__(parent)
        self.setWindowTitle("Datenträger umbenennen")
        self.setMinimumWidth(440)
        lay = QVBoxLayout(self)
        lay.setSizeConstraint(QLayout.SetMinimumSize)
        spacer = QWidget()
        spacer.setFixedSize(380, 0)
        lay.addWidget(spacer)
        lay.setContentsMargins(32, 28, 32, 24)
        lay.setSpacing(12)
        lay.addWidget(Label("Datenträger umbenennen", "DialogTitle"))
        lay.addWidget(Label(f"{dev} · höchstens {maxlen} Zeichen (Buchstaben, Ziffern, Leerzeichen, _ . -)",
                            "Small", wrap=True))
        self.entry = LineEdit(current or "", mono=True)
        self.entry.setMaxLength(maxlen)
        lay.addLayout(Field("Neue Bezeichnung", self.entry))
        btns = QHBoxLayout()
        btns.addStretch(1)
        btns.addWidget(Button("Abbrechen", "ghost", self.reject))
        ok = Button("Umbenennen", "primary", self.accept)
        ok.setDefault(True)
        btns.addWidget(ok)
        lay.addLayout(btns)
        self.entry.selectAll()
        self.entry.setFocus()


class FormatDialog(QDialog):
    def __init__(self, parent, dev, name, size):
        super().__init__(parent)
        self.setWindowTitle("Datenträger formatieren")
        self.setMinimumWidth(480)
        self.name = name
        lay = QVBoxLayout(self)
        lay.setSizeConstraint(QLayout.SetMinimumSize)
        spacer = QWidget()
        spacer.setFixedSize(380, 0)
        lay.addWidget(spacer)
        lay.setContentsMargins(32, 28, 32, 24)
        lay.setSpacing(12)
        lay.addWidget(Label("Datenträger formatieren", "DialogTitle"))
        lay.addWidget(Label(f"✕  Alle Daten auf {dev} ({size}) werden unwiderruflich gelöscht.", "Danger", wrap=True))
        self.fs = QComboBox()
        self.fs.addItems(list(FORMATS))
        self.fs.setMinimumHeight(38)
        lay.addLayout(Field("Dateisystem", self.fs))
        self.label = LineEdit(placeholder="optional, z. B. USB-Stick", mono=True)
        lay.addLayout(Field("Bezeichnung", self.label))
        self.confirm = LineEdit(placeholder=name, mono=True)
        lay.addLayout(Field("Zur Bestätigung den Gerätenamen eintippen", self.confirm))
        btns = QHBoxLayout()
        btns.addStretch(1)
        btns.addWidget(Button("Abbrechen", "ghost", self.reject))
        self.ok = Button("Formatieren", "danger", self.accept)
        self.ok.setEnabled(False)
        btns.addWidget(self.ok)
        lay.addLayout(btns)
        self.confirm.textChanged.connect(lambda t: self.ok.setEnabled(t.strip() == name))
        self.fs.currentIndexChanged.connect(self._limit)
        self._limit()

    def _limit(self):
        self.label.setMaxLength(FORMATS[self.fs.currentText()][1])


class DisksTab(Page):
    COLS = [("Gerät", 200), ("Bezeichnung", 150), ("Dateisystem", 110), ("Größe", 90),
            ("Belegt", 90), ("Eingehängt unter", 200)]

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.nodes = {}      # path -> lsblk-Knoten
        self.parents = {}    # path -> Eltern-Knoten
        self.current = None

        self.badge = StatusBadge("off", "Lade …")
        self.lay.addLayout(page_header("Datenträger", self.badge,
                                       Button("Diagnose", "ghost", self.diagnose,
                                              "Rohdaten von lsblk und USB in die Ausgabe schreiben"),
                                       Button("↻", "icon", self.refresh, "Neu einlesen")))
        self.warn = Label("", "Danger", wrap=True)
        self.warn.setTextFormat(Qt.RichText)
        self.warn.hide()
        self.lay.addWidget(self.warn)

        lst = Panel("Laufwerke & Partitionen")
        self.tree = QTreeWidget()
        self.tree.setColumnCount(len(self.COLS))
        self.tree.setHeaderLabels([c[0].upper() for c in self.COLS])
        for i, (_, w) in enumerate(self.COLS):
            self.tree.setColumnWidth(i, w)
        self.tree.header().setStretchLastSection(True)
        self.tree.header().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.tree.setMinimumHeight(320)
        self.tree.setRootIsDecorated(True)
        self.tree.currentItemChanged.connect(lambda cur, prev: self._select(cur))
        lst.body.addWidget(self.tree)
        self.lay.addWidget(lst, 1)

        det = Panel("Details")
        self.det_title = Label("Kein Gerät ausgewählt", "PanelTitle")
        det.body.addWidget(self.det_title)
        self.det_grid = QGridLayout()
        self.det_grid.setHorizontalSpacing(24)
        self.det_grid.setVerticalSpacing(10)
        det.body.addLayout(self.det_grid)
        self.det_usage = QVBoxLayout()
        det.body.addLayout(self.det_usage)
        self.det_note = Label("", "Hint", wrap=True)
        det.body.addWidget(self.det_note)

        acts = QHBoxLayout()
        acts.setSpacing(8)
        self.b_mount = Button("Einhängen", "primary", self.mount)
        self.b_umount = Button("Aushängen", "ghost", self.umount)
        self.b_rename = Button("Umbenennen", "ghost", self.rename)
        self.b_check = Button("Prüfen (nur lesen)", "ghost", self.check_fs)
        self.b_eject = Button("Sicher entfernen", "ghost", self.eject)
        self.b_format = Button("Formatieren …", "danger", self.format)
        for b in (self.b_mount, self.b_umount, self.b_rename, self.b_check, self.b_eject):
            acts.addWidget(b)
        acts.addStretch(1)
        acts.addWidget(self.b_format)
        det.body.addLayout(acts)
        self.lay.addWidget(det)

        out = Panel("Ausgabe")
        self.log = LogView(140)
        out.body.addWidget(self.log)
        self.lay.addWidget(out)

        self._select(None)
        self.refresh()

    # ---- Daten ----------------------------------------------------------

    def refresh(self):
        keep = self.current.get("path") if self.current else None
        cols = "NAME,PATH,TYPE,SIZE,FSTYPE,LABEL,MOUNTPOINTS,MODEL,RM,HOTPLUG,FSUSED,FSSIZE,TRAN,RO,UUID"

        def done(rc, out, err):
            if rc != 0 and "MOUNTPOINTS" in cols:
                # ältere util-linux-Versionen kennen MOUNTPOINTS nicht
                run_capture_async(["lsblk", "-J", "-b", "-o", cols.replace("MOUNTPOINTS", "MOUNTPOINT")],
                                  lambda r2, o2, e2: self._fill(r2, o2, e2, keep))
                return
            self._fill(rc, out, err, keep)

        run_capture_async(["lsblk", "-J", "-b", "-o", cols], done)

    def _fill(self, rc, out, err, keep):
        try:
            self._fill_inner(rc, out, err, keep)
        except Exception as e:
            self.badge.set("danger", "Fehler")
            self.log.set_text(f"error: Laufwerksliste konnte nicht aufgebaut werden: {e}\n")
            raise
        self._check_usb()

    def _check_usb(self):
        msgs = []
        usb = usb_storage_devices()
        no_driver = [n for n, ok in usb if not ok]
        if kernel_modules_missing():
            msgs.append(f"✕ Der Kernel wurde aktualisiert, läuft aber noch in der alten Version "
                        f"({os.uname().release}). Bis zum <b>Neustart</b> können neue USB-Sticks nicht "
                        f"erkannt werden, weil die Treiber des laufenden Kernels gelöscht wurden.")
        if no_driver:
            msgs.append("✕ USB-Speicher angeschlossen, aber ohne Treiber: " + ", ".join(no_driver)
                        + (" – bitte neu starten." if kernel_modules_missing()
                           else " – Stick abziehen und neu einstecken, sonst „Diagnose“ klicken."))
        self.warn.setText("<br>".join(msgs))
        self.warn.setVisible(bool(msgs))

    def diagnose(self):
        self.log.set_text("")
        lines = [f"$ uname -r\n{os.uname().release}",
                 f"Module für laufenden Kernel vorhanden: {'nein – Neustart nötig!' if kernel_modules_missing() else 'ja'}"]
        usb = usb_storage_devices()
        lines.append("USB-Massenspeicher (USB-Ebene): " + (", ".join(
            f"{n} [{'Treiber ok' if ok else 'KEIN Treiber'}]" for n, ok in usb) or "keiner gefunden"))
        self.log.append_text("\n".join(lines) + "\n\n")
        run_streaming(["lsblk", "-o", "NAME,TYPE,SIZE,FSTYPE,LABEL,RM,HOTPLUG,TRAN,MOUNTPOINTS"],
                      self.log, clear_first=False)

    def _fill_inner(self, rc, out, err, keep):
        self.tree.clear()
        self.nodes.clear()
        self.parents.clear()
        try:
            devs = json.loads(out)["blockdevices"]
        except Exception:
            self.badge.set("danger", "lsblk-Fehler")
            self.log.set_text(f"error: lsblk fehlgeschlagen (Exit {rc}): {err.strip()}\n"
                              f"Ausgabe: {out[:500]}\n")
            return
        devs = [d for d in devs if d.get("type") not in ("loop", "rom") and not str(d.get("name", "")).startswith("zram")]
        n_disks = 0
        select_item = None

        def add(node, parent_item, parent_node):
            nonlocal select_item
            path = node.get("path") or f"/dev/{node.get('name')}"
            node["path"] = path
            self.nodes[path] = node
            self.parents[path] = parent_node
            name = path
            if node.get("type") == "disk":
                extra = " · ".join(x for x in (node.get("model") or "", (node.get("tran") or "").upper()) if x)
                name = f"{path}  {extra}" if extra else path
            used = node.get("fsused")
            vals = [name, node.get("label") or "", node.get("fstype") or "",
                    fmt_bytes(node.get("size")), fmt_bytes(used) if used else "",
                    ", ".join(_mounts(node))]
            it = QTreeWidgetItem(parent_item, vals) if parent_item else QTreeWidgetItem(self.tree, vals)
            it.setData(0, Qt.UserRole, path)
            for c in (0, 3, 4, 5):
                it.setFont(c, QFont(FONTS["mono"], 10))
            if node.get("type") == "disk":
                f = QFont(FONTS["sans"], 10)
                f.setWeight(QFont.DemiBold)
                it.setFont(0, f)
            if path == keep:
                select_item = it
            for ch in node.get("children") or []:
                add(ch, it, node)
            return it

        for d in devs:
            n_disks += 1
            add(d, None, None)
        self.tree.expandAll()
        self.badge.set("info", f"{n_disks} Laufwerk{'e' if n_disks != 1 else ''}")
        if select_item:
            self.tree.setCurrentItem(select_item)
        else:
            self._select(None)

    # ---- Auswahl --------------------------------------------------------

    def _select(self, item):
        while self.det_grid.count():
            lay = self.det_grid.takeAt(0).layout()
            if lay:
                while lay.count():
                    w = lay.takeAt(0).widget()
                    if w:
                        w.deleteLater()
        while self.det_usage.count():
            w = self.det_usage.takeAt(0).widget()
            if w:
                w.deleteLater()
        node = self.nodes.get(item.data(0, Qt.UserRole)) if item else None
        self.current = node
        for b in (self.b_mount, self.b_umount, self.b_rename, self.b_check, self.b_eject, self.b_format):
            b.setEnabled(False)
        if not node:
            self.det_title.setText("Kein Gerät ausgewählt")
            self.det_note.setText("Wähle oben ein Laufwerk oder eine Partition aus.")
            return

        path, fs, typ = node["path"], node.get("fstype") or "", node.get("type")
        mps = _mounts(node)
        self.det_title.setText(path + (f"  ·  {node['label']}" if node.get("label") else ""))
        info = [("Typ", {"disk": "Laufwerk", "part": "Partition", "crypt": "Verschlüsselt (geöffnet)",
                         "lvm": "LVM-Volume"}.get(typ, typ or "—")),
                ("Dateisystem", fs or "—"), ("Größe", fmt_bytes(node.get("size"))),
                ("Eingehängt unter", ", ".join(mps) or "nicht eingehängt"),
                ("Wechseldatenträger", "ja" if self._removable(node) else "nein"),
                ("UUID", node.get("uuid") or "—")]
        for i, (k, v) in enumerate(info):
            self.det_grid.addLayout(Field(k, Label(v, "Value", wrap=True)), i // 3, i % 3)
        if node.get("fsused") and node.get("fssize"):
            self.det_usage.addWidget(UsageBar(mps[0] if mps else path, int(node["fsused"]) / 1073741824,
                                              int(node["fssize"]) / 1073741824))

        system = any(m in SYSTEM_MOUNTS for m in _all_mounts(node))
        has_children = bool(node.get("children"))
        mountable = bool(fs) and fs not in ("swap", "crypto_LUKS", "LVM2_member", "linux_raid_member")
        notes = []
        self.b_mount.setEnabled(mountable and not mps)
        self.b_umount.setEnabled(bool(mps) and not system and fs != "swap")
        self.b_rename.setEnabled(fs in LABEL_TOOLS and not system)
        self.b_check.setEnabled(fs in CHECK_TOOLS and not mps)
        self.b_eject.setEnabled(self._removable(node) and not system)
        self.b_format.setEnabled(not system and not _all_mounts(node) and not (typ == "disk" and has_children)
                                 and typ in ("part", "disk"))
        if system:
            notes.append("System-Datenträger – Aushängen, Umbenennen und Formatieren sind gesperrt.")
        elif typ == "disk" and has_children:
            notes.append("Zum Formatieren eine Partition auswählen.")
        elif _all_mounts(node):
            notes.append("Zum Formatieren oder Prüfen erst aushängen.")
        if fs == "crypto_LUKS":
            notes.append("Verschlüsselte Partition – bitte mit cryptsetup/Dateimanager entsperren.")
        if not fs and typ == "part":
            notes.append("Kein Dateisystem – mit „Formatieren“ anlegen.")
        self.det_note.setText("  ".join(notes))

    def _removable(self, node):
        disk = node if node.get("type") == "disk" else self.parents.get(node["path"])
        while disk is not None and disk.get("type") != "disk":
            disk = self.parents.get(disk["path"])
        return bool(disk and (disk.get("rm") or disk.get("hotplug")))

    # ---- Aktionen -------------------------------------------------------

    def _root(self, cmd, label=None, then=None):
        if not self.app.priv.ensure(self):
            return
        self.log.set_text(f"$ sudo {label or ' '.join(shlex.quote(c) for c in cmd)}\n")

        def done(rc):
            self.log.append_text(f"[Exit-Code {rc}]\n")
            if then:
                then(rc)
            self.refresh()

        run_streaming(cmd, self.log, needs_sudo=True, clear_first=False, on_done=done)

    def _need_tool(self, tool, pkg):
        if which(tool):
            return True
        show_error(self, "Werkzeug fehlt", f"'{tool}' ist nicht installiert.\n\nsudo pacman -S {pkg}")
        return False

    def mount(self):
        n = self.current
        dev = n["path"]
        if which("udisksctl"):
            self.log.set_text(f"$ udisksctl mount -b {dev}\n")

            def done(rc):
                self.log.append_text(f"[Exit-Code {rc}]\n")
                if rc != 0:
                    self.log.append_text("udisks hat abgelehnt – versuche es mit sudo …\n")
                    self._mount_sudo(n)
                else:
                    self.refresh()
            run_streaming(["udisksctl", "mount", "-b", dev], self.log, clear_first=False, on_done=done)
        else:
            self._mount_sudo(n)

    def _mount_sudo(self, n):
        dev = n["path"]
        name = re.sub(r"[^A-Za-z0-9_.-]", "_", n.get("label") or n.get("name") or os.path.basename(dev))
        target = f"/mnt/{name}"
        opts = []
        if (n.get("fstype") or "") in ("vfat", "exfat", "ntfs"):
            opts = ["-o", f"uid={os.getuid()},gid={os.getgid()}"]
        script = f"mkdir -p {shlex.quote(target)} && mount {' '.join(opts)} {shlex.quote(dev)} {shlex.quote(target)}"
        self._root(["bash", "-c", script], f"mount {dev} {target}")

    def umount(self):
        n = self.current
        dev = n["path"]
        if which("udisksctl"):
            self.log.set_text(f"$ udisksctl unmount -b {dev}\n")

            def done(rc):
                self.log.append_text(f"[Exit-Code {rc}]\n")
                if rc != 0:
                    self.log.append_text("udisks hat abgelehnt – versuche es mit sudo …\n")
                    self._root(["umount", dev])
                else:
                    self.refresh()
            run_streaming(["udisksctl", "unmount", "-b", dev], self.log, clear_first=False, on_done=done)
        else:
            self._root(["umount", dev])

    def rename(self):
        n = self.current
        fs = n.get("fstype")
        builder, maxlen, need_unmounted, pkg = LABEL_TOOLS[fs]
        mps = _mounts(n)
        if need_unmounted and mps:
            show_info(self, "Erst aushängen", f"{fs} kann nur ausgehängt umbenannt werden.")
            return
        dlg = RenameDialog(self, n["path"], n.get("label"), maxlen)
        if dlg.exec() != QDialog.Accepted:
            return
        label = dlg.entry.text().strip()
        if not LABEL_RE.match(label):
            show_warning(self, "Ungültige Bezeichnung",
                         "Erlaubt sind Buchstaben, Ziffern, Leerzeichen und _ . -")
            return
        cmd = builder(n["path"], label, mps[0] if mps else None)
        if self._need_tool(cmd[0], pkg):
            self._root(cmd)

    def check_fs(self):
        n = self.current
        cmd = CHECK_TOOLS[n["fstype"]] + [n["path"]]
        if self._need_tool(cmd[0], "e2fsprogs / btrfs-progs / dosfstools / exfatprogs"):
            self._root(cmd)

    def eject(self):
        n = self.current
        disk = n if n.get("type") == "disk" else self.parents.get(n["path"])
        if not which("udisksctl"):
            show_error(self, "Werkzeug fehlt", "udisksctl ist nicht installiert.\n\nsudo pacman -S udisks2")
            return
        if not ask_confirm(self, "Sicher entfernen",
                           f"{disk['path']} aushängen und ausschalten?", "Sicher entfernen"):
            return
        parts = [c["path"] for c in (disk.get("children") or []) if _mounts(c)]
        if _mounts(disk):
            parts.append(disk["path"])
        steps = [{"cmd": ["udisksctl", "unmount", "-b", p], "needs_sudo": False,
                  "label": f"udisksctl unmount -b {p}"} for p in parts]
        steps.append({"cmd": ["udisksctl", "power-off", "-b", disk["path"]], "needs_sudo": False,
                      "label": f"udisksctl power-off -b {disk['path']}"})
        run_sequence(steps, self.log, on_all_done=lambda: (
            self.app.set_status(f"{disk['path']} kann jetzt entfernt werden."), self.refresh()))

    def format(self):
        n = self.current
        name = os.path.basename(n["path"])
        dlg = FormatDialog(self, n["path"], name, fmt_bytes(n.get("size")))
        if dlg.exec() != QDialog.Accepted or dlg.confirm.text().strip() != name:
            return
        builder, maxlen, pkg = FORMATS[dlg.fs.currentText()]
        label = dlg.label.text().strip()
        if label and not LABEL_RE.match(label):
            show_warning(self, "Ungültige Bezeichnung", "Erlaubt sind Buchstaben, Ziffern, Leerzeichen und _ . -")
            return
        # Sicherheitsnetz: direkt vor dem Formatieren noch einmal prüfen, ob etwas eingehängt ist
        r = subprocess.run(["findmnt", "-rn", "-S", n["path"]], capture_output=True, text=True)
        if r.stdout.strip():
            show_error(self, "Noch eingehängt", f"{n['path']} ist eingehängt. Bitte zuerst aushängen.")
            return
        cmd = builder(n["path"], label)
        if self._need_tool(cmd[0], pkg):
            self._root(cmd, then=lambda rc: self.app.set_status(
                f"Formatieren von {n['path']} {'abgeschlossen' if rc == 0 else 'fehlgeschlagen'}."))


# --------------------------------------------------------------------------
# Modul: Speicher (Belegung je Festplatte, Ordner-Analyse, Aufräumen)
# --------------------------------------------------------------------------

class BarList(QWidget):
    """Liste mit Größenbalken (eine Farbe = Menge). Doppelklick auf Ordner öffnet ihn."""
    opened = Signal(str)
    ROW = 40

    def __init__(self):
        super().__init__()
        self.rows = []      # (name, size, path, is_dir)
        self.total = 0
        self.hover = -1
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.set_rows([], 0)

    def set_rows(self, rows, total):
        self.rows, self.total, self.hover = rows, max(total, 1), -1
        self.setFixedHeight(max(len(rows), 1) * self.ROW)
        self.update()

    def _row_at(self, y):
        i = int(y // self.ROW)
        return i if 0 <= i < len(self.rows) else -1

    def mouseMoveEvent(self, e):
        i = self._row_at(e.position().y())
        if i != self.hover:
            self.hover = i
            if i >= 0:
                name, size, path, is_dir = self.rows[i]
                self.setToolTip(f"{path}\n{fmt_bytes(size)} · {size / self.total * 100:.1f} %"
                                + ("\nDoppelklick zum Öffnen" if is_dir else ""))
                self.setCursor(Qt.PointingHandCursor if is_dir else Qt.ArrowCursor)
            self.update()

    def leaveEvent(self, e):
        self.hover = -1
        self.update()

    def mouseDoubleClickEvent(self, e):
        i = self._row_at(e.position().y())
        if i >= 0 and self.rows[i][3]:
            self.opened.emit(self.rows[i][2])

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        if not self.rows:
            p.setPen(QColor(COLORS["muted"]))
            p.setFont(QFont(FONTS["sans"], 10))
            p.drawText(QRectF(0, 0, w, self.ROW), Qt.AlignLeft | Qt.AlignVCenter,
                       "Noch keine Analyse – Ordner wählen und „Analysieren“ klicken.")
            return
        name_font = QFont(FONTS["mono"], 10)
        val_font = QFont(FONTS["mono"], 10)
        val_font.setWeight(QFont.DemiBold)
        biggest = max(r[1] for r in self.rows) or 1
        for i, (name, size, path, is_dir) in enumerate(self.rows):
            y = i * self.ROW
            if i == self.hover:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(COLORS["bg3"]))
                p.drawRoundedRect(QRectF(-6, y + 1, w + 12, self.ROW - 2), 6, 6)
            p.setFont(name_font)
            p.setPen(QColor(COLORS["ink"]))
            label = (name + "/") if is_dir else name
            p.drawText(QRectF(0, y + 2, w - 170, 20), Qt.AlignLeft | Qt.AlignVCenter,
                       p.fontMetrics().elidedText(label, Qt.ElideMiddle, int(w - 180)))
            p.setFont(val_font)
            p.drawText(QRectF(w - 170, y + 2, 170, 20), Qt.AlignRight | Qt.AlignVCenter,
                       f"{fmt_bytes(size)}   {size / self.total * 100:4.1f} %")
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(COLORS["bg3"]))
            p.drawRoundedRect(QRectF(0, y + 26, w, 6), 3, 3)
            p.setBrush(QColor(COLORS["accent"] if is_dir else COLORS["muted"]))
            bw = max(w * size / biggest, 4) if size else 0
            if bw:
                p.drawRoundedRect(QRectF(0, y + 26, bw, 6), 3, 3)
        p.end()


def _du_size(path, use_sudo):
    cmd = (["sudo", "-n"] if use_sudo else []) + ["du", "-sxB1", path]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        return int(r.stdout.split()[0]) if r.stdout.strip() else 0
    except Exception:
        return 0


_SIZE_UNITS = {"B": 1, "KiB": 1024, "MiB": 1024 ** 2, "GiB": 1024 ** 3, "TiB": 1024 ** 4}


class StorageTab(Page):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.busy = False
        self.path = None
        self.history = []

        self.badge = StatusBadge("off", "Lade …")
        self.lay.addLayout(page_header("Speicherbelegung", self.badge,
                                       Button("↻", "icon", self.refresh_fs, "Neu einlesen")))

        fsp = Panel("Festplatten & Partitionen")
        self.fs_box = QVBoxLayout()
        self.fs_box.setSpacing(12)
        fsp.body.addLayout(self.fs_box)
        self.lay.addWidget(fsp)

        ana = Panel("Was belegt den Platz?")
        top = QHBoxLayout()
        top.setSpacing(8)
        self.mp_cb = QComboBox()
        self.mp_cb.setMinimumWidth(220)
        top.addLayout(Field("Festplatte / Ordner", self.mp_cb))
        top.addStretch(1)
        right = QVBoxLayout()
        right.addStretch(1)
        rb = QHBoxLayout()
        rb.setSpacing(8)
        self.cb_root = QCheckBox("Mit root-Rechten (genauer)")
        self.cb_root.setChecked(True)
        rb.addWidget(self.cb_root)
        self.b_analyze = Button("Analysieren", "primary", lambda: self.analyze(self.mp_cb.currentData()))
        rb.addWidget(self.b_analyze)
        right.addLayout(rb)
        top.addLayout(right)
        ana.body.addLayout(top)

        crumb = QHBoxLayout()
        crumb.setSpacing(8)
        self.b_back = Button("← Zurück", "ghost", self.back)
        self.b_back.setEnabled(False)
        crumb.addWidget(self.b_back)
        self.crumb = Label("", "Value")
        crumb.addWidget(self.crumb, 1)
        self.crumb_total = Label("", "Muted")
        crumb.addWidget(self.crumb_total)
        ana.body.addLayout(crumb)
        self.bars = BarList()
        self.bars.opened.connect(self._open)
        ana.body.addWidget(self.bars)
        ana.body.addWidget(Label("Petrol = Ordner (Doppelklick öffnet ihn), grau = einzelne Dateien. "
                                 "Die größten 25 Einträge werden gezeigt.", "Hint", wrap=True))
        self.lay.addWidget(ana)

        cl = Panel("Typische Platzfresser & Aufräumen",
                   [Button("Größen ermitteln", "ghost", self.scan_cleanup)])
        self.cl_grid = QGridLayout()
        self.cl_grid.setHorizontalSpacing(16)
        self.cl_grid.setVerticalSpacing(10)
        self.cl_grid.setColumnStretch(0, 1)
        cl.body.addLayout(self.cl_grid)
        self.lay.addWidget(cl)

        out = Panel("Ausgabe")
        self.log = LogView(140)
        out.body.addWidget(self.log)
        self.lay.addWidget(out)

        self._build_cleanup_rows()
        self.refresh_fs()

    # ---- Dateisysteme ---------------------------------------------------

    def refresh_fs(self):
        args = ["df", "-B1", "--output=source,fstype,size,used,avail,target",
                "-x", "tmpfs", "-x", "devtmpfs", "-x", "squashfs", "-x", "overlay", "-x", "efivarfs"]

        def done(rc, out, err):
            while self.fs_box.count():
                w = self.fs_box.takeAt(0).widget()
                if w:
                    w.deleteLater()
            prev = self.mp_cb.currentData()
            self.mp_cb.clear()
            seen = set()
            rows = []
            for line in out.splitlines()[1:]:
                p = line.split(None, 5)
                if len(p) < 6 or not p[0].startswith("/dev/") or p[0] in seen:
                    continue
                seen.add(p[0])
                rows.append((p[0], p[1], int(p[2]), int(p[3]), p[5]))
            for src, fstype, size, used, target in rows:
                self.fs_box.addWidget(UsageBar(f"{target}   {src} · {fstype}", used / 1073741824,
                                               size / 1073741824))
                self.mp_cb.addItem(f"{target}  ({fmt_bytes(used)} belegt)", target)
            if not rows:
                self.fs_box.addWidget(Label("Keine Dateisysteme gefunden.", "Muted"))
            self.mp_cb.addItem("Home-Ordner (~)", os.path.expanduser("~"))
            i = self.mp_cb.findData(prev)
            if i >= 0:
                self.mp_cb.setCurrentIndex(i)
            root = next((r for r in rows if r[4] == "/"), rows[0] if rows else None)
            if root:
                pct = root[3] / root[2] * 100 if root[2] else 0
                tone = "danger" if pct >= 90 else "warn" if pct >= 80 else "ok"
                self.badge.set(tone, f"System: {fmt_bytes(root[2] - root[3])} frei ({100 - pct:.0f} %)")

        run_capture_async(args, done)

    # ---- Ordner-Analyse ---------------------------------------------------

    def analyze(self, path, push=False):
        if not path or self.busy:
            return
        use_sudo = self.cb_root.isChecked()
        if use_sudo and not self.app.priv.ensure(self):
            use_sudo = False
        if push and self.path:
            self.history.append(self.path)
        self.path = path
        self.busy = True
        self.b_analyze.setEnabled(False)
        self.b_analyze.setText("Analysiere …")
        self.crumb.setText(path)
        self.crumb_total.setText("wird berechnet …")
        self.b_back.setEnabled(bool(self.history))
        self.app.set_status(f"Analysiere {path} … (kann bei großen Platten etwas dauern)")

        def worker():
            cmd = (["sudo", "-n"] if use_sudo else []) + ["du", "-x", "-B1", "-d1", "-a", path]
            try:
                r = subprocess.run(cmd, capture_output=True, text=True)
                out = r.stdout
            except Exception as e:
                out = ""
                ui(lambda m=f"error: {e}\n": self.log.append_text(m))
            total, rows = 0, []
            norm = os.path.normpath(path)
            for line in out.splitlines():
                if "\t" not in line:
                    continue
                size_s, p = line.split("\t", 1)
                try:
                    size = int(size_s)
                except ValueError:
                    continue
                if os.path.normpath(p) == norm:
                    total = size
                else:
                    rows.append((os.path.basename(p) or p, size, p, os.path.isdir(p) and not os.path.islink(p)))
            rows.sort(key=lambda r: -r[1])
            if len(rows) > 25:
                rest = sum(r[1] for r in rows[25:])
                rows = rows[:25] + [(f"… {len(rows) - 25} weitere", rest, path, False)]
            ui(lambda: self._show(path, rows, total))

        threading.Thread(target=worker, daemon=True).start()

    def _show(self, path, rows, total):
        self.busy = False
        self.b_analyze.setEnabled(True)
        self.b_analyze.setText("Analysieren")
        self.bars.set_rows(rows, total)
        self.crumb_total.setText(f"gesamt {fmt_bytes(total)}")
        self.app.set_status(f"Analyse von {path} fertig.")

    def _open(self, path):
        self.analyze(path, push=True)

    def back(self):
        if self.history:
            prev = self.history.pop()
            self.path = None
            self.analyze(prev)

    # ---- Aufräumen --------------------------------------------------------

    def _build_cleanup_rows(self):
        home = os.path.expanduser("~")
        self.cleanup = [
            {"key": "pkgcache", "name": "Pacman-Paketcache", "path": "/var/cache/pacman/pkg",
             "action": "Alte Versionen löschen", "hint": "behält die 2 neuesten Versionen je Paket"},
            {"key": "orphans", "name": "Verwaiste Pakete", "path": "pacman -Qdtq",
             "action": "Entfernen", "hint": "Abhängigkeiten, die nichts mehr braucht"},
            {"key": "journal", "name": "System-Logs (Journal)", "path": "/var/log/journal",
             "action": "Auf 200 MB kürzen", "hint": ""},
            {"key": "trash", "name": "Papierkorb", "path": os.path.join(home, ".local/share/Trash"),
             "action": "Leeren", "hint": ""},
            {"key": "flatpak", "name": "Flatpak (System + Benutzer)", "path": "/var/lib/flatpak",
             "action": "Unbenutzte entfernen", "hint": "entfernt ungenutzte Laufzeiten"},
            {"key": "usercache", "name": "Benutzer-Cache (~/.cache)", "path": os.path.join(home, ".cache"),
             "action": None, "hint": "nur Anzeige – Programme legen hier Zwischendaten ab"},
            {"key": "paru", "name": "AUR-Build-Cache (paru)", "path": os.path.join(home, ".cache/paru"),
             "action": None, "hint": "nur Anzeige"},
            {"key": "docker", "name": "Docker", "path": "/var/lib/docker", "action": None, "hint": "nur Anzeige"},
        ]
        for i, c in enumerate(self.cleanup):
            txt = QVBoxLayout()
            txt.setSpacing(0)
            txt.addWidget(Label(c["name"]))
            txt.addWidget(Label(short_path(c["path"]) + (f" · {c['hint']}" if c["hint"] else ""), "Hint"))
            self.cl_grid.addLayout(txt, i, 0)
            c["size_lbl"] = Label("—", "Value")
            c["size_lbl"].setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            c["size_lbl"].setMinimumWidth(110)
            self.cl_grid.addWidget(c["size_lbl"], i, 1)
            if c["action"]:
                b = Button(c["action"], "ghost", lambda _=False, k=c["key"]: self.clean(k))
                c["btn"] = b
                self.cl_grid.addWidget(b, i, 2)

    def scan_cleanup(self):
        use_sudo = self.app.priv.is_authenticated_nonblocking()
        for c in self.cleanup:
            c["size_lbl"].setText("…")

        def worker():
            res = {}
            for c in self.cleanup:
                k = c["key"]
                if k == "orphans":
                    r = subprocess.run(["pacman", "-Qdtq"], capture_output=True, text=True) \
                        if which("pacman") else None
                    pkgs = r.stdout.split() if r and r.returncode == 0 else []
                    size = 0
                    if pkgs:
                        qi = subprocess.run(["pacman", "-Qi"] + pkgs, capture_output=True, text=True,
                                            env={**os.environ, "LC_ALL": "C"}).stdout
                        for m in re.finditer(r"^Installed Size\s*:\s*([\d.,]+)\s*(\S+)", qi, re.M):
                            size += float(m.group(1).replace(",", ".")) * _SIZE_UNITS.get(m.group(2), 1)
                    res[k] = (size, f"{len(pkgs)} Pakete · {fmt_bytes(size)}" if pkgs else "keine")
                elif k == "flatpak":
                    size = sum(_du_size(p, use_sudo) for p in ("/var/lib/flatpak",
                               os.path.expanduser("~/.local/share/flatpak")) if os.path.exists(p))
                    res[k] = (size, fmt_bytes(size) if size else "—")
                else:
                    p = c["path"]
                    size = _du_size(p, use_sudo) if os.path.exists(p) else 0
                    res[k] = (size, fmt_bytes(size) if os.path.exists(p) else "nicht vorhanden")
            ui(lambda: self._show_cleanup(res))

        threading.Thread(target=worker, daemon=True).start()

    def _show_cleanup(self, res):
        for c in self.cleanup:
            size, txt = res.get(c["key"], (0, "—"))
            c["size_lbl"].setText(txt)

    def clean(self, key):
        home = os.path.expanduser("~")
        if key == "pkgcache":
            if which("paccache"):
                cmd, label, sudo = ["bash", "-c", "paccache -rk2 && paccache -ruk0"], "paccache -rk2 && paccache -ruk0", True
            else:
                cmd, label, sudo = ["pacman", "-Sc", "--noconfirm"], "pacman -Sc", True
            text = "Alte Paketversionen aus dem Pacman-Cache löschen?"
        elif key == "orphans":
            r = subprocess.run(["pacman", "-Qdtq"], capture_output=True, text=True)
            pkgs = r.stdout.split()
            if not pkgs:
                show_info(self, "Nichts zu tun", "Es gibt keine verwaisten Pakete.")
                return
            cmd, label, sudo = ["pacman", "-Rns", "--noconfirm", "--"] + pkgs, "pacman -Rns " + quoted(pkgs), True
            text = "Diese verwaisten Pakete entfernen?\n\n" + "\n".join(pkgs[:30]) + ("\n…" if len(pkgs) > 30 else "")
        elif key == "journal":
            cmd, label, sudo = ["journalctl", "--vacuum-size=200M"], "journalctl --vacuum-size=200M", True
            text = "System-Logs auf 200 MB kürzen?"
        elif key == "trash":
            t = shlex.quote(os.path.join(home, ".local/share/Trash"))
            cmd = ["bash", "-c", f"find {t}/files {t}/info -mindepth 1 -delete 2>/dev/null; true"]
            label, sudo = "Papierkorb leeren", False
            text = "Papierkorb endgültig leeren?"
        elif key == "flatpak":
            cmd, label, sudo = ["flatpak", "uninstall", "--unused", "-y"], "flatpak uninstall --unused -y", False
            text = "Ungenutzte Flatpak-Laufzeiten entfernen?"
        else:
            return
        if not ask_confirm(self, "Aufräumen", text, "Ausführen", danger=key in ("trash", "orphans")):
            return
        if sudo and not self.app.priv.ensure(self):
            return
        self.log.set_text(f"$ {'sudo ' if sudo else ''}{label}\n")

        def done(rc):
            self.log.append_text(f"[Exit-Code {rc}]\n")
            self.refresh_fs()
            self.scan_cleanup()

        run_streaming(cmd, self.log, needs_sudo=sudo, clear_first=False, on_done=done)


# --------------------------------------------------------------------------
# Modul: Taskmanager (Leistung + Prozesse, liest direkt aus /proc)
# --------------------------------------------------------------------------

PAGE_SIZE = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 4096
CLK_TCK = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100
N_CPU = os.cpu_count() or 1


def _read(path, default=""):
    try:
        with open(path) as f:
            return f.read()
    except Exception:
        return default


def cpu_times():
    """(gesamt, leerlauf) in Jiffies aus /proc/stat."""
    parts = _read("/proc/stat").split("\n", 1)[0].split()[1:]
    vals = [int(x) for x in parts[:8]] if parts else [0] * 8
    idle = vals[3] + (vals[4] if len(vals) > 4 else 0)
    return sum(vals), idle


def meminfo():
    info = {}
    for line in _read("/proc/meminfo").splitlines():
        k, _, v = line.partition(":")
        try:
            info[k] = int(v.split()[0]) * 1024
        except (ValueError, IndexError):
            pass
    return info


_USERS = {}


def _user(uid):
    if uid not in _USERS:
        try:
            _USERS[uid] = pwd.getpwuid(uid).pw_name
        except KeyError:
            _USERS[uid] = str(uid)
    return _USERS[uid]


def read_processes():
    """{pid: dict(name, user, uid, state, ticks, rss, cmd, nice, threads)}"""
    procs = {}
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        pid = int(d)
        stat = _read(f"/proc/{pid}/stat")
        if not stat:
            continue
        try:
            rpar = stat.rindex(")")
            name = stat[stat.index("(") + 1:rpar]
            f = stat[rpar + 2:].split()
            state, ticks = f[0], int(f[11]) + int(f[12])
            nice, threads = int(f[16]), int(f[17])
            rss = int(f[21]) * PAGE_SIZE
        except (ValueError, IndexError):
            continue
        try:
            uid = os.stat(f"/proc/{pid}").st_uid
        except OSError:
            continue
        cmd = _read(f"/proc/{pid}/cmdline").replace("\0", " ").strip()
        procs[pid] = {"name": name, "uid": uid, "user": _user(uid), "state": state, "ticks": ticks,
                      "rss": rss, "cmd": cmd or f"[{name}]", "nice": nice, "threads": threads}
    return procs


STATES = {"R": "läuft", "S": "schläft", "D": "wartet (E/A)", "Z": "Zombie", "T": "angehalten",
          "t": "angehalten", "I": "Leerlauf", "X": "beendet"}


class NumItem(QTableWidgetItem):
    """Tabellenzelle, die nach Zahlwert statt Text sortiert."""

    def __init__(self, text, value):
        super().__init__(text)
        self.setData(Qt.UserRole, value)

    def __lt__(self, other):
        a, b = self.data(Qt.UserRole), other.data(Qt.UserRole)
        try:
            return a < b
        except TypeError:
            return str(a) < str(b)


class StatTile(QFrame):
    """Kennzahl-Kachel: Label, große Zahl, Zusatzzeile, Verlauf (eine Serie → keine Legende)."""
    HISTORY = 60

    def __init__(self, title, color=None, compact=False, maxval=100):
        super().__init__()
        self.setObjectName("Panel")
        self.color = QColor(color or COLORS["accent"])
        self.values = []
        self.maxval = maxval   # None = automatisch nach größtem Wert skalieren
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(2)
        lay.addWidget(Label(title.upper(), "FieldLabel"))
        self.big = Label("—", "BigValue")
        lay.addWidget(self.big)
        self.sub = Label("", "Hint")
        lay.addWidget(self.sub)
        self.spark = _Spark(self)
        if compact:
            self.spark.setFixedHeight(26)
            self.big.setObjectName("MidValue")
        lay.addWidget(self.spark)

    def set(self, big, sub, value=None):
        self.big.setText(big)
        self.sub.setText(sub)
        if value is not None:
            self.values = (self.values + [max(0.0, float(value))])[-self.HISTORY:]
            self.spark.setToolTip(f"Verlauf der letzten {len(self.values) * 2} s · aktuell {big}")
            self.spark.update()

    def scaled(self):
        top = self.maxval or max(max(self.values, default=0), 1)
        return [min(100.0, v / top * 100) for v in self.values]


class _Spark(QWidget):
    def __init__(self, tile):
        super().__init__()
        self.tile = tile
        self.setFixedHeight(40)

    def paintEvent(self, e):
        vals = self.tile.scaled()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(QColor(COLORS["line"]))
        p.drawLine(0, h - 1, w, h - 1)
        if len(vals) < 2:
            p.end()
            return
        step = w / (StatTile.HISTORY - 1)
        x0 = w - step * (len(vals) - 1)
        pts = [(x0 + i * step, h - 2 - (v / 100) * (h - 6)) for i, v in enumerate(vals)]
        area = QPainterPath()
        area.moveTo(pts[0][0], h - 1)
        for x, y in pts:
            area.lineTo(x, y)
        area.lineTo(pts[-1][0], h - 1)
        fill = QColor(self.tile.color)
        fill.setAlpha(40)
        p.fillPath(area, fill)
        line = QPainterPath()
        line.moveTo(*pts[0])
        for x, y in pts[1:]:
            line.lineTo(x, y)
        pen = QPen(self.tile.color, 2)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.drawPath(line)
        p.setBrush(self.tile.color)
        p.setPen(Qt.NoPen)
        p.drawEllipse(QRectF(pts[-1][0] - 3, pts[-1][1] - 3, 6, 6))
        p.end()


# --------------------------------------------------------------------------
# Systeminformationen (Hardware, Akku, Netzwerk, Temperaturen) – ohne root
# --------------------------------------------------------------------------

def _first_line(path):
    return _read(path).strip().split("\n", 1)[0].strip()


def cpu_model():
    for line in _read("/proc/cpuinfo").splitlines():
        if line.lower().startswith(("model name", "hardware", "processor\t: arm")):
            name = line.split(":", 1)[1].strip()
            return re.sub(r"\s+", " ", name.replace("(R)", "").replace("(TM)", "").replace(" CPU", ""))
    return platform_machine()


def platform_machine():
    try:
        return os.uname().machine
    except Exception:
        return "unbekannt"


def cpu_mhz():
    vals = []
    base = "/sys/devices/system/cpu"
    try:
        for d in os.listdir(base):
            if re.match(r"cpu\d+$", d):
                v = _first_line(f"{base}/{d}/cpufreq/scaling_cur_freq")
                if v.isdigit():
                    vals.append(int(v) / 1000)
    except Exception:
        pass
    if not vals:
        vals = [float(l.split(":")[1]) for l in _read("/proc/cpuinfo").splitlines() if l.startswith("cpu MHz")]
    return (sum(vals) / len(vals), max(vals)) if vals else (None, None)


def cpu_threads_cores():
    threads = os.cpu_count() or 1
    cores = set()
    phys = None
    for line in _read("/proc/cpuinfo").splitlines():
        if line.startswith("physical id"):
            phys = line.split(":")[1].strip()
        elif line.startswith("core id"):
            cores.add((phys, line.split(":")[1].strip()))
    return (len(cores) or threads), threads


def temperatures():
    """{'cpu': °C, 'gpu': °C, ...} aus /sys/class/hwmon"""
    out = {}
    base = "/sys/class/hwmon"
    try:
        mons = os.listdir(base)
    except Exception:
        return out
    for m in mons:
        name = _first_line(f"{base}/{m}/name")
        try:
            files = sorted(f for f in os.listdir(f"{base}/{m}") if re.match(r"temp\d+_input$", f))
        except Exception:
            continue
        for f in files:
            label = _first_line(f"{base}/{m}/{f.replace('_input', '_label')}")
            try:
                t = int(_first_line(f"{base}/{m}/{f}")) / 1000
            except ValueError:
                continue
            if name in ("k10temp", "zenpower") and (label in ("Tctl", "Tdie", "") and "cpu" not in out):
                out["cpu"] = t
            elif name == "coretemp" and label.startswith("Package") and "cpu" not in out:
                out["cpu"] = t
            elif name in ("amdgpu", "nouveau", "radeon") and "gpu" not in out:
                out["gpu"] = t
            elif name == "nvme" and "nvme" not in out:
                out["nvme"] = t
            elif name in ("acpitz", "cpu_thermal") and "cpu" not in out:
                out.setdefault("_acpi", t)
    if "cpu" not in out and "_acpi" in out:
        out["cpu"] = out["_acpi"]
    out.pop("_acpi", None)
    return out


_PCI_IDS = None


def _pci_name(vendor, device):
    global _PCI_IDS
    if _PCI_IDS is None:
        _PCI_IDS = {}
        for path in ("/usr/share/hwdata/pci.ids", "/usr/share/misc/pci.ids"):
            if os.path.exists(path):
                cur = None
                with open(path, errors="ignore") as f:
                    for line in f:
                        if line.startswith("#") or not line.strip():
                            continue
                        if line.startswith("C "):
                            break
                        if not line.startswith("\t"):
                            cur = line[:4].lower()
                            _PCI_IDS[cur] = line[6:].strip()
                        elif not line.startswith("\t\t") and cur:
                            _PCI_IDS[f"{cur}:{line[1:5].lower()}"] = line[7:].strip()
                break
    v = _PCI_IDS.get(vendor, vendor)
    d = _PCI_IDS.get(f"{vendor}:{device}", device)
    v = v.replace("Advanced Micro Devices, Inc. [AMD/ATI]", "AMD").replace("NVIDIA Corporation", "NVIDIA") \
         .replace("Intel Corporation", "Intel")
    return f"{v} {d}"


def gpus():
    """[{name, card, busy%(oder None), vram_used, vram_total}]"""
    res = []
    seen = set()
    base = "/sys/class/drm"
    try:
        cards = sorted(c for c in os.listdir(base) if re.match(r"card\d+$", c))
    except Exception:
        cards = []
    for c in cards:
        dev = f"{base}/{c}/device"
        vendor = _first_line(f"{dev}/vendor").replace("0x", "").lower()
        device = _first_line(f"{dev}/device").replace("0x", "").lower()
        if not vendor or (vendor, device) in seen:
            continue
        seen.add((vendor, device))
        g = {"name": _pci_name(vendor, device), "card": c, "busy": None, "vram_used": None, "vram_total": None}
        busy = _first_line(f"{dev}/gpu_busy_percent")
        if busy.isdigit():
            g["busy"] = int(busy)
        vu, vt = _first_line(f"{dev}/mem_info_vram_used"), _first_line(f"{dev}/mem_info_vram_total")
        if vu.isdigit() and vt.isdigit():
            g["vram_used"], g["vram_total"] = int(vu), int(vt)
        res.append(g)
    if which("nvidia-smi"):
        try:
            r = subprocess.run(["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total",
                                "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=3)
            for i, line in enumerate(r.stdout.strip().splitlines()):
                name, util, mu, mt = [x.strip() for x in line.split(",")]
                nv = [g for g in res if g["name"].startswith("NVIDIA")]
                g = nv[i] if i < len(nv) else {"card": f"nvidia{i}"}
                g.update({"name": "NVIDIA " + name.replace("NVIDIA ", ""), "busy": int(util),
                          "vram_used": int(mu) * 1048576, "vram_total": int(mt) * 1048576})
                if g not in res:
                    res.append(g)
        except Exception:
            pass
    return res


def batteries():
    """[{name, capacity%, status, watts, hours_left, health%, model}] + ac_online"""
    res, ac = [], None
    base = "/sys/class/power_supply"
    try:
        items = os.listdir(base)
    except Exception:
        return res, ac
    for it in items:
        p = f"{base}/{it}"
        typ = _first_line(f"{p}/type")
        if typ == "Mains":
            ac = _first_line(f"{p}/online") == "1"
        if typ != "Battery" or _first_line(f"{p}/scope") == "Device":
            continue

        def num(n):
            v = _first_line(f"{p}/{n}")
            return int(v) if v.lstrip("-").isdigit() else None
        cap = num("capacity")
        status = _first_line(f"{p}/status")
        power = num("power_now")
        if power is None and num("current_now") is not None and num("voltage_now"):
            power = num("current_now") * num("voltage_now") / 1e6
        e_now = num("energy_now") or (num("charge_now") and num("voltage_now") and num("charge_now") * num("voltage_now") / 1e6)
        e_full = num("energy_full") or (num("charge_full") and num("voltage_now") and num("charge_full") * num("voltage_now") / 1e6)
        e_design = num("energy_full_design") or (num("charge_full_design") and num("voltage_now")
                                                 and num("charge_full_design") * num("voltage_now") / 1e6)
        watts = abs(power) / 1e6 if power else None
        hours = None
        if watts and watts > 0.1 and e_now:
            if status == "Discharging":
                hours = (e_now / 1e6) / watts
            elif status == "Charging" and e_full:
                hours = max(0, (e_full - e_now) / 1e6) / watts
        res.append({"name": it, "capacity": cap, "status": status, "watts": watts, "hours": hours,
                    "health": (e_full / e_design * 100) if (e_full and e_design) else None,
                    "model": " ".join(x for x in (_first_line(f"{p}/manufacturer"),
                                                  _first_line(f"{p}/model_name")) if x)})
    return res, ac


BAT_STATUS = {"Charging": "lädt", "Discharging": "Akkubetrieb", "Full": "voll", "Not charging": "lädt nicht",
              "Unknown": "unbekannt"}


def net_counters():
    """{iface: (rx_bytes, tx_bytes)}"""
    out = {}
    for line in _read("/proc/net/dev").splitlines()[2:]:
        name, _, rest = line.partition(":")
        f = rest.split()
        if len(f) >= 9:
            out[name.strip()] = (int(f[0]), int(f[8]))
    return out


def disk_counters():
    """(read_bytes, write_bytes) aller physischen Laufwerke"""
    rd = wr = 0
    for line in _read("/proc/diskstats").splitlines():
        f = line.split()
        if len(f) > 9 and re.match(r"^(sd[a-z]+|nvme\d+n\d+|vd[a-z]+|mmcblk\d+|hd[a-z]+)$", f[2]):
            rd += int(f[5]) * 512
            wr += int(f[9]) * 512
    return rd, wr


def iface_kind(name):
    if name == "lo":
        return "Loopback"
    if os.path.isdir(f"/sys/class/net/{name}/wireless") or name.startswith(("wl", "wlan")):
        return "WLAN"
    if name.startswith(("wg", "tun", "tap", "ppp", "proton", "mullvad", "tailscale", "nordlynx", "vpn")):
        return "VPN"
    if name.startswith(("docker", "br-", "virbr", "veth", "vnet")):
        return "Virtuell"
    if name.startswith(("en", "eth")):
        return "LAN"
    return "Netzwerk"


def net_interfaces():
    """[{name, kind, state, ipv4[], ipv6[], mac}], gateway, dns[]"""
    ifaces, gw, dns = [], None, []
    try:
        data = json.loads(subprocess.run(["ip", "-j", "addr"], capture_output=True, text=True, timeout=5).stdout)
    except Exception:
        data = []
    for it in data:
        name = it.get("ifname", "")
        if name == "lo":
            continue
        v4 = [f"{a['local']}/{a.get('prefixlen', '')}" for a in it.get("addr_info", []) if a.get("family") == "inet"]
        v6 = [a["local"] for a in it.get("addr_info", [])
              if a.get("family") == "inet6" and a.get("scope") == "global"]
        ifaces.append({"name": name, "kind": iface_kind(name), "state": it.get("operstate", "?"),
                       "ipv4": v4, "ipv6": v6, "mac": it.get("address", "")})
    try:
        routes = json.loads(subprocess.run(["ip", "-j", "route", "show", "default"], capture_output=True,
                                           text=True, timeout=5).stdout)
        if routes:
            gw = f"{routes[0].get('gateway', '—')} über {routes[0].get('dev', '?')}"
    except Exception:
        pass
    if which("resolvectl"):
        r = subprocess.run(["resolvectl", "dns"], capture_output=True, text=True, timeout=5)
        for line in r.stdout.splitlines():
            parts = line.split(":", 1)
            if len(parts) == 2:
                dns += [x for x in parts[1].split() if x not in dns]
    if not dns:
        dns = [l.split()[1] for l in _read("/etc/resolv.conf").splitlines() if l.startswith("nameserver")]
    return ifaces, gw, dns


def internet_route_dev():
    """Über welche Schnittstelle geht der Internetverkehr gerade? (inkl. Policy-Routing von VPNs)"""
    try:
        data = json.loads(subprocess.run(["ip", "-j", "route", "get", "1.1.1.1"], capture_output=True,
                                         text=True, timeout=5).stdout or "[]")
        return data[0].get("dev") if data else None
    except Exception:
        return None


def tailscale_state():
    """None (nicht installiert) oder dict(running, state, exit_node, ips)"""
    if not which("tailscale"):
        return None
    try:
        r = subprocess.run(["tailscale", "status", "--json"], capture_output=True, text=True, timeout=6)
        data = json.loads(r.stdout or "{}")
    except Exception:
        return {"running": False, "state": "Dienst nicht erreichbar", "exit_node": None, "ips": []}
    state = data.get("BackendState", "") or "unbekannt"
    exit_name = None
    if data.get("ExitNodeStatus"):
        for p in (data.get("Peer") or {}).values():
            if p.get("ExitNode"):
                exit_name = (p.get("HostName") or p.get("DNSName") or "").rstrip(".") or "Exit-Node"
                break
        exit_name = exit_name or "Exit-Node"
    return {"running": state == "Running", "state": state, "exit_node": exit_name,
            "ips": (data.get("Self") or {}).get("TailscaleIPs") or data.get("TailscaleIPs") or []}


TS_STATES = {"Stopped": "gestoppt/pausiert", "NeedsLogin": "nicht angemeldet", "NeedsMachineAuth": "wartet auf Freigabe",
             "Starting": "startet", "NoState": "aus"}


def vpn_state(ifaces=None):
    """Einheitlicher VPN-Zustand für die Sicherheits-Übersicht.
    Zählt nur Verbindungen, die wirklich aktiv sind – eine vorhandene, aber pausierte Schnittstelle
    (z. B. tailscale0 nach „tailscale down“) gilt nicht als verbunden."""
    if ifaces is None:
        ifaces = net_interfaces()[0]
    res = {"mullvad": None, "tailscale": tailscale_state(), "others": [], "route_dev": internet_route_dev()}
    if which("mullvad"):
        rc, st = _mullvad(["status"])
        res["mullvad"] = st
    for i in ifaces:
        if i["kind"] != "VPN" or i["name"].startswith("tailscale"):
            continue
        if i["name"].startswith(("wg0-mullvad", "mullvad")) and res["mullvad"] is not None:
            continue
        if i["state"] in ("UP", "UNKNOWN") and (i["ipv4"] or i["ipv6"]):
            res["others"].append(i["name"])
    return res


def public_ip_info():
    """Fragt am.i.mullvad.net nach öffentlicher IP, Ort, Anbieter und ob Mullvad genutzt wird."""
    import urllib.request
    req = urllib.request.Request("https://am.i.mullvad.net/json", headers={"User-Agent": "tuxdex"})
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read().decode())


def system_summary():
    osr = {}
    for line in _read("/etc/os-release").splitlines():
        k, _, v = line.partition("=")
        osr[k] = v.strip('"')
    dmi = "/sys/class/dmi/id"
    vendor, product = _first_line(f"{dmi}/sys_vendor"), _first_line(f"{dmi}/product_name")
    board = " ".join(x for x in (_first_line(f"{dmi}/board_vendor"), _first_line(f"{dmi}/board_name")) if x)
    bios = " ".join(x for x in (_first_line(f"{dmi}/bios_version"), _first_line(f"{dmi}/bios_date")) if x)
    cores, threads = cpu_threads_cores()
    mem = meminfo()
    session = os.environ.get("XDG_SESSION_TYPE", "")
    desk = os.environ.get("XDG_CURRENT_DESKTOP", "") or os.environ.get("DESKTOP_SESSION", "")
    return {
        "Computer": " ".join(x for x in (vendor, product) if x and "To be filled" not in x) or "—",
        "Mainboard": board or "—",
        "BIOS/UEFI": (bios or "—") + ("  ·  UEFI" if os.path.isdir("/sys/firmware/efi") else "  ·  Legacy-BIOS"),
        "Prozessor": f"{cpu_model()}  ·  {cores} Kerne / {threads} Threads",
        "Grafik": "\n".join(g["name"] for g in gpus()) or "—",
        "Arbeitsspeicher": fmt_bytes(mem.get("MemTotal", 0)),
        "Betriebssystem": osr.get("PRETTY_NAME", "Linux"),
        "Kernel": os.uname().release,
        "Desktop": " · ".join(x for x in (desk, session.capitalize() if session else "") if x) or "—",
        "Rechnername": os.uname().nodename,
    }


# ---- Programm-Icons für Prozesse ------------------------------------------

_DESKTOP_MAP = None


def desktop_map():
    """{schlüssel: (icon, name)} – Schlüssel: Programmname aus Exec, Desktop-ID, StartupWMClass"""
    global _DESKTOP_MAP
    if _DESKTOP_MAP is not None:
        return _DESKTOP_MAP
    m = {}
    dirs = [os.path.expanduser("~/.local/share/applications"), "/usr/local/share/applications",
            "/usr/share/applications", "/var/lib/flatpak/exports/share/applications",
            os.path.expanduser("~/.local/share/flatpak/exports/share/applications"),
            "/var/lib/snapd/desktop/applications"]
    for d in dirs:
        try:
            files = [f for f in os.listdir(d) if f.endswith(".desktop")]
        except Exception:
            continue
        for fn in files:
            entry, in_main = {}, False
            for line in _read(os.path.join(d, fn)).splitlines():
                if line.startswith("["):
                    in_main = line.strip() == "[Desktop Entry]"
                    continue
                if in_main and "=" in line:
                    k, _, v = line.partition("=")
                    entry.setdefault(k.strip(), v.strip())
            icon = entry.get("Icon")
            if not icon:
                continue
            val = (icon, entry.get("Name", fn[:-8]))
            did = fn[:-8]
            m.setdefault(did.lower(), val)
            m.setdefault(did.split(".")[-1].lower(), val)
            if entry.get("StartupWMClass"):
                m.setdefault(entry["StartupWMClass"].lower(), val)
            exe = entry.get("Exec", "")
            toks = [t for t in shlex.split(exe, posix=True) if "=" not in t or t.startswith("/")] if exe else []
            toks = [t for t in toks if t not in ("env", "flatpak", "run") and not t.startswith(("-", "%"))]
            # Interpreter überspringen: „python3 /pfad/skript.py“ → skript
            while toks and re.match(r"^(python[\d.]*|bash|sh|java|node|perl|ruby|gjs)$", os.path.basename(toks[0])):
                toks = toks[1:]
            if toks:
                base = os.path.basename(toks[0]).lower()
                m.setdefault(base, val)
                m.setdefault(re.sub(r"\.(py|sh|js)$", "", base).replace("_", "-"), val)
                if "flatpak" in exe and len(toks) >= 1:
                    m.setdefault(toks[-1].lower(), val)
    _DESKTOP_MAP = m
    return m


def app_for_process(pid, name, cmd):
    """(icon_name, app_name) oder None"""
    m = desktop_map()
    cg = _read(f"/proc/{pid}/cgroup")
    mt = re.search(r"app-flatpak-([\w.\-]+?)-\d+\.scope", cg) or \
        re.search(r"app-(?:[\w]+-)?([\w.\-]+?)(?:@[\w]+\.service|-\d+\.scope)", cg)
    if mt:
        key = mt.group(1).lower()
        for k in (key, key.split(".")[-1]):
            if k in m:
                return m[k]
    cand = [name.lower()]
    first = cmd.split(" ", 1)[0] if cmd and not cmd.startswith("[") else ""
    if first:
        cand.append(os.path.basename(first).lower())
        if re.match(r"^(python[\d.]*|bash|sh|java|node|perl|ruby|gjs)$", os.path.basename(first)) \
                and len(cmd.split()) > 1:
            cand = [os.path.basename(cmd.split()[1]).lower()]
            cand.append(re.sub(r"\.(py|sh|js)$", "", cand[0]).replace("_", "-"))
    for c in cand:
        if c in m:
            return m[c]
    return None


_ICON_CACHE = {}


def themed_icon(name):
    if name in _ICON_CACHE:
        return _ICON_CACHE[name]
    icon = QIcon()
    if name.startswith("/") and os.path.exists(name):
        icon = QIcon(name)
    else:
        icon = QIcon.fromTheme(name)
        if icon.isNull():
            for ext in ("png", "svg", "xpm"):
                p = f"/usr/share/pixmaps/{name}.{ext}"
                if os.path.exists(p):
                    icon = QIcon(p)
                    break
        if icon.isNull():
            for base in ("/usr/share/icons/hicolor", os.path.expanduser("~/.local/share/icons/hicolor"),
                         "/var/lib/flatpak/exports/share/icons/hicolor"):
                for sz in ("scalable", "256x256", "128x128", "64x64", "48x48", "32x32"):
                    for ext in ("svg", "png"):
                        p = f"{base}/{sz}/apps/{name}.{ext}"
                        if os.path.exists(p):
                            icon = QIcon(p)
                            break
                    if not icon.isNull():
                        break
                if not icon.isNull():
                    break
    _ICON_CACHE[name] = icon
    return icon


def letter_icon(text, size=20):
    key = ("letter", text[:1].upper())
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]
    px = QPixmap(size * 2, size * 2)
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(COLORS["bg3"]))
    p.drawRoundedRect(QRectF(0, 0, size * 2, size * 2), 10, 10)
    f = QFont(FONTS["sans"])
    f.setPixelSize(int(size * 1.1))
    f.setWeight(QFont.DemiBold)
    p.setFont(f)
    p.setPen(QColor(COLORS["muted"]))
    p.drawText(QRectF(0, 0, size * 2, size * 2), Qt.AlignCenter, text[:1].upper() or "?")
    p.end()
    icon = QIcon(px)
    _ICON_CACHE[key] = icon
    return icon


def setup_icon_theme():
    if not QIcon.themeName() or QIcon.themeName() == "hicolor":
        for t in ("breeze-dark", "breeze", "Papirus-Dark", "Papirus", "Adwaita", "hicolor"):
            if os.path.isdir(f"/usr/share/icons/{t}"):
                QIcon.setThemeName(t)
                break
    QIcon.setFallbackThemeName("hicolor")


class Segmented(QFrame):
    """Umschalter innerhalb eines Tabs (z. B. Prozesse | Leistung | System)."""

    def __init__(self, labels, on_change):
        super().__init__()
        self.setObjectName("Segmented")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(2)
        self.btns = []
        for i, l in enumerate(labels):
            b = QPushButton(l)
            b.setObjectName("Seg")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.TabFocus)
            b.clicked.connect(lambda _=False, i=i: (self.set(i), on_change(i)))
            lay.addWidget(b)
            self.btns.append(b)
        self.set(0)

    def set(self, idx):
        for i, b in enumerate(self.btns):
            b.setChecked(i == idx)


ENERGY_LEVELS = [(0.5, "sehr niedrig"), (5, "niedrig"), (20, "mittel"), (50, "hoch"), (1e9, "sehr hoch")]


def energy_label(cpu):
    for lim, txt in ENERGY_LEVELS:
        if cpu < lim:
            return txt
    return "sehr hoch"


class TaskTab(Page):
    COLS = [("Name", 230), ("PID", 70), ("Benutzer", 95), ("CPU", 70), ("Arbeitsspeicher", 115),
            ("Datenträger", 100), ("Energie (gesch.)", 120), ("Status", 100), ("Befehl", 300)]
    INTERVAL = 2000

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.prev_total = None
        self.prev_ticks = {}
        self.prev_io = {}
        self.prev_net = None
        self.prev_disk = None
        self.data = {}
        self.busy = False
        self.app_cache = {}   # pid -> (icon_name, app_name) | None

        self.badge = StatusBadge("info", "Live · alle 2 s")
        self.pause_btn = Button("Pausieren", "ghost", self.toggle_pause)
        self.seg = Segmented(["Prozesse", "Leistung", "System"], self._switch)
        self.lay.addLayout(page_header("Taskmanager", self.seg, self.badge, self.pause_btn))

        self.views = QStackedWidget()
        self.lay.addWidget(self.views, 1)

        # ---------- Prozesse ----------
        pv = QWidget()
        pl = QVBoxLayout(pv)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(16)
        mini = QHBoxLayout()
        mini.setSpacing(16)
        self.m_cpu, self.m_ram, self.m_net, self.m_bat = (StatTile(t, compact=True) for t in
                                                          ("Prozessor", "Arbeitsspeicher", "Netzwerk", "Akku"))
        for t in (self.m_cpu, self.m_ram, self.m_net, self.m_bat):
            mini.addWidget(t, 1)
        pl.addLayout(mini)

        pp = Panel("Prozesse")
        top = QHBoxLayout()
        top.setSpacing(8)
        self.search = LineEdit(placeholder="Name, PID, Benutzer oder Befehl …")
        self.search.textChanged.connect(lambda _: self._render())
        top.addWidget(self.search, 1)
        self.filter = QComboBox()
        self.filter.addItems(["Alle Prozesse", "Programme", "Hintergrundprozesse", "Nur meine"])
        self.filter.setMinimumWidth(190)
        self.filter.setMinimumHeight(38)
        self.filter.currentIndexChanged.connect(lambda _: self._render())
        top.addWidget(self.filter)
        pp.body.addLayout(top)

        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels([c[0].upper() for c in self.COLS])
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setIconSize(QSize(20, 20))
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(30)
        hh = self.table.horizontalHeader()
        hh.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        hh.setStretchLastSection(True)
        hh.setSortIndicatorShown(True)
        for i, (_, w) in enumerate(self.COLS):
            self.table.setColumnWidth(i, w)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(3, Qt.DescendingOrder)
        self.table.setMinimumHeight(420)
        self.table.itemSelectionChanged.connect(self._sel_changed)
        pp.body.addWidget(self.table, 1)

        acts = QHBoxLayout()
        acts.setSpacing(8)
        self.sel_label = Label("Kein Prozess ausgewählt", "Muted")
        acts.addWidget(self.sel_label, 1)
        self.b_nice_down = Button("Priorität senken", "ghost", lambda: self.renice(+5),
                                  "nice +5 – Prozess bekommt weniger CPU-Zeit")
        self.b_nice_up = Button("Priorität erhöhen", "ghost", lambda: self.renice(-5),
                                "nice −5 – braucht root-Rechte")
        self.b_term = Button("Beenden", "ghost", lambda: self.kill(signal.SIGTERM))
        self.b_kill = Button("Erzwingen", "danger", lambda: self.kill(signal.SIGKILL))
        for b in (self.b_nice_down, self.b_nice_up, self.b_term, self.b_kill):
            acts.addWidget(b)
        pp.body.addLayout(acts)
        pp.body.addWidget(Label(
            "CPU = Anteil an der Leistung aller Kerne. Energie wird aus der CPU-Last geschätzt – Linux misst den "
            "Verbrauch einzelner Programme nicht direkt. Datenträger = Lesen + Schreiben pro Sekunde "
            "(bei Prozessen anderer Benutzer nur mit root sichtbar).", "Hint", wrap=True))
        pl.addWidget(pp, 1)
        self.views.addWidget(pv)

        # ---------- Leistung ----------
        lv = QWidget()
        ll = QGridLayout(lv)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(16)
        self.t_cpu = StatTile("Prozessor")
        self.t_ram = StatTile("Arbeitsspeicher")
        self.t_gpu = StatTile("Grafik")
        self.t_net = StatTile("Netzwerk", maxval=None)
        self.t_disk = StatTile("Datenträger", maxval=None)
        self.t_bat = StatTile("Akku")
        self.t_swap = StatTile("Swap")
        self.t_sys = StatTile("System")
        self.t_sys.spark.hide()
        for i, t in enumerate((self.t_cpu, self.t_ram, self.t_gpu, self.t_net, self.t_disk, self.t_bat,
                               self.t_swap, self.t_sys)):
            ll.addWidget(t, i // 3, i % 3)
        for c in range(3):
            ll.setColumnStretch(c, 1)
        ll.setRowStretch(3, 1)
        self.views.addWidget(lv)

        # ---------- System ----------
        sv = QWidget()
        sl = QVBoxLayout(sv)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(16)
        hw = Panel("Hardware & System")
        self.sys_grid = QGridLayout()
        self.sys_grid.setHorizontalSpacing(24)
        self.sys_grid.setVerticalSpacing(12)
        hw.body.addLayout(self.sys_grid)
        sl.addWidget(hw)
        netp = Panel("Netzwerk & IP-Adressen", [Button("Öffentliche IP prüfen", "ghost", self.check_public_ip,
                                                       "Fragt am.i.mullvad.net nach deiner öffentlichen IP")])
        self.net_box = QVBoxLayout()
        self.net_box.setSpacing(8)
        netp.body.addLayout(self.net_box)
        self.pub_label = Label("Öffentliche IP: noch nicht geprüft (Abfrage über am.i.mullvad.net)", "Hint", wrap=True)
        self.pub_label.setTextFormat(Qt.RichText)
        netp.body.addWidget(self.pub_label)
        sl.addWidget(netp)
        batp = Panel("Akku")
        self.bat_box = QVBoxLayout()
        batp.body.addLayout(self.bat_box)
        sl.addWidget(batp)
        self.bat_panel = batp
        sl.addStretch(1)
        self.views.addWidget(sv)

        self._sel_changed()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(self.INTERVAL)
        QTimer.singleShot(200, self.tick)

    # ---- Ansichten --------------------------------------------------------

    def _switch(self, idx):
        self.views.setCurrentIndex(idx)
        if idx == 2:
            self.load_system()

    def toggle_pause(self):
        if self.timer.isActive():
            self.timer.stop()
            self.pause_btn.setText("Fortsetzen")
            self.badge.set("off", "Pausiert")
        else:
            self.timer.start(self.INTERVAL)
            self.pause_btn.setText("Pausieren")
            self.badge.set("info", "Live · alle 2 s")
            self.tick()

    # ---- Datenerfassung (Hintergrund-Thread) ------------------------------

    def tick(self):
        if self.busy or not self.isVisible():
            return
        self.busy = True
        want_gpu = self.views.currentIndex() == 1

        def worker():
            total, idle = cpu_times()
            procs = read_processes()
            for pid, p in procs.items():
                io = _read(f"/proc/{pid}/io")
                m1 = re.search(r"read_bytes: (\d+)", io)
                m2 = re.search(r"write_bytes: (\d+)", io)
                p["io"] = int(m1.group(1)) + int(m2.group(1)) if (m1 and m2) else None
                if pid not in self.app_cache:
                    self.app_cache[pid] = app_for_process(pid, p["name"], p["cmd"])
                p["app"] = self.app_cache[pid]
            snap = {
                "t": time.time(), "total": total, "idle": idle, "procs": procs, "mem": meminfo(),
                "load": _read("/proc/loadavg").split()[:3],
                "up": float((_read("/proc/uptime").split() or ["0"])[0]),
                "net": net_counters(), "disk": disk_counters(), "bat": batteries(),
                "temps": temperatures(), "mhz": cpu_mhz(), "gpus": gpus() if want_gpu else None,
            }
            ui(lambda: self._update(snap))

        threading.Thread(target=worker, daemon=True).start()

    def _update(self, s):
        self.busy = False
        procs, mem = s["procs"], s["mem"]
        cpu_pct, dt = None, 0
        if self.prev_total:
            dt = s["total"] - self.prev_total[0]
            di = s["idle"] - self.prev_total[1]
            cpu_pct = 100.0 * (dt - di) / dt if dt > 0 else 0.0
        secs = max(0.5, s["t"] - (self.prev_total[2] if self.prev_total else s["t"] - 2))
        for pid, p in procs.items():
            prev = self.prev_ticks.get(pid)
            p["cpu"] = 100.0 * (p["ticks"] - prev) / dt if (prev is not None and dt > 0) else 0.0
            pio = self.prev_io.get(pid)
            p["io_rate"] = (p["io"] - pio) / secs if (p["io"] is not None and pio is not None) else \
                (None if p["io"] is None else 0)
        self.prev_total = (s["total"], s["idle"], s["t"])
        self.prev_ticks = {pid: p["ticks"] for pid, p in procs.items()}
        self.prev_io = {pid: p["io"] for pid, p in procs.items() if p["io"] is not None}
        self.app_cache = {pid: v for pid, v in self.app_cache.items() if pid in procs}
        self.data = procs

        # Prozessor
        temps = s["temps"]
        avg_mhz, max_mhz = s["mhz"]
        cpu_sub = [f"{N_CPU} Threads"]
        if avg_mhz:
            cpu_sub.append(f"{avg_mhz / 1000:.2f} GHz")
        if "cpu" in temps:
            cpu_sub.append(f"{temps['cpu']:.0f} °C")
        cpu_sub.append("Last " + " / ".join(s["load"]))
        if cpu_pct is not None:
            for t in (self.t_cpu, self.m_cpu):
                t.set(f"{cpu_pct:.0f} %", " · ".join(cpu_sub), cpu_pct)
        # RAM
        mt, ma = mem.get("MemTotal", 0), mem.get("MemAvailable", 0)
        used = mt - ma
        for t in (self.t_ram, self.m_ram):
            t.set(f"{used / mt * 100:.0f} %" if mt else "—", f"{fmt_bytes(used)} von {fmt_bytes(mt)}",
                  used / mt * 100 if mt else 0)
        # Swap
        st, sf = mem.get("SwapTotal", 0), mem.get("SwapFree", 0)
        if st:
            self.t_swap.set(f"{(st - sf) / st * 100:.0f} %", f"{fmt_bytes(st - sf)} von {fmt_bytes(st)}",
                            (st - sf) / st * 100)
        else:
            self.t_swap.set("aus", "kein Swap aktiv", 0)
        # Netzwerk
        net = {k: v for k, v in s["net"].items() if k != "lo"}
        rx = sum(v[0] for v in net.values())
        tx = sum(v[1] for v in net.values())
        if self.prev_net:
            drx, dtx = max(0, rx - self.prev_net[0]) / secs, max(0, tx - self.prev_net[1]) / secs
            txt = f"↓ {fmt_bytes(drx)}/s"
            sub = f"↑ {fmt_bytes(dtx)}/s · gesamt ↓ {fmt_bytes(rx)} ↑ {fmt_bytes(tx)}"
            self.t_net.set(txt, sub, drx + dtx)
            self.m_net.set(txt, f"↑ {fmt_bytes(dtx)}/s", drx + dtx)
        self.prev_net = (rx, tx)
        # Datenträger
        rd, wr = s["disk"]
        if self.prev_disk:
            drd, dwr = max(0, rd - self.prev_disk[0]) / secs, max(0, wr - self.prev_disk[1]) / secs
            self.t_disk.set(f"{fmt_bytes(drd + dwr)}/s", f"Lesen {fmt_bytes(drd)}/s · Schreiben {fmt_bytes(dwr)}/s",
                            drd + dwr)
        self.prev_disk = (rd, wr)
        # Grafik
        if s["gpus"] is not None:
            gl = s["gpus"]
            g = next((x for x in gl if x.get("busy") is not None), gl[0] if gl else None)
            if g:
                sub = [g["name"]]
                if g.get("vram_total"):
                    sub.append(f"VRAM {fmt_bytes(g['vram_used'])} / {fmt_bytes(g['vram_total'])}")
                if "gpu" in temps:
                    sub.append(f"{temps['gpu']:.0f} °C")
                if g.get("busy") is not None:
                    self.t_gpu.set(f"{g['busy']} %", " · ".join(sub), g["busy"])
                else:
                    self.t_gpu.set("—", " · ".join(sub) + " · Auslastung vom Treiber nicht gemeldet", None)
            else:
                self.t_gpu.set("—", "keine Grafikkarte erkannt", None)
        # Akku
        bats, ac = s["bat"]
        if bats:
            b = bats[0]
            st_txt = BAT_STATUS.get(b["status"], b["status"])
            sub = [st_txt]
            if b["watts"] is not None:
                sub.append(f"{b['watts']:.1f} W")
            if b["hours"]:
                h, m = int(b["hours"]), int((b["hours"] % 1) * 60)
                sub.append(("noch " if b["status"] == "Discharging" else "voll in ") + f"{h}:{m:02d} h")
            for t in (self.t_bat, self.m_bat):
                t.set(f"{b['capacity']} %" if b["capacity"] is not None else "—", " · ".join(sub),
                      b["capacity"])
        else:
            for t in (self.t_bat, self.m_bat):
                t.set("Netz", "kein Akku – Netzbetrieb", None)
        # System
        d, rem = divmod(int(s["up"]), 86400)
        h, rem = divmod(rem, 3600)
        n_apps = sum(1 for p in procs.values() if p.get("app"))
        self.t_sys.set(f"{len(procs)}", f"Prozesse ({n_apps} von Programmen) · läuft seit "
                       + (f"{d} T " if d else "") + f"{h} Std {rem // 60} Min")
        if self.views.currentIndex() == 0:
            self._render()

    # ---- Tabelle ----------------------------------------------------------

    def _render(self):
        q = self.search.text().strip().lower()
        mode = self.filter.currentIndex()
        me = os.getuid()
        rows = []
        for pid, p in self.data.items():
            if mode == 1 and not p.get("app"):
                continue
            if mode == 2 and p.get("app"):
                continue
            if mode == 3 and p["uid"] != me:
                continue
            app_name = p["app"][1] if p.get("app") else ""
            if q and q not in f"{p['name']} {app_name} {pid} {p['user']} {p['cmd']}".lower():
                continue
            rows.append((pid, p))

        sel_pid = self._selected_pid()
        vbar = self.table.verticalScrollBar().value()
        sort_col = self.table.horizontalHeader().sortIndicatorSection()
        sort_ord = self.table.horizontalHeader().sortIndicatorOrder()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        mono = QFont(FONTS["mono"], 10)
        hot = QColor(COLORS["warn"])
        for r, (pid, p) in enumerate(rows):
            app = p.get("app")
            label = app[1] if app else p["name"]
            name_it = QTableWidgetItem(label)
            if app:
                ic = themed_icon(app[0])
                name_it.setIcon(ic if not ic.isNull() else letter_icon(label))
            elif not p["cmd"].startswith("["):
                name_it.setIcon(letter_icon(p["name"]))
            else:
                name_it.setIcon(QIcon())
            iorate = p.get("io_rate")
            cells = [
                name_it,
                NumItem(str(pid), pid),
                QTableWidgetItem(p["user"]),
                NumItem(f"{p['cpu']:.1f} %", p["cpu"]),
                NumItem(fmt_bytes(p["rss"]), p["rss"]),
                NumItem("—" if iorate is None else (f"{fmt_bytes(iorate)}/s" if iorate else "0"),
                        -1 if iorate is None else iorate),
                NumItem(energy_label(p["cpu"]), p["cpu"]),
                QTableWidgetItem(STATES.get(p["state"], p["state"])),
                QTableWidgetItem(p["cmd"]),
            ]
            for c, it in enumerate(cells):
                if c in (1, 3, 4, 5, 8):
                    it.setFont(mono)
                if c in (1, 3, 4, 5):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if c in (3, 6) and p["cpu"] >= 50:
                    it.setForeground(hot)
                it.setToolTip(f"{label} · PID {pid}\n{p['cmd']}")
                self.table.setItem(r, c, it)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(sort_col, sort_ord)
        if sel_pid is not None:
            for r in range(self.table.rowCount()):
                it = self.table.item(r, 1)
                if it and it.data(Qt.UserRole) == sel_pid:
                    self.table.selectRow(r)
                    break
        self.table.verticalScrollBar().setValue(vbar)

    def _selected_pid(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        it = self.table.item(rows[0].row(), 1)
        return it.data(Qt.UserRole) if it else None

    def _sel_changed(self):
        pid = self._selected_pid()
        p = self.data.get(pid) if pid is not None else None
        for b in (self.b_nice_down, self.b_nice_up, self.b_term, self.b_kill):
            b.setEnabled(p is not None and pid > 1)
        if p:
            nm = p["app"][1] if p.get("app") else p["name"]
            self.sel_label.setText(f"{nm} · PID {pid} · {p['user']} · nice {p['nice']}")
        else:
            self.sel_label.setText("Kein Prozess ausgewählt")

    # ---- System-Ansicht ---------------------------------------------------

    def load_system(self):
        def worker():
            info = system_summary()
            ifaces, gw, dns = net_interfaces()
            bats, ac = batteries()
            ui(lambda: self._show_system(info, ifaces, gw, dns, bats, ac))
        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def _clear(layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
            elif item.layout():
                TaskTab._clear(item.layout())

    def _show_system(self, info, ifaces, gw, dns, bats, ac):
        self._clear(self.sys_grid)
        for i, (k, v) in enumerate(info.items()):
            self.sys_grid.addLayout(Field(k, Label(v, "Value", wrap=True)), i // 2, i % 2)
        self._clear(self.net_box)
        for it in ifaces:
            if it["kind"] == "Virtuell" and not it["ipv4"]:
                continue
            row = QHBoxLayout()
            row.setSpacing(12)
            up = it["state"] in ("UP", "UNKNOWN") and (it["ipv4"] or it["ipv6"])
            row.addWidget(StatusBadge("ok" if up else "off", f"{it['kind']} · {it['name']}"))
            addrs = ", ".join(it["ipv4"] + it["ipv6"][:1]) or "keine Adresse"
            lab = Label(addrs, "Value", wrap=True)
            lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
            row.addWidget(lab, 1)
            row.addWidget(Label(it["mac"], "Hint"))
            self.net_box.addLayout(row)
        extra = Label(f"Standard-Gateway: {gw or '—'}   ·   DNS-Server: {', '.join(dns) or '—'}", "Hint", wrap=True)
        extra.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.net_box.addWidget(extra)
        self._clear(self.bat_box)
        if not bats:
            self.bat_box.addWidget(Label("Kein Akku gefunden – das Gerät läuft am Netz.", "Muted"))
        for b in bats:
            parts = [f"{b['capacity']} %" if b["capacity"] is not None else "—",
                     BAT_STATUS.get(b["status"], b["status"])]
            if b["watts"] is not None:
                parts.append(f"{b['watts']:.1f} W")
            if b["health"]:
                parts.append(f"Zustand {b['health']:.0f} % der Originalkapazität")
            if b["model"]:
                parts.append(b["model"])
            self.bat_box.addWidget(Label("  ·  ".join(parts), "Value", wrap=True))

    def check_public_ip(self):
        self.pub_label.setText("Öffentliche IP wird geprüft …")

        def worker():
            try:
                d = public_ip_info()
                txt = (f"Öffentliche IP: <b>{d.get('ip', '?')}</b> · {d.get('city') or ''} "
                       f"{d.get('country') or ''} · {d.get('organization') or ''} · "
                       + (f'<span style="color:{COLORS["ok"]}">● über Mullvad-VPN</span>'
                          if d.get("mullvad_exit_ip") else
                          f'<span style="color:{COLORS["warn"]}">▲ nicht über Mullvad</span>'))
            except Exception as e:
                txt = f"Öffentliche IP konnte nicht ermittelt werden ({e})."
            ui(lambda: self.pub_label.setText(txt))
        threading.Thread(target=worker, daemon=True).start()

    # ---- Aktionen ---------------------------------------------------------

    def _as_root(self, p):
        return p["uid"] != os.getuid()

    def kill(self, sig):
        pid = self._selected_pid()
        p = self.data.get(pid)
        if not p:
            return
        nm = p["app"][1] if p.get("app") else p["name"]
        hard = sig == signal.SIGKILL
        if not ask_confirm(self, "Prozess erzwingen" if hard else "Prozess beenden",
                           f"{nm} (PID {pid}) {'sofort stoppen' if hard else 'beenden'}?"
                           + ("\n\nUngespeicherte Daten gehen verloren." if hard else "")
                           + ("\n\nDer Prozess gehört „" + p["user"] + "“ – dafür sind root-Rechte nötig."
                              if self._as_root(p) else ""),
                           "Erzwingen" if hard else "Beenden", danger=hard):
            return
        if not self._as_root(p):
            try:
                os.kill(pid, sig)
                self.app.set_status(f"Signal an {nm} (PID {pid}) gesendet.")
            except ProcessLookupError:
                self.app.set_status("Prozess existiert nicht mehr.")
            except PermissionError:
                show_error(self, "Keine Berechtigung", "Der Prozess darf nicht beendet werden.")
            QTimer.singleShot(300, self.tick)
            return
        if not self.app.priv.ensure(self):
            return
        run_capture_async(["kill", f"-{int(sig)}", str(pid)],
                          lambda rc, o, e: (self.app.set_status(
                              f"{nm} (PID {pid}) " + ("beendet." if rc == 0 else f"– Fehler: {e.strip()}")),
                              self.tick()), needs_sudo=True)

    def renice(self, delta):
        pid = self._selected_pid()
        p = self.data.get(pid)
        if not p:
            return
        new = max(-20, min(19, p["nice"] + delta))
        needs_root = delta < 0 or self._as_root(p)
        if needs_root and not self.app.priv.ensure(self):
            return
        run_capture_async(["renice", "-n", str(new), "-p", str(pid)],
                          lambda rc, o, e: (self.app.set_status(
                              f"Priorität jetzt nice {new}." if rc == 0
                              else f"renice fehlgeschlagen: {e.strip()}"), self.tick()),
                          needs_sudo=needs_root)


# --------------------------------------------------------------------------
# Modul: Antivirus (ClamAV)
# --------------------------------------------------------------------------

QUARANTINE_DIR = os.path.join(os.path.expanduser("~/.local/share"), "tuxdex", "quarantine")
QUARANTINE_INDEX = os.path.join(QUARANTINE_DIR, "index.json")
AV_LAST = os.path.join(CACHE_DIR, "clamav_last.json")
FOUND_RE = re.compile(r"^(.*): (.+) FOUND$")


_MONTHS = {m: i + 1 for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"))}


def parse_c_date(text):
    """Englisches Datum wie „Sat Sep 26 08:24:13 2026“ unabhängig von der Systemsprache lesen."""
    m = re.search(r"([A-Za-z]{3})\s+(\d{1,2})\s+(\d{1,2}):(\d{2}):(\d{2})\s+(\d{4})", text)
    if not m or m.group(1).lower() not in _MONTHS:
        raise ValueError(f"unbekanntes Datum: {text!r}")
    return datetime(int(m.group(6)), _MONTHS[m.group(1).lower()], int(m.group(2)),
                    int(m.group(3)), int(m.group(4)), int(m.group(5)))


def _load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=1)
    except Exception:
        pass


class AntivirusTab(Page):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.run = None
        self.found = []          # [{path, threat, status}]
        self.scan_started = None
        self.summary = {}

        self.badge = StatusBadge("off", "Prüfe …")
        self.lay.addLayout(page_header("Antivirus (ClamAV)", self.badge,
                                       Button("↻", "icon", self.refresh_status, "Status neu prüfen")))

        # --- Status ---
        st = Panel("Schutz-Status")
        self.st_grid = QGridLayout()
        self.st_grid.setHorizontalSpacing(24)
        self.st_grid.setVerticalSpacing(10)
        st.body.addLayout(self.st_grid)
        self.st_note = Label("", "Warn", wrap=True)
        self.st_note.setTextFormat(Qt.RichText)
        st.body.addWidget(self.st_note)
        b = QHBoxLayout()
        b.setSpacing(8)
        self.b_fresh = Button("Signaturen aktualisieren", "ghost", self.update_signatures)
        self.b_auto = Button("Automatische Updates aktivieren", "ghost", self.enable_auto)
        for x in (self.b_fresh, self.b_auto):
            b.addWidget(x)
        b.addStretch(1)
        st.body.addLayout(b)
        self.lay.addWidget(st)

        # --- Scan ---
        sc = Panel("Scan")
        r = QHBoxLayout()
        r.setSpacing(8)
        self.target = QComboBox()
        home = os.path.expanduser("~")
        self.target.addItem("Persönlicher Ordner  (~)", home)
        if os.path.isdir(os.path.join(home, "Downloads")):
            self.target.addItem("Downloads  (~/Downloads)", os.path.join(home, "Downloads"))
        self.target.addItem("Ganzes System  (/)", "/")
        self.target.addItem("Eigener Ordner …", "__custom__")
        self.target.setMinimumWidth(280)
        self.target.activated.connect(self._target_chosen)
        r.addLayout(Field("Was scannen?", self.target))
        r.addStretch(1)
        right = QVBoxLayout()
        right.addStretch(1)
        rb = QHBoxLayout()
        rb.setSpacing(8)
        self.b_scan = Button("Scan starten", "primary", self.start_scan)
        self.b_stop = Button("Scan abbrechen", "danger", self.stop_scan)
        self.b_stop.hide()
        rb.addWidget(self.b_scan)
        rb.addWidget(self.b_stop)
        right.addLayout(rb)
        r.addLayout(right)
        sc.body.addLayout(r)
        opts = QHBoxLayout()
        opts.setSpacing(16)
        self.cb_root = QCheckBox("Mit root-Rechten (nötig für Systemordner)")
        self.cb_quar = QCheckBox("Funde automatisch in Quarantäne verschieben")
        opts.addWidget(self.cb_root)
        opts.addWidget(self.cb_quar)
        opts.addStretch(1)
        sc.body.addLayout(opts)
        # Live-Status des Scans
        self.scan_box = QWidget()
        sbx = QVBoxLayout(self.scan_box)
        sbx.setContentsMargins(0, 4, 0, 0)
        sbx.setSpacing(8)
        srow = QHBoxLayout()
        srow.setSpacing(12)
        self.scan_state = StatusBadge("off", "Nicht aktiv")
        srow.addWidget(self.scan_state)
        self.scan_time = Label("", "Value")
        srow.addWidget(self.scan_time)
        srow.addStretch(1)
        self.scan_eta = Label("", "Muted")
        srow.addWidget(self.scan_eta)
        sbx.addLayout(srow)
        self.scan_bar = ProgressBar()
        sbx.addWidget(self.scan_bar)
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(8)
        self.st_files = Label("—", "Value")
        self.st_bytes = Label("—", "Value")
        self.st_rate = Label("—", "Value")
        self.st_found = Label("0", "Value")
        for i, (k, w) in enumerate((("Dateien", self.st_files), ("Datenmenge", self.st_bytes),
                                    ("Tempo", self.st_rate), ("Funde", self.st_found))):
            grid.addLayout(Field(k, w), 0, i)
        sbx.addLayout(grid)
        self.scan_cur = Label("", "Hint")
        self.scan_cur.setTextInteractionFlags(Qt.TextSelectableByMouse)
        sbx.addWidget(self.scan_cur)
        self.scan_box.hide()
        sc.body.addWidget(self.scan_box)
        self.progress = Label("", "Muted")
        sc.body.addWidget(self.progress)
        self.last_scan = Label("", "Hint")
        sc.body.addWidget(self.last_scan)
        self.lay.addWidget(sc)
        self.scan_panel = sc

        # --- Funde ---
        fp = Panel("Funde")
        self.ftable = QTableWidget(0, 3)
        self.ftable.setHorizontalHeaderLabels(["DATEI", "BEDROHUNG", "STATUS"])
        self.ftable.verticalHeader().setVisible(False)
        self.ftable.setShowGrid(False)
        self.ftable.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.ftable.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.ftable.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.ftable.setColumnWidth(0, 460)
        self.ftable.setColumnWidth(1, 340)
        self.ftable.horizontalHeader().setStretchLastSection(True)
        self.ftable.setMinimumHeight(150)
        self.ftable.itemSelectionChanged.connect(self._found_sel)
        self.f_empty = Label("Noch keine Funde.", "Muted")
        fp.body.addWidget(self.f_empty)
        fp.body.addWidget(self.ftable)
        self.ftable.hide()
        fa = QHBoxLayout()
        fa.setSpacing(8)
        self.b_q = Button("In Quarantäne verschieben", "primary", self.quarantine_selected)
        self.b_show = Button("Ordner öffnen", "ghost", self.show_folder)
        self.b_del = Button("Endgültig löschen", "danger", self.delete_selected)
        fa.addWidget(self.b_q)
        fa.addWidget(self.b_show)
        fa.addStretch(1)
        fa.addWidget(self.b_del)
        fp.body.addLayout(fa)
        self.lay.addWidget(fp)
        self.found_panel = fp

        # --- Quarantäne ---
        qp = Panel("Quarantäne", [Button("↻", "icon", self.refresh_quarantine, "Neu laden")])
        self.qtable = QTableWidget(0, 3)
        self.qtable.setHorizontalHeaderLabels(["URSPRÜNGLICHER ORT", "BEDROHUNG", "SEIT"])
        self.qtable.verticalHeader().setVisible(False)
        self.qtable.setShowGrid(False)
        self.qtable.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.qtable.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.qtable.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.qtable.setColumnWidth(0, 460)
        self.qtable.setColumnWidth(1, 340)
        self.qtable.horizontalHeader().setStretchLastSection(True)
        self.qtable.setMinimumHeight(120)
        self.qtable.itemSelectionChanged.connect(self._q_sel)
        self.q_empty = Label("Die Quarantäne ist leer.", "Muted")
        qp.body.addWidget(self.q_empty)
        qp.body.addWidget(self.qtable)
        qa = QHBoxLayout()
        qa.setSpacing(8)
        self.b_restore = Button("Wiederherstellen", "ghost", self.restore_selected)
        self.b_qdel = Button("Endgültig löschen", "danger", self.qdelete_selected)
        qa.addWidget(self.b_restore)
        qa.addStretch(1)
        qa.addWidget(self.b_qdel)
        qp.body.addLayout(qa)
        qp.body.addWidget(Label(f"Dateien in Quarantäne liegen ohne Ausführungsrechte in {short_path(QUARANTINE_DIR)}.",
                                "Hint", wrap=True))
        self.lay.addWidget(qp)

        out = Panel("Ausgabe")
        self.log = LogView(150)
        out.body.addWidget(self.log)
        self.lay.addWidget(out)

        self.tick_timer = QTimer(self)
        self.tick_timer.timeout.connect(self._tick)

        self._found_sel()
        self._render_found()
        self.refresh_quarantine()
        self._show_last()
        self.refresh_status()

    # ---- Status -----------------------------------------------------------

    def _st_item(self, i, label, value, name="Value"):
        self.st_grid.addLayout(Field(label, Label(value, name, wrap=True)), i // 3, i % 3)

    def refresh_status(self):
        def worker():
            res = {"installed": which("clamscan")}
            if res["installed"]:
                r = subprocess.run(["clamscan", "--version"], capture_output=True, text=True)
                res["version"] = r.stdout.strip()
                for svc in ("clamav-freshclam", "clamav-daemon"):
                    try:
                        a = subprocess.run(["systemctl", "is-active", svc], capture_output=True, text=True)
                        res[svc] = a.stdout.strip()
                    except Exception:
                        res[svc] = "unbekannt"
            ui(lambda: self._show_status(res))
        threading.Thread(target=worker, daemon=True).start()

    def _show_status(self, res):
        while self.st_grid.count():
            lay = self.st_grid.takeAt(0).layout()
            if lay:
                while lay.count():
                    w = lay.takeAt(0).widget()
                    if w:
                        w.deleteLater()
        self.installed = res["installed"]
        for x in (self.b_fresh, self.b_auto, self.b_scan):
            x.setEnabled(self.installed)
            x.setVisible(self.installed)
        self.scan_panel.setVisible(self.installed)
        self.found_panel.setVisible(self.installed)
        if not self.installed:
            self.badge.set("off", "Nicht installiert")
            self._st_item(0, "ClamAV", "nicht installiert")
            self.st_note.setText(f'<span style="color:{COLORS["muted"]}">ClamAV ist nicht installiert. Tuxdex '
                                 f'funktioniert auch ohne. Sobald ClamAV auf dem System vorhanden ist, lässt es sich '
                                 f'hier bedienen.</span>')
            return
        # "ClamAV 1.4.1/27411/Wed Sep 25 08:34:07 2026"
        ver = res.get("version", "")
        parts = ver.split("/")
        engine = parts[0].replace("ClamAV", "").strip() if parts else "?"
        sig_ver = parts[1] if len(parts) > 1 else "—"
        sig_date, age_days = "keine Signaturen", None
        if len(parts) > 2:
            try:
                dt = parse_c_date(parts[2])
                sig_date = dt.strftime("%d.%m.%Y %H:%M")
                age_days = (datetime.now() - dt).days
            except ValueError:
                sig_date = parts[2].strip()
        fresh = res.get("clamav-freshclam") == "active"
        daemon = res.get("clamav-daemon") == "active"
        self.daemon_active = daemon
        self._st_item(0, "Engine", engine)
        try:
            db = [os.path.getmtime(os.path.join("/var/lib/clamav", f)) for f in os.listdir("/var/lib/clamav")
                  if f.endswith((".cvd", ".cld"))]
        except Exception:
            db = []
        if db and age_days is None:
            # Fallback: Dateidatum der Datenbank, falls die Versionszeile nicht lesbar ist
            dt = datetime.fromtimestamp(max(db))
            sig_date, age_days = dt.strftime("%d.%m.%Y %H:%M"), (datetime.now() - dt).days
        self._st_item(1, "Signaturen", f"{sig_date}  (Version {sig_ver})")
        self._st_item(2, "Automatische Updates", "● aktiv" if fresh else "○ aus",
                      "Value")
        self._st_item(3, "Scan-Dienst (clamd)", "● läuft – schnelle Scans" if daemon else "○ aus – Scans mit clamscan")
        notes = []
        if age_days is None:
            self.badge.set("danger", "Keine Signaturen")
            notes.append(f'<span style="color:{COLORS["danger"]}">✕ Es sind noch keine Virensignaturen geladen – '
                         + ("der Dienst lädt sie gerade (beim ersten Mal einige Minuten).</span>" if fresh else
                            "„Signaturen aktualisieren“ klicken.</span>"))
        elif age_days > 3:
            self.badge.set("warn", f"Signaturen {age_days} Tage alt")
            notes.append(f"▲ Die Signaturen sind {age_days} Tage alt. Aktualisieren oder automatische "
                         f"Updates aktivieren.")
        else:
            self.badge.set("ok", "Signaturen aktuell")
        if not fresh:
            notes.append(f'<span style="color:{COLORS["muted"]}">Tipp: Automatische Updates halten die '
                         f'Signaturen täglich aktuell (Dienst clamav-freshclam).</span>')
        self.b_auto.setVisible(not fresh)
        self.b_scan.setEnabled(age_days is not None)
        self.b_scan.setToolTip("" if age_days is not None else "Erst Signaturen laden – ohne sie kann ClamAV nichts erkennen.")
        self.b_fresh.setProperty("variant", "primary" if (age_days is None or age_days > 3) else "ghost")
        repolish(self.b_fresh)
        self.st_note.setText("<br>".join(notes))

    def update_signatures(self):
        if not self.app.priv.ensure(self):
            return
        fresh_active = subprocess.run(["systemctl", "is-active", "clamav-freshclam"],
                                      capture_output=True, text=True).stdout.strip() == "active"
        running = subprocess.run(["pgrep", "-x", "freshclam"], capture_output=True, text=True).stdout.strip()
        if fresh_active:
            # Der Dienst hält die Sperre – ein zweites freshclam würde scheitern.
            # Neustart des Dienstes löst sofort eine Aktualisierung aus.
            self.log.set_text("$ sudo systemctl restart clamav-freshclam\n"
                              "Der Dienst clamav-freshclam läuft bereits und lädt die Signaturen selbst.\n"
                              "Neustart löst sofort eine Prüfung aus – der erste Download (~200 MB) kann "
                              "einige Minuten dauern.\n\n")
            run_streaming(["systemctl", "restart", "clamav-freshclam"], self.log, needs_sudo=True,
                          clear_first=False, on_done=lambda rc: self._watch_freshclam())
            return
        if running:
            self.log.set_text("freshclam läuft bereits (PID " + running.replace("\n", ", ")
                              + ") – warte auf das Ergebnis …\n")
            self._watch_freshclam()
            return
        self.log.set_text("$ sudo freshclam\n")

        def done(rc):
            self.log.append_text(f"\n[Exit-Code {rc}]\n")
            if rc != 0:
                self.log.append_text("Tipp: „Automatische Updates aktivieren“ – der Dienst lädt die Signaturen "
                                     "dann selbstständig und täglich.\n")
            self.refresh_status()

        run_streaming(["freshclam"], self.log, needs_sudo=True, clear_first=False, on_done=done)

    def _watch_freshclam(self, rounds=0):
        """Verfolgt den freshclam-Dienst: zeigt neue Meldungen, erkennt Fehler (z. B. Download-Sperre
        des ClamAV-Servers) und hört auf, sobald Signaturen da sind (max. 10 Min.)."""
        def cb(rc, out, err):
            lines = [l for l in out.splitlines() if l.strip()]
            if rc != 0 and not lines:
                lines = ["(Dienst-Meldungen nicht lesbar – bitte oben rechts anmelden)"]
            if lines:
                self.log.append_text("\n".join(lines[-8:]) + "\n")
            text = "\n".join(lines).lower()
            # Signaturen vorhanden?
            ver = subprocess.run(["clamscan", "--version"], capture_output=True, text=True).stdout.strip()
            parts = ver.split("/")
            if len(parts) > 2:
                self.log.append_text(f"● Signaturen sind geladen (Version {parts[1]}, Stand {parts[2].strip()}).\n")
                self.refresh_status()
                return
            # typische Fehler sofort melden statt weiter zu warten
            if any(k in text for k in ("cool-down", "cooldown", "429", "rate limit", "forbidden", "403")):
                self.log.append_text("✕ Der ClamAV-Server lässt gerade keine Downloads zu (zu viele Anfragen von "
                                     "deiner IP, z. B. über ein VPN). Später erneut versuchen oder VPN-Server wechseln.\n")
                self.refresh_status()
                return
            if any(k in text for k in ("can't connect", "connection failed", "could not resolve", "no route")):
                self.log.append_text("✕ Keine Verbindung zum ClamAV-Server – Internet/DNS prüfen.\n")
                self.refresh_status()
                return
            if rounds >= 60:
                self.log.append_text("▲ Noch keine Signaturen nach 10 Minuten – Meldungen oben prüfen.\n")
                self.refresh_status()
                return
            el = (rounds + 1) * 10
            self.badge.set("info", f"Lade Signaturen … {el // 60}:{el % 60:02d}")
            QTimer.singleShot(10000, lambda: self._watch_freshclam(rounds + 1))

        args = ["journalctl", "-u", "clamav-freshclam", "--no-pager", "-o", "cat"]
        args += ["-n", "15"] if rounds == 0 else ["--since", "-10s"]
        run_capture_async(args, cb, needs_sudo=True)

    def enable_auto(self):
        if not self.app.priv.ensure(self):
            return
        self.log.set_text("$ sudo systemctl enable --now clamav-freshclam\n")
        run_streaming(["systemctl", "enable", "--now", "clamav-freshclam"], self.log, needs_sudo=True,
                      clear_first=False, on_done=lambda rc: (self.log.append_text(f"[Exit-Code {rc}]\n"),
                                                             self.refresh_status()))

    # ---- Scan -------------------------------------------------------------

    def _target_chosen(self, idx):
        if self.target.itemData(idx) != "__custom__":
            if self.target.itemData(idx) == "/":
                self.cb_root.setChecked(True)
            return
        from PySide6.QtWidgets import QFileDialog
        d = QFileDialog.getExistingDirectory(self, "Ordner zum Scannen wählen", os.path.expanduser("~"))
        if d:
            i = self.target.findData(d)
            if i < 0:
                self.target.insertItem(self.target.count() - 1, d, d)
                i = self.target.findData(d)
            self.target.setCurrentIndex(i)
        else:
            self.target.setCurrentIndex(0)

    def start_scan(self):
        path = self.target.currentData()
        if not path or path == "__custom__":
            return
        use_root = self.cb_root.isChecked()
        if use_root and not self.app.priv.ensure(self):
            return
        excl = [f"--exclude-dir=^{re.escape(QUARANTINE_DIR)}"]
        prune = [QUARANTINE_DIR]
        if path == "/":
            excl.insert(0, "--exclude-dir=^/(proc|sys|dev|run)(/|$)")
            prune += ["/proc", "/sys", "/dev", "/run"]
        # ohne -i: clamscan meldet jede Datei → daraus Fortschritt, Tempo und „lebt es noch?“
        cmd = ["clamscan", "-r"] + excl + [path]
        self.found, self.summary = [], {}
        self._render_found()
        self.scan_target = path
        self.scan_started = time.time()
        self.sc = {"files": 0, "bytes": 0, "total_files": None, "total_bytes": None, "counting": True,
                   "last_line": time.time(), "last_file": "", "warnings": 0, "proc": None, "count_proc": None,
                   "cancelled": False, "done": False}
        self.b_scan.hide()
        self.b_stop.show()
        self.scan_box.show()
        self.progress.setText("")
        self.badge.set("info", "Scan läuft")
        self.log.set_text(f"$ {'sudo ' if use_root else ''}{' '.join(shlex.quote(c) for c in cmd)}\n"
                          "(Nur Funde, Warnungen und die Zusammenfassung werden hier angezeigt.)\n")
        sudo = ["sudo", "-n"] if use_root else []
        threading.Thread(target=self._count_worker, args=(sudo, path, prune), daemon=True).start()
        threading.Thread(target=self._scan_worker, args=(sudo + cmd,), daemon=True).start()
        self.tick_timer.start(500)
        self._tick()

    def _count_worker(self, sudo, path, prune):
        """Zählt parallel, wie viele Dateien/Bytes insgesamt anstehen (für Prozent und Restzeit)."""
        sc = self.sc
        expr = []
        for p in prune:
            expr += ["-path", p, "-prune", "-o"]
        cmd = sudo + ["find", path] + expr + ["-type", "f", "-printf", "%s\n"]
        n = size = 0
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
            sc["count_proc"] = proc
            for line in proc.stdout:
                n += 1
                try:
                    size += int(line)
                except ValueError:
                    pass
                if n % 5000 == 0:
                    sc["count_files"], sc["count_bytes"] = n, size
                if sc["cancelled"]:
                    proc.kill()
                    return
            proc.wait()
        except Exception:
            pass
        sc["total_files"], sc["total_bytes"], sc["counting"] = n, size, False

    def _scan_worker(self, cmd):
        sc = self.sc
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                    errors="replace", bufsize=1)
        except Exception as e:
            ui(lambda m=str(e): (self.log.append_text(f"error: {m}\n"), self._scan_done(2)))
            return
        sc["proc"] = proc
        in_summary = False
        for line in proc.stdout:
            line = line.rstrip("\n")
            sc["last_line"] = time.time()
            if in_summary:
                ui(lambda l=line: self._scan_line(l))
                ui(lambda l=line: self.log.append_text(l + "\n"))
                continue
            if line.startswith("----------- SCAN SUMMARY"):
                in_summary = True
                ui(lambda l=line: self.log.append_text("\n" + l + "\n"))
                continue
            if line.endswith(" FOUND"):
                sc["files"] += 1
                ui(lambda l=line: (self._scan_line(l), self.log.append_text(l + "\n")))
                continue
            p, sep, res = line.rpartition(": ")
            if sep and p.startswith("/"):
                if res in ("Symbolic link", "Excluded"):
                    continue          # wird übersprungen, zählt nicht als Datei (wie bei find -type f)
                sc["files"] += 1
                sc["last_file"] = p
                if res == "OK":
                    try:
                        sc["bytes"] += os.lstat(p).st_size
                    except OSError:
                        pass
                continue
            if line.strip():
                sc["warnings"] += 1
                if sc["warnings"] <= 40:
                    ui(lambda l=line: self.log.append_text(l + "\n"))
                elif sc["warnings"] == 41:
                    ui(lambda: self.log.append_text("… weitere Warnungen ausgeblendet\n"))
        rc = proc.wait()
        ui(lambda: self._scan_done(rc))

    def _tick(self):
        sc = getattr(self, "sc", None)
        if not sc or not self.scan_started or sc["done"]:
            return
        now = time.time()
        el = int(now - self.scan_started)
        self.scan_time.setText(f"{self.scan_target}  ·  {el // 3600:d}:{el // 60 % 60:02d}:{el % 60:02d}")
        files, byts = sc["files"], sc["bytes"]
        tf, tb = sc["total_files"], sc["total_bytes"]
        if tf:
            pct = min(99.0, files / tf * 100)
            self.scan_bar.set(pct, f"{pct:.0f} %")
            self.st_files.setText(f"{files:,} / {tf:,}".replace(",", "."))
            self.st_bytes.setText(f"{fmt_bytes(byts)} / {fmt_bytes(tb)}")
        else:
            cf = sc.get("count_files")
            self.scan_bar.set(None, "zähle Dateien …")
            self.st_files.setText(f"{files:,}".replace(",", ".") + (f" / ≥ {cf:,}".replace(",", ".") if cf else ""))
            self.st_bytes.setText(fmt_bytes(byts))
        rate = files / max(1, el)
        brate = byts / max(1, el)
        self.st_rate.setText(f"{rate:.0f} Dateien/s · {fmt_bytes(brate)}/s")
        self.st_found.setText(str(len(self.found)))
        self.st_found.setStyleSheet(f"color: {COLORS['danger']};" if self.found else "")
        if tf and rate > 0 and files < tf:
            rest = int((tf - files) / rate)
            self.scan_eta.setText(f"Restzeit ca. {rest // 3600}:{rest // 60 % 60:02d} h" if rest >= 3600
                                  else (f"Restzeit ca. {rest // 60} Min" if rest >= 60 else "Restzeit unter 1 Min"))
        else:
            self.scan_eta.setText("")
        quiet = int(now - sc["last_line"])
        last = sc["last_file"]
        proc = sc["proc"]
        if proc is not None and proc.poll() is None:
            if quiet < 60:
                self.scan_state.set("ok", "Läuft")
                self.scan_cur.setText(f"Zuletzt geprüft: {last}" if last else "Startet … Signaturen werden geladen")
            elif quiet < 600:
                self.scan_state.set("warn", f"Arbeitet – seit {quiet // 60}:{quiet % 60:02d} keine Meldung")
                self.scan_cur.setText("Wahrscheinlich eine große Datei oder ein Archiv nach: " + (last or "—"))
            else:
                self.scan_state.set("danger", f"Hängt? {quiet // 60} Min keine Meldung")
                self.scan_cur.setText("Keine Rückmeldung seit über 10 Minuten nach: " + (last or "—")
                                      + " – Abbrechen und den Ordner ausschließen oder erneut versuchen.")
        elif proc is None:
            self.scan_state.set("info", "Startet …")

    def _scan_line(self, line):
        line = line.strip()
        m = FOUND_RE.match(line)
        if m:
            self.found.append({"path": m.group(1), "threat": m.group(2), "status": "gefunden"})
            self._render_found()
            return
        if ":" in line:
            k, _, v = line.partition(":")
            k = k.strip()
            if k in ("Scanned files", "Infected files", "Scanned directories", "Time", "Data scanned"):
                self.summary[k] = v.strip()

    def stop_scan(self):
        sc = getattr(self, "sc", None)
        if not sc:
            return
        sc["cancelled"] = True
        for key in ("proc", "count_proc"):
            p = sc.get(key)
            if p is not None and p.poll() is None:
                try:
                    p.terminate()
                except Exception:
                    pass
        self.scan_state.set("info", "Wird abgebrochen …")

    def _scan_done(self, rc):
        sc = self.sc
        if sc["done"]:
            return
        sc["done"] = True
        self.tick_timer.stop()
        cp = sc.get("count_proc")
        if cp is not None and cp.poll() is None:
            cp.kill()
        el = int(time.time() - (self.scan_started or time.time()))
        self.scan_started = None
        self.b_stop.hide()
        self.b_scan.show()
        cancelled = sc["cancelled"]
        n = len(self.found)
        self.log.append_text(f"\n[Exit-Code {rc}]\n")
        dur = f"{el // 3600:d}:{el // 60 % 60:02d}:{el % 60:02d}"
        files = sc["files"]
        self.st_files.setText(f"{files:,}".replace(",", ".") + (f" / {sc['total_files']:,}".replace(",", ".")
                                                                if sc["total_files"] else ""))
        self.st_bytes.setText(fmt_bytes(sc["bytes"]))
        self.st_found.setText(str(n))
        self.scan_eta.setText("")
        if cancelled:
            self.scan_state.set("off", "Abgebrochen")
            self.badge.set("off", "Scan abgebrochen")
            self.progress.setText(f"Scan nach {dur} abgebrochen – {files:,} Dateien geprüft.".replace(",", "."))
        elif rc == 2 and not n:
            self.scan_state.set("danger", "Fehler")
            self.badge.set("danger", "Scan-Fehler")
            self.progress.setText("Scan mit Fehlern beendet – Details in der Ausgabe.")
        else:
            self.scan_bar.set(100, "100 %")
            self.scan_state.set("danger" if n else "ok", "Fertig")
            if n:
                self.badge.set("danger", f"{n} Bedrohung{'en' if n != 1 else ''} gefunden")
                self.progress.setText(f"✕ {n} infizierte Datei{'en' if n != 1 else ''} gefunden · Dauer {dur}.")
            else:
                self.badge.set("ok", "Keine Bedrohungen")
                self.progress.setText(f"● Keine Bedrohungen gefunden · {files:,} Dateien in {dur}.".replace(",", "."))
        self.scan_cur.setText("")
        if not cancelled:
            _save_json(AV_LAST, {"at": time.time(), "target": self.scan_target, "found": n,
                                 "scanned": self.summary.get("Scanned files", str(files)), "duration": el})
            self._show_last()
            if n and self.cb_quar.isChecked():
                self._quarantine([f for f in self.found if f["status"] == "gefunden"])

    def _show_last(self):
        last = _load_json(AV_LAST, None)
        if last:
            d = last.get("duration", 0)
            self.last_scan.setText(
                f"Letzter Scan: {fmt_ago(last['at'])} · {last['target']} · {last.get('scanned', '?')} Dateien · "
                f"{last['found']} Funde · Dauer {d // 60:02d}:{d % 60:02d}")
        else:
            self.last_scan.setText("Noch kein Scan durchgeführt.")

    # ---- Funde ------------------------------------------------------------

    def _render_found(self):
        self.ftable.setRowCount(len(self.found))
        danger = QColor(COLORS["danger"])
        for r, f in enumerate(self.found):
            cells = [QTableWidgetItem(f["path"]), QTableWidgetItem(f["threat"]), QTableWidgetItem(f["status"])]
            cells[0].setFont(QFont(FONTS["mono"], 10))
            if f["status"] == "gefunden":
                cells[1].setForeground(danger)
            for c, it in enumerate(cells):
                it.setToolTip(f["path"])
                self.ftable.setItem(r, c, it)
        self.ftable.setVisible(bool(self.found))
        self.f_empty.setVisible(not self.found)
        self._found_sel()

    def _sel_found(self):
        rows = sorted({i.row() for i in self.ftable.selectedIndexes()})
        return [self.found[r] for r in rows if r < len(self.found)]

    def _found_sel(self):
        sel = [f for f in self._sel_found() if f["status"] == "gefunden"]
        self.b_q.setEnabled(bool(sel))
        self.b_del.setEnabled(bool(sel))
        self.b_show.setEnabled(len(self._sel_found()) == 1)

    def _needs_root(self, path):
        d = os.path.dirname(path) or "/"
        return not (os.access(path, os.R_OK) and os.access(d, os.W_OK))

    def quarantine_selected(self):
        self._quarantine([f for f in self._sel_found() if f["status"] == "gefunden"])

    def _quarantine(self, items):
        if not items:
            return
        os.makedirs(QUARANTINE_DIR, mode=0o700, exist_ok=True)
        index = _load_json(QUARANTINE_INDEX, {})
        root_items = [f for f in items if self._needs_root(f["path"])]
        if root_items and not self.app.priv.ensure(self):
            items = [f for f in items if f not in root_items]
            root_items = []
        uid, gid = os.getuid(), os.getgid()
        for f in items:
            qname = f"{int(time.time() * 1000)}_{os.path.basename(f['path'])}"
            dest = os.path.join(QUARANTINE_DIR, qname)
            try:
                if f in root_items:
                    r = subprocess.run(["sudo", "-n", "bash", "-c",
                                        f"mv -- {shlex.quote(f['path'])} {shlex.quote(dest)} && "
                                        f"chown {uid}:{gid} {shlex.quote(dest)} && chmod 0400 {shlex.quote(dest)}"],
                                       capture_output=True, text=True)
                    if r.returncode != 0:
                        raise OSError(r.stderr.strip())
                else:
                    shutil.move(f["path"], dest)
                    os.chmod(dest, 0o400)
                index[qname] = {"orig": f["path"], "threat": f["threat"], "at": time.time(),
                                "root": f in root_items}
                f["status"] = "in Quarantäne"
                self.log.append_text(f"In Quarantäne: {f['path']}\n")
            except Exception as e:
                self.log.append_text(f"error: {f['path']} konnte nicht verschoben werden: {e}\n")
        _save_json(QUARANTINE_INDEX, index)
        self._render_found()
        self.refresh_quarantine()

    def delete_selected(self):
        items = [f for f in self._sel_found() if f["status"] == "gefunden"]
        if not items or not ask_confirm(self, "Endgültig löschen",
                                        "Diese Dateien unwiderruflich löschen?\n\n"
                                        + "\n".join(f["path"] for f in items[:15]), "Löschen", danger=True):
            return
        root_items = [f for f in items if self._needs_root(f["path"])]
        if root_items and not self.app.priv.ensure(self):
            return
        for f in items:
            try:
                if f in root_items:
                    r = subprocess.run(["sudo", "-n", "rm", "-f", "--", f["path"]], capture_output=True, text=True)
                    if r.returncode != 0:
                        raise OSError(r.stderr.strip())
                else:
                    os.remove(f["path"])
                f["status"] = "gelöscht"
                self.log.append_text(f"Gelöscht: {f['path']}\n")
            except Exception as e:
                self.log.append_text(f"error: {f['path']}: {e}\n")
        self._render_found()

    def show_folder(self):
        sel = self._sel_found()
        if sel and which("xdg-open"):
            subprocess.Popen(["xdg-open", os.path.dirname(sel[0]["path"])],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # ---- Quarantäne -------------------------------------------------------

    def refresh_quarantine(self):
        index = _load_json(QUARANTINE_INDEX, {})
        index = {k: v for k, v in index.items() if os.path.exists(os.path.join(QUARANTINE_DIR, k))}
        self.qitems = sorted(index.items(), key=lambda kv: -kv[1].get("at", 0))
        self.qtable.setRowCount(len(self.qitems))
        for r, (k, v) in enumerate(self.qitems):
            a = QTableWidgetItem(v["orig"])
            a.setFont(QFont(FONTS["mono"], 10))
            self.qtable.setItem(r, 0, a)
            self.qtable.setItem(r, 1, QTableWidgetItem(v["threat"]))
            self.qtable.setItem(r, 2, QTableWidgetItem(fmt_ago(v.get("at", 0))))
        self.qtable.setVisible(bool(self.qitems))
        self.q_empty.setVisible(not self.qitems)
        self._q_sel()

    def _sel_q(self):
        rows = sorted({i.row() for i in self.qtable.selectedIndexes()})
        return [self.qitems[r] for r in rows if r < len(self.qitems)]

    def _q_sel(self):
        sel = self._sel_q()
        self.b_restore.setEnabled(bool(sel))
        self.b_qdel.setEnabled(bool(sel))

    def restore_selected(self):
        sel = self._sel_q()
        if not sel or not ask_confirm(self, "Wiederherstellen",
                                      "Diese Dateien an ihren ursprünglichen Ort zurücklegen?\n"
                                      "Nur tun, wenn du sicher bist, dass es ein Fehlalarm ist.\n\n"
                                      + "\n".join(v["orig"] for _, v in sel[:15]), "Wiederherstellen"):
            return
        index = _load_json(QUARANTINE_INDEX, {})
        for k, v in sel:
            src = os.path.join(QUARANTINE_DIR, k)
            try:
                if v.get("root") or self._needs_root(v["orig"]):
                    if not self.app.priv.ensure(self):
                        return
                    r = subprocess.run(["sudo", "-n", "mv", "-n", "--", src, v["orig"]], capture_output=True, text=True)
                    if r.returncode != 0:
                        raise OSError(r.stderr.strip())
                else:
                    if os.path.exists(v["orig"]):
                        raise OSError("am Zielort existiert bereits eine Datei")
                    shutil.move(src, v["orig"])
                    os.chmod(v["orig"], 0o600)
                index.pop(k, None)
                self.log.append_text(f"Wiederhergestellt: {v['orig']}\n")
            except Exception as e:
                self.log.append_text(f"error: {v['orig']}: {e}\n")
        _save_json(QUARANTINE_INDEX, index)
        self.refresh_quarantine()

    def qdelete_selected(self):
        sel = self._sel_q()
        if not sel or not ask_confirm(self, "Endgültig löschen",
                                      f"{len(sel)} Datei(en) aus der Quarantäne unwiderruflich löschen?",
                                      "Löschen", danger=True):
            return
        index = _load_json(QUARANTINE_INDEX, {})
        for k, v in sel:
            try:
                p = os.path.join(QUARANTINE_DIR, k)
                os.chmod(p, 0o600)
                os.remove(p)
                index.pop(k, None)
            except Exception as e:
                self.log.append_text(f"error: {v['orig']}: {e}\n")
        _save_json(QUARANTINE_INDEX, index)
        self.refresh_quarantine()


# --------------------------------------------------------------------------
# Modul: Sicherheit (Übersicht, Mullvad VPN, Firewall, Netzwerk)
# --------------------------------------------------------------------------

def secure_boot_state():
    """True/False, oder None ohne UEFI."""
    if not os.path.isdir("/sys/firmware/efi"):
        return None
    try:
        for f in os.listdir("/sys/firmware/efi/efivars"):
            if f.startswith("SecureBoot-"):
                with open(f"/sys/firmware/efi/efivars/{f}", "rb") as fh:
                    data = fh.read()
                return bool(data) and data[-1] == 1
    except Exception:
        pass
    if which("mokutil"):
        r = subprocess.run(["mokutil", "--sb-state"], capture_output=True, text=True)
        return "enabled" in r.stdout.lower()
    return False


def luks_state():
    """(root_encrypted, [(gerät, geöffnet, eingehängt unter)])"""
    try:
        data = json.loads(subprocess.run(["lsblk", "-J", "-o", "NAME,PATH,TYPE,FSTYPE,MOUNTPOINTS"],
                                         capture_output=True, text=True, timeout=5).stdout)["blockdevices"]
    except Exception:
        return None, []
    luks, root_enc = [], False

    def walk(node, under_crypt):
        nonlocal root_enc
        mps = [m for m in (node.get("mountpoints") or []) if m]
        is_crypt = node.get("type") == "crypt"
        if node.get("fstype") == "crypto_LUKS":
            kids = node.get("children") or []
            opened = any(k.get("type") == "crypt" for k in kids)
            mounts = []
            for k in kids:
                mounts += _all_mounts(k)
            luks.append((node.get("path"), opened, ", ".join(mounts)))
        if "/" in mps and (under_crypt or is_crypt):
            root_enc = True
        for ch in node.get("children") or []:
            walk(ch, under_crypt or is_crypt)
    for d in data:
        walk(d, False)
    return root_enc, luks


def microcode_state():
    """(paketname, installiert) – (None, None) in einer VM oder bei unbekannter CPU."""
    info = _read("/proc/cpuinfo")
    if re.search(r"^flags\s*:.*\bhypervisor\b", info, re.M):
        return None, None
    pkg = "intel-ucode" if "GenuineIntel" in info else ("amd-ucode" if "AuthenticAMD" in info else None)
    if not pkg:
        return None, None
    try:
        ok = subprocess.run(["pacman", "-Q", pkg], capture_output=True, timeout=5).returncode == 0
    except Exception:
        ok = False
    return pkg, ok


def _dev_encrypted(dev):
    """True, wenn das Blockgerät (oder ein Elterngerät) ein dm-crypt-Container ist."""
    try:
        r = subprocess.run(["lsblk", "-s", "-n", "-o", "TYPE", dev], capture_output=True, text=True, timeout=5)
        return "crypt" in r.stdout.split()
    except Exception:
        return False


def swap_state():
    """[(pfad, verschlüsselt)] aller aktiven Swap-Bereiche. zram liegt im RAM und gilt als sicher."""
    res = []
    for line in _read("/proc/swaps").splitlines()[1:]:
        f = line.split()
        if len(f) < 2:
            continue
        path, kind = f[0].replace("\\040", " "), f[1]
        if "/zram" in path:
            res.append((path, True))
            continue
        dev = path
        if kind == "file":
            try:
                dev = subprocess.run(["findmnt", "-n", "-o", "SOURCE", "--target", path], capture_output=True,
                                     text=True, timeout=5).stdout.strip().split("[")[0]
            except Exception:
                dev = ""
        res.append((path, bool(dev) and _dev_encrypted(dev)))
    return res


# Kernel-Schutz: nur Werte, die im Alltag nichts kaputt machen
HARDEN_SYSCTL = {"kernel.kexec_load_disabled": "1", "kernel.sysrq": "0"}
HARDEN_FILE = "/etc/sysctl.d/90-tuxdex-hardening.conf"


def sysctl_missing():
    """Namen der HARDEN_SYSCTL-Werte, die aktuell nicht gesetzt sind."""
    return [k for k, v in HARDEN_SYSCTL.items()
            if _read("/proc/sys/" + k.replace(".", "/")).strip() != v]


def listening_ports():
    """[(proto, adresse, port, prozess)] – nur Dienste, die von außen erreichbar sind."""
    out = []
    try:
        r = subprocess.run(["ss", "-tulnpH"], capture_output=True, text=True, timeout=5)
    except Exception:
        return out
    for line in r.stdout.splitlines():
        f = line.split()
        if len(f) < 5:
            continue
        proto, local = f[0], f[4]
        addr, _, port = local.rpartition(":")
        addr = addr.strip("[]").split("%")[0]
        if addr.startswith("127.") or addr in ("::1", "localhost") or addr.startswith("fe80"):
            continue
        m = re.search(r'users:\(\("([^"]+)"', line)
        out.append((proto, addr, port, m.group(1) if m else "?"))
    seen, res = set(), []
    for o in out:
        k = (o[0], o[2])
        if k not in seen:
            seen.add(k)
            res.append(o)
    return res


def svc_active(name):
    try:
        return subprocess.run(["systemctl", "is-active", name], capture_output=True, text=True,
                              timeout=5).stdout.strip() == "active"
    except Exception:
        return False


def svc_enabled(name):
    try:
        return subprocess.run(["systemctl", "is-enabled", name], capture_output=True, text=True,
                              timeout=5).stdout.strip() == "enabled"
    except Exception:
        return False


class CheckRow(QFrame):
    """Zeile der Sicherheits-Übersicht: Status-Badge · Titel + Detail · optionaler Button."""

    def __init__(self, title):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setSpacing(16)
        self.badge = StatusBadge("off", "…")
        self.badge.setFixedWidth(150)
        lay.addWidget(self.badge)
        txt = QVBoxLayout()
        txt.setSpacing(0)
        txt.addWidget(Label(title, "PanelTitle"))
        self.detail = Label("", "Hint", wrap=True)
        txt.addWidget(self.detail)
        lay.addLayout(txt, 1)
        self.btn = Button("", "ghost")
        self.btn.hide()
        lay.addWidget(self.btn)
        self._cb = None
        self.btn.clicked.connect(lambda: self._cb and self._cb())

    def set(self, tone, short, detail, action=None, cb=None):
        self.badge.set(tone, short)
        self.detail.setText(detail)
        if action:
            self.btn.setText(action)
            self._cb = cb
            self.btn.show()
        else:
            self.btn.hide()


def _mullvad(args, timeout=15):
    try:
        r = subprocess.run(["mullvad"] + args, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr).strip()
    except Exception as e:
        return 1, str(e)


def _on(text, *keys):
    """liest on/off, allow/block, true/false aus einer mullvad-„get“-Ausgabe."""
    low = text.lower()
    for k in keys:
        m = re.search(re.escape(k.lower()) + r"[^\n:]*:\s*(\w+)", low)
        if m:
            return m.group(1) in ("on", "true", "allow", "enabled", "yes")
    return any(w in low.split() for w in ("on", "true", "allow", "enabled"))


class SecurityTab(Page):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.fw_backend = "ufw" if which("ufw") else ("firewalld" if which("firewall-cmd") else None)
        self.relays = {}       # code -> (name, {city_code: city_name})
        self.mv_loading = False

        self.badge = StatusBadge("off", "Prüfe …")
        self.lay.addLayout(page_header("Sicherheit", self.badge,
                                       Button("↻", "icon", self.refresh_all, "Alles neu prüfen")))

        # ---------- Übersicht ----------
        ov = Panel("Übersicht")
        self.rows = {}
        for key, title in (("vpn", "VPN"), ("fw", "Firewall"), ("luks", "Festplattenverschlüsselung (LUKS)"),
                           ("sb", "Secure Boot"), ("ucode", "CPU-Microcode"), ("swapenc", "Swap-Verschlüsselung"),
                           ("kernel", "Kernel-Schutz"), ("upd", "System-Updates"), ("av", "Antivirus"),
                           ("ports", "Offene Netzwerk-Ports"), ("ssh", "SSH-Server")):
            r = CheckRow(title)
            self.rows[key] = r
            ov.body.addWidget(r)
        self.lay.addWidget(ov)

        # ---------- Offene Ports ----------
        self.ports_panel = Panel("Offene Ports", [Button("↻", "icon", self.refresh_ports, "Neu prüfen")])
        self.ports_note = Label("", "Hint", wrap=True)
        self.ports_note.setTextFormat(Qt.RichText)
        self.ports_panel.body.addWidget(self.ports_note)
        self.ports_fw_btn = Button("Firewall aktivieren", "primary", lambda: self.fw_enable())
        self.ports_fw_btn.hide()
        pfb = QHBoxLayout()
        pfb.addWidget(self.ports_fw_btn)
        pfb.addStretch(1)
        self.ports_panel.body.addLayout(pfb)
        self.ports_grid = QGridLayout()
        self.ports_grid.setHorizontalSpacing(16)
        self.ports_grid.setVerticalSpacing(8)
        self.ports_panel.body.addLayout(self.ports_grid)
        self.lay.addWidget(self.ports_panel)

        # ---------- Netzwerk ----------
        net = Panel("Netzwerk & IP", [Button("Öffentliche IP prüfen", "ghost", self.check_public_ip,
                                             "Fragt am.i.mullvad.net – zeigt, wie dich Webseiten sehen")])
        self.ip_local = Label("", "Value", wrap=True)
        self.ip_local.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.ip_pub = Label("Öffentliche IP: noch nicht geprüft", "Hint", wrap=True)
        self.ip_pub.setTextFormat(Qt.RichText)
        self.ip_pub.setTextInteractionFlags(Qt.TextSelectableByMouse)
        net.body.addLayout(Field("Lokale Adressen", self.ip_local))
        net.body.addWidget(self.ip_pub)
        self.lay.addWidget(net)

        # ---------- Mullvad ----------
        self.mv_panel = Panel("Mullvad VPN")
        mv = self.mv_panel.body
        head = QHBoxLayout()
        head.setSpacing(8)
        self.mv_badge = StatusBadge("off", "Prüfe …")
        head.addWidget(self.mv_badge)
        self.mv_where = Label("", "Value", wrap=True)
        head.addWidget(self.mv_where, 1)
        self.b_connect = Button("Verbinden", "primary", lambda: self._mv_action(["connect"], wait=True))
        self.b_disconnect = Button("Trennen", "ghost", lambda: self._mv_action(["disconnect"]))
        self.b_reconnect = Button("Neuer Server", "ghost", lambda: self._mv_action(["reconnect"], wait=True))
        for b in (self.b_connect, self.b_disconnect, self.b_reconnect):
            head.addWidget(b)
        mv.addLayout(head)

        self.mv_setup = QWidget()
        su = QVBoxLayout(self.mv_setup)
        su.setContentsMargins(0, 0, 0, 0)
        su.setSpacing(8)
        self.mv_setup_text = Label("", "Muted", wrap=True)
        self.mv_setup_text.setTextFormat(Qt.RichText)
        su.addWidget(self.mv_setup_text)
        sb = QHBoxLayout()
        self.b_mv_daemon = Button("Mullvad-Dienst starten", "primary", self.mv_start_daemon)
        sb.addWidget(self.b_mv_daemon)
        sb.addStretch(1)
        su.addLayout(sb)
        mv.addWidget(self.mv_setup)

        self.mv_main = QWidget()
        mm = QVBoxLayout(self.mv_main)
        mm.setContentsMargins(0, 0, 0, 0)
        mm.setSpacing(14)
        # Konto
        acc = QHBoxLayout()
        acc.setSpacing(8)
        self.acc_info = Label("", "Value", wrap=True)
        acc.addLayout(Field("Konto", self.acc_info), 1)
        self.acc_edit = LineEdit(placeholder="16-stellige Kontonummer", mono=True)
        self.acc_edit.setMaxLength(19)
        self.acc_edit.setEchoMode(QLineEdit.Password)
        self.acc_edit.setMinimumWidth(240)
        self.b_login = Button("Anmelden", "primary", self.mv_login)
        self.b_logout = Button("Abmelden", "ghost", self.mv_logout)
        box = QVBoxLayout()
        box.addStretch(1)
        ab = QHBoxLayout()
        ab.setSpacing(8)
        for w in (self.acc_edit, self.b_login, self.b_logout):
            ab.addWidget(w)
        box.addLayout(ab)
        acc.addLayout(box)
        mm.addLayout(acc)
        # Standort
        loc = QHBoxLayout()
        loc.setSpacing(8)
        self.cb_country = QComboBox()
        self.cb_country.setMinimumWidth(220)
        self.cb_country.currentIndexChanged.connect(self._fill_cities)
        self.cb_city = QComboBox()
        self.cb_city.setMinimumWidth(200)
        loc.addLayout(Field("Land", self.cb_country))
        loc.addLayout(Field("Stadt", self.cb_city))
        lb = QVBoxLayout()
        lb.addStretch(1)
        lb.addWidget(Button("Standort übernehmen", "ghost", self.mv_set_location))
        loc.addLayout(lb)
        loc.addStretch(1)
        mm.addLayout(loc)
        # Einstellungen
        mm.addWidget(Label("EINSTELLUNGEN", "FieldLabel"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(6)
        self.o_auto = QCheckBox("Beim Systemstart automatisch verbinden")
        self.o_lock = QCheckBox("Kill-Switch: Internet nur über VPN (Lockdown-Modus)")
        self.o_lan = QCheckBox("Geräte im lokalen Netz erreichbar (Drucker, NAS …)")
        self.o_ads = QCheckBox("Werbung blockieren (DNS)")
        self.o_track = QCheckBox("Tracker blockieren (DNS)")
        self.o_mal = QCheckBox("Schadsoftware-Seiten blockieren (DNS)")
        for i, cb in enumerate((self.o_auto, self.o_lock, self.o_lan, self.o_ads, self.o_track, self.o_mal)):
            grid.addWidget(cb, i % 3, i // 3)
        mm.addLayout(grid)
        self.o_auto.clicked.connect(lambda v: self._mv_action(["auto-connect", "set", "on" if v else "off"]))
        self.o_lock.clicked.connect(self._toggle_lockdown)
        self.o_lan.clicked.connect(lambda v: self._mv_action(["lan", "set", "allow" if v else "block"]))
        for cb in (self.o_ads, self.o_track, self.o_mal):
            cb.clicked.connect(lambda _=False: self._mv_dns())
        mm.addWidget(Label("Mullvad-Befehle brauchen kein Passwort – der Mullvad-Dienst erledigt das. "
                           "Mit Kill-Switch gibt es ohne VPN-Verbindung kein Internet.", "Hint", wrap=True))
        mv.addWidget(self.mv_main)
        self.lay.addWidget(self.mv_panel)

        # ---------- Firewall ----------
        fw = Panel("Firewall")
        fh = QHBoxLayout()
        fh.setSpacing(8)
        self.fw_badge = StatusBadge("off", "…")
        fh.addWidget(self.fw_badge)
        self.fw_label = Label("", "Value")
        fh.addWidget(self.fw_label, 1)
        self.b_fw_on = Button("Aktivieren", "primary", self.fw_enable)
        self.b_fw_status = Button("Regeln anzeigen", "ghost", self.fw_status)
        self.b_fw_off = Button("Deaktivieren", "danger", self.fw_disable)
        self.b_fw_install = Button("ufw installieren", "primary", self.fw_install)
        for b in (self.b_fw_install, self.b_fw_on, self.b_fw_status, self.b_fw_off):
            fh.addWidget(b)
        fw.body.addLayout(fh)
        self.fw_rules = QWidget()
        rl = QVBoxLayout(self.fw_rules)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)
        self.rule_table = QTableWidget(0, 2)
        self.rule_table.setHorizontalHeaderLabels(["NR.", "REGEL"])
        self.rule_table.verticalHeader().setVisible(False)
        self.rule_table.setShowGrid(False)
        self.rule_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.rule_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.rule_table.setColumnWidth(0, 60)
        self.rule_table.horizontalHeader().setStretchLastSection(True)
        self.rule_table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.rule_table.setMinimumHeight(140)
        rl.addWidget(self.rule_table)
        add = QHBoxLayout()
        add.setSpacing(8)
        self.r_port = LineEdit(placeholder="z. B. 22 oder 8000:8100", mono=True)
        self.r_proto = QComboBox()
        self.r_proto.addItems(["tcp", "udp", "tcp+udp"])
        self.r_proto.setMinimumHeight(38)
        self.r_act = QComboBox()
        self.r_act.addItems(["erlauben", "sperren"])
        self.r_act.setMinimumHeight(38)
        add.addLayout(Field("Port", self.r_port), 1)
        add.addLayout(Field("Protokoll", self.r_proto))
        add.addLayout(Field("Aktion", self.r_act))
        ab2 = QVBoxLayout()
        ab2.addStretch(1)
        h2 = QHBoxLayout()
        h2.setSpacing(8)
        h2.addWidget(Button("Regel hinzufügen", "ghost", self.fw_add_rule))
        h2.addWidget(Button("Ausgewählte löschen", "danger", self.fw_del_rule))
        ab2.addLayout(h2)
        add.addLayout(ab2)
        rl.addLayout(add)
        fw.body.addWidget(self.fw_rules)
        self.fw_rules.setVisible(self.fw_backend == "ufw")
        self.lay.addWidget(fw)

        out = Panel("Ausgabe")
        self.log = LogView(150)
        out.body.addWidget(self.log)
        self.lay.addWidget(out)

        QTimer.singleShot(400, self.refresh_all)
        self._vpn_timer = QTimer(self)
        self._vpn_timer.timeout.connect(self._poll_vpn)
        self._vpn_timer.start(10000)

    # ======================================================================
    # Übersicht
    # ======================================================================

    def refresh_all(self):
        self.badge.set("info", "Prüfe …")

        def worker():
            r = {}
            # VPN
            r["mullvad"] = which("mullvad")
            r["mv_status"] = _mullvad(["status"])[1] if r["mullvad"] else ""
            ifaces, gw, dns = net_interfaces()
            r["ifaces"], r["gw"], r["dns"] = ifaces, gw, dns
            r["vpn"] = vpn_state(ifaces)
            # Firewall
            r["fw"] = svc_active("ufw") or svc_active("firewalld") or svc_active("nftables") \
                or svc_active("iptables")
            r["fw_name"] = next((n for n in ("ufw", "firewalld", "nftables", "iptables") if svc_active(n)), None)
            r["fw_enabled"] = any(svc_enabled(n) for n in ("ufw", "firewalld", "nftables", "iptables"))
            r["luks"] = luks_state()
            r["sb"] = secure_boot_state()
            r["ucode"] = microcode_state()
            r["swap"] = swap_state()
            r["sysctl"] = sysctl_missing()
            # Updates
            last = None
            try:
                with open("/var/log/pacman.log", errors="ignore") as f:
                    m = re.findall(r"\[([^\]]+)\][^\n]*starting full system upgrade", f.read())
                if m:
                    ts = m[-1].replace("T", " ")[:16]
                    last = datetime.strptime(ts, "%Y-%m-%d %H:%M")
            except Exception:
                pass
            r["last_upgrade"] = last
            r["pending"] = _load_json(UPDATE_CACHE, {}).get("updates", [])
            # Antivirus
            if which("clamscan"):
                ver = subprocess.run(["clamscan", "--version"], capture_output=True, text=True).stdout
                parts = ver.strip().split("/")
                try:
                    r["av"] = (datetime.now() - parse_c_date(parts[2])).days
                except Exception:
                    r["av"] = -1
            else:
                r["av"] = None
            r["ports"] = listening_ports()
            r["ssh"] = svc_active("sshd")
            root_login = re.search(r"^\s*PermitRootLogin\s+(\S+)", _read("/etc/ssh/sshd_config"), re.M)
            r["ssh_root"] = root_login.group(1) if root_login else None
            r["ssh_pw"] = re.search(r"^\s*PasswordAuthentication\s+no", _read("/etc/ssh/sshd_config"), re.M) is None
            ui(lambda: self._show(r))
        threading.Thread(target=worker, daemon=True).start()
        self.mv_refresh()
        self.fw_refresh()
        self.refresh_ports()

    def _goto(self, widget):
        QTimer.singleShot(0, lambda: self.ensureWidgetVisible(widget, 0, 40))

    def _show(self, r):
        warn = 0
        # VPN
        warn += self._show_vpn(r["vpn"])
        # Firewall
        if r["fw"]:
            self.rows["fw"].set("ok", "Aktiv", f"{r['fw_name']} läuft"
                                + ("" if r["fw_enabled"] else " – startet aber nicht automatisch."))
        else:
            warn += 1
            self.rows["fw"].set("danger", "Aus", "Keine Firewall aktiv. Eingehende Verbindungen werden nicht gefiltert.",
                                "Aktivieren" if self.fw_backend else "ufw installieren",
                                self.fw_enable if self.fw_backend else self.fw_install)
        # LUKS
        root_enc, luks = r["luks"]
        others = ", ".join(f"{d} ({'offen' if o else 'gesperrt'})" for d, o, m in luks) or "keine"
        if root_enc:
            self.rows["luks"].set("ok", "Verschlüsselt", f"Die Systempartition liegt auf LUKS. LUKS-Geräte: {others}")
        elif root_enc is None:
            self.rows["luks"].set("off", "Unbekannt", "lsblk konnte nicht gelesen werden.")
        else:
            warn += 1
            self.rows["luks"].set("warn", "Nicht verschlüsselt",
                                  "Die Systempartition ist unverschlüsselt – bei Diebstahl sind alle Daten lesbar. "
                                  "Nachträglich nur über Neuinstallation/Backup sinnvoll. LUKS-Geräte: " + others)
        # Secure Boot
        sb = r["sb"]
        if sb is None:
            self.rows["sb"].set("off", "Kein UEFI", "Das System startet im Legacy-BIOS-Modus.")
        elif sb:
            self.rows["sb"].set("ok", "Aktiv", "Nur signierte Bootloader/Kernel werden gestartet.")
        else:
            self.rows["sb"].set("off", "Aus", "Optional: mit sbctl eigene Schlüssel einrichten "
                                              "(schützt vor manipulierten Bootloadern).")
        # Microcode
        pkg, ok = r["ucode"]
        if pkg is None:
            self.rows["ucode"].set("off", "Nicht nötig", "Virtuelle Maschine oder unbekannte CPU – der Host lädt "
                                                         "den Microcode.")
        elif ok:
            self.rows["ucode"].set("ok", "Installiert", f"{pkg} schließt CPU-Sicherheitslücken (z. B. Spectre).")
        else:
            warn += 1
            self.rows["ucode"].set("warn", "Fehlt", f"{pkg} fehlt – bekannte CPU-Sicherheitslücken bleiben offen. "
                                   "Wirkt nach dem nächsten Neustart.", "Installieren", self.install_ucode)
        # Swap
        plain = [p for p, enc in r["swap"] if not enc]
        if not r["swap"]:
            self.rows["swapenc"].set("ok", "Kein Swap", "Es wird kein Swap genutzt.")
        elif not plain:
            self.rows["swapenc"].set("ok", "Geschützt", "Swap liegt verschlüsselt oder im RAM (zram): "
                                     + ", ".join(p for p, _ in r["swap"]))
        else:
            warn += 1
            self.rows["swapenc"].set("warn", "Unverschlüsselt",
                                     f"{', '.join(plain)} ist unverschlüsselt – Passwörter und Schlüssel aus dem "
                                     "RAM können dort lesbar auf der Platte landen. Abhilfe: Swap-Partition "
                                     "entfernen und ein Swapfile auf der verschlüsselten Systempartition anlegen.",
                                     "Zum Swap", lambda: self.app.select([m[0] for m in MODULES].index("swap")))
        # Kernel-Schutz
        miss = r["sysctl"]
        if not miss:
            self.rows["kernel"].set("ok", "Aktiv", "Kernel-Austausch im laufenden Betrieb (kexec) und "
                                                   "SysRq-Tastenkürzel sind gesperrt.")
        else:
            warn += 1
            self.rows["kernel"].set("warn", "Offen", "Nicht gesetzt: " + ", ".join(
                f"{k}={HARDEN_SYSCTL[k]}" for k in miss) + ". Sperrt den Kernel-Austausch im laufenden Betrieb "
                "(kexec) und SysRq-Tastenkürzel – im Alltag ohne Nachteile.", "Aktivieren", self.harden_kernel)
        # Updates
        last = r["last_upgrade"]
        imp = [u for u in r["pending"] if u.get("kind")]
        if last is None:
            self.rows["upd"].set("off", "Unbekannt", "Kein vollständiges Update im pacman-Log gefunden.")
        else:
            days = (datetime.now() - last).days
            txt = f"Letztes vollständiges Update vor {days} Tag{'en' if days != 1 else ''}"
            if r["pending"]:
                txt += f" · {len(r['pending'])} Updates offen" + (f", {len(imp)} wichtig" if imp else "")
            goto_upd = lambda: self.app.select([m[0] for m in MODULES].index("update"))
            if days > 14 or imp:
                warn += 1
                self.rows["upd"].set("warn", "Veraltet" if days > 14 else "Wichtige offen", txt + ".",
                                     "Zu den Updates", goto_upd)
            else:
                self.rows["upd"].set("ok", "Aktuell", txt + ".")
        # Antivirus
        av = r["av"]
        goto_av = lambda: self.app.select([m[0] for m in MODULES].index("antivirus"))
        if av is None:
            self.rows["av"].set("off", "Nicht installiert", "ClamAV ist optional – Tuxdex funktioniert auch ohne.")
        elif av < 0:
            self.rows["av"].set("warn", "Keine Signaturen", "ClamAV ist installiert, aber ohne Virensignaturen.",
                                "Einrichten", goto_av)
        elif av > 3:
            self.rows["av"].set("warn", f"{av} Tage alt", "Die Virensignaturen sind veraltet.", "Aktualisieren", goto_av)
        else:
            self.rows["av"].set("ok", "Aktuell", "ClamAV mit aktuellen Signaturen.")
        # Ports
        ports = r["ports"]
        if not ports:
            self.rows["ports"].set("ok", "Keine offen", "Kein Dienst wartet auf Verbindungen von außen.")
        else:
            lst = ", ".join(f"{p[2]}/{p[0]} ({p[3]})" for p in ports[:8]) + (" …" if len(ports) > 8 else "")
            tone = "info" if r["fw"] else "warn"
            if not r["fw"]:
                warn += 1
            self.rows["ports"].set(tone, f"{len(ports)} offen", f"{lst}. "
                                   + ("Die Firewall filtert diese Ports." if r["fw"]
                                      else "Ohne Firewall sind sie im Netz erreichbar."),
                                   "Verwalten", lambda: self._goto(self.ports_panel))
        # SSH
        if not r["ssh"]:
            self.rows["ssh"].set("ok", "Aus", "Kein Fernzugriff per SSH möglich.")
        else:
            risky = (r["ssh_root"] or "").lower() in ("yes",) or r["ssh_pw"]
            if risky:
                warn += 1
            self.rows["ssh"].set("warn" if risky else "info", "Läuft",
                                 "SSH-Server aktiv"
                                 + (" · root-Anmeldung erlaubt" if (r["ssh_root"] or "").lower() == "yes" else "")
                                 + (" · Passwort-Anmeldung erlaubt (Schlüssel sind sicherer)" if r["ssh_pw"] else ""),
                                 "Dienst stoppen", self.stop_ssh)
        # Netzwerk
        loc = []
        for i in r["ifaces"]:
            if i["ipv4"] or i["ipv6"]:
                loc.append(f"{i['kind']} {i['name']}: " + ", ".join(i["ipv4"] + i["ipv6"][:1]))
        self.ip_local.setText("\n".join(loc) + f"\nGateway: {r['gw'] or '—'}  ·  DNS: {', '.join(r['dns']) or '—'}")

        self.badge.set("ok" if warn == 0 else ("warn" if warn <= 2 else "danger"),
                       "Alles in Ordnung" if warn == 0 else f"{warn} Hinweis{'e' if warn != 1 else ''}")

    def _show_vpn(self, v):
        """Setzt die VPN-Zeile; gibt 1 zurück, wenn ein Hinweis gezählt werden soll."""
        mv = v.get("mullvad")
        mv_first = mv.splitlines()[0].strip().lower() if mv else ""
        ts = v.get("tailscale")
        route = v.get("route_dev") or "—"
        if mv_first.startswith("connected"):
            self.rows["vpn"].set("ok", "Aktiv", "Mullvad ist verbunden. " + self._mv_location(mv))
            return 0
        if ts and ts["running"] and ts["exit_node"]:
            self.rows["vpn"].set("ok", "Aktiv", f"Tailscale ist verbunden – dein Internetverkehr läuft über den "
                                 f"Exit-Node „{ts['exit_node']}“.")
            return 0
        if v["others"]:
            full = route in v["others"]
            self.rows["vpn"].set("ok" if full else "info", "Aktiv" if full else "Verbunden",
                                 f"VPN-Verbindung aktiv: {', '.join(v['others'])}. " +
                                 ("Der Internetverkehr läuft darüber." if full else
                                  f"Der Internetverkehr läuft aber direkt über {route} (Split-Tunnel)."))
            return 0
        if ts and ts["running"]:
            self.rows["vpn"].set("info", "Tailscale an", "Tailscale ist verbunden (privates Netz zwischen deinen "
                                 "Geräten). Ohne Exit-Node läuft der Internetverkehr direkt, nicht über ein VPN.")
            return 0
        extra = ""
        if ts is not None and not ts["running"]:
            extra = f" Tailscale ist {TS_STATES.get(ts['state'], ts['state'])}."
        if mv is not None:
            self.rows["vpn"].set("warn", "Aus", "Mullvad ist nicht verbunden – Anbieter und Webseiten sehen "
                                 "deine echte IP." + extra, "Verbinden",
                                 lambda: self._mv_action(["connect"], wait=True))
            return 1
        self.rows["vpn"].set("off", "Kein VPN", "Es ist kein VPN aktiv." + extra +
                             " Optional – Tuxdex funktioniert auch ohne VPN.")
        return 0

    def _poll_vpn(self):
        """Alle 10 s: VPN-Zeile auffrischen (z. B. nach „tailscale down“), solange der Tab sichtbar ist."""
        if not self.isVisible() or getattr(self, "_vpn_busy", False):
            return
        self._vpn_busy = True

        def worker():
            v = vpn_state()
            ui(lambda: (self._show_vpn(v), setattr(self, "_vpn_busy", False)))
        threading.Thread(target=worker, daemon=True).start()

    def stop_ssh(self):
        if not ask_confirm(self, "SSH stoppen", "SSH-Server stoppen und nicht mehr automatisch starten?\n"
                           "Laufende Fernverbindungen werden getrennt.", "Stoppen", danger=True):
            return
        self._root(["systemctl", "disable", "--now", "sshd"])

    def install_ucode(self):
        pkg, ok = microcode_state()
        if not pkg or ok:
            return
        self._root(["pacman", "-S", "--needed", pkg], interactive=True)

    def harden_kernel(self):
        if not ask_confirm(self, "Kernel-Schutz", "Kernel-Austausch im laufenden Betrieb (kexec) und "
                           "SysRq-Tastenkürzel sperren?\n\nWird in " + HARDEN_FILE + " gespeichert und gilt "
                           "sofort und nach jedem Neustart.", "Aktivieren"):
            return
        body = "".join(f"{k} = {v}\n" for k, v in HARDEN_SYSCTL.items())
        script = (f"printf %s {shlex.quote('# Tuxdex: Kernel-Schutz' + chr(10) + body)} > {HARDEN_FILE} && "
                  f"sysctl -p {HARDEN_FILE}")
        self._root(["sh", "-c", script])

    def check_public_ip(self):
        self.ip_pub.setText("Öffentliche IP wird geprüft …")

        def worker():
            try:
                d = public_ip_info()
                txt = (f"Öffentliche IP: <b>{d.get('ip', '?')}</b> · {d.get('city') or ''} {d.get('country') or ''}"
                       f" · {d.get('organization') or ''}<br>"
                       + (f'<span style="color:{COLORS["ok"]}">● Dein Verkehr läuft über Mullvad '
                          f'({d.get("mullvad_exit_ip_hostname", "")}).</span>' if d.get("mullvad_exit_ip") else
                          f'<span style="color:{COLORS["warn"]}">▲ Nicht über Mullvad – Webseiten sehen diese '
                          f'Adresse.</span>'))
            except Exception as e:
                txt = f"Öffentliche IP konnte nicht ermittelt werden ({e})."
            ui(lambda: self.ip_pub.setText(txt))
        threading.Thread(target=worker, daemon=True).start()

    def _root(self, cmd, then=None, interactive=False):
        if not self.app.priv.ensure(self):
            return
        self.log.set_text(f"$ sudo {' '.join(shlex.quote(c) for c in cmd)}\n")

        def done(rc):
            self.log.append_text(f"\n[Exit-Code {rc}]\n")
            if then:
                then(rc)
            self.refresh_all()
        run_streaming(cmd, self.log, needs_sudo=True, clear_first=False, on_done=done, interactive=interactive)


    # ======================================================================
    # Offene Ports – je Port ein Knopf „Sperren“ / „Freigeben“
    # ======================================================================

    PORT_NAMES = {"22": "SSH", "80": "Webserver", "443": "Webserver (HTTPS)", "631": "Drucken (CUPS)",
                  "5353": "Geräteerkennung (mDNS)", "1716": "KDE Connect", "5900": "Bildschirmfreigabe (VNC)",
                  "3389": "Remotedesktop", "139": "Dateifreigabe (Samba)", "445": "Dateifreigabe (Samba)",
                  "8080": "Webserver", "3000": "Entwicklungsserver", "5432": "PostgreSQL", "3306": "MySQL",
                  "6379": "Redis", "27017": "MongoDB", "51820": "WireGuard", "53": "DNS", "68": "DHCP",
                  "546": "DHCPv6", "5355": "Namensauflösung (LLMNR)", "27036": "Steam", "57621": "Spotify"}

    def refresh_ports(self):
        backend = "ufw" if svc_active("ufw") else ("firewalld" if svc_active("firewalld") else None)
        authed = self.app.priv.is_authenticated_nonblocking()

        def worker():
            ports = listening_ports()
            rules = None
            if backend == "ufw" and authed:
                r = subprocess.run(["sudo", "-n", "ufw", "status"], capture_output=True, text=True)
                rules = {}
                for line in r.stdout.splitlines():
                    m = re.match(r"^(\d+)(?:/(tcp|udp))?\s+(?:\(v6\)\s+)?(ALLOW|DENY|REJECT|LIMIT)", line.strip())
                    if m:
                        for pr in ([m.group(2)] if m.group(2) else ["tcp", "udp"]):
                            rules[(m.group(1), pr)] = m.group(3) in ("ALLOW", "LIMIT")
                default_allow = "default: allow (incoming)" in subprocess.run(
                    ["sudo", "-n", "ufw", "status", "verbose"], capture_output=True, text=True).stdout.lower()
                rules["__default__"] = default_allow
            elif backend == "firewalld" and authed:
                r = subprocess.run(["sudo", "-n", "firewall-cmd", "--list-ports"], capture_output=True, text=True)
                rules = {}
                for tok in r.stdout.split():
                    port, _, pr = tok.partition("/")
                    rules[(port, pr)] = True
                rules["__default__"] = False
            ui(lambda: self._show_ports(ports, backend, rules))
        threading.Thread(target=worker, daemon=True).start()

    def _show_ports(self, ports, backend, rules):
        TaskTab._clear(self.ports_grid)
        self.ports_fw_btn.setVisible(bool(ports) and backend is None)
        if not ports:
            self.ports_note.setText("Kein Programm wartet auf Verbindungen von außen – nichts zu tun.")
            return
        if backend is None:
            self.ports_note.setText(f'<span style="color:{COLORS["warn"]}">▲ Ohne aktive Firewall sind alle '
                                    f'Ports unten aus dem Netz erreichbar.</span> Nach dem Aktivieren sind sie '
                                    f'gesperrt und du kannst jeden einzeln per Knopf freigeben.')
        elif rules is None:
            self.ports_note.setText("Oben rechts <b>anmelden</b>, um zu sehen, welche Ports die Firewall "
                                    "durchlässt – dann kannst du sie per Knopf sperren oder freigeben.")
        else:
            self.ports_note.setText("<b>Freigegeben</b> = aus dem Netz erreichbar. <b>Gesperrt</b> = die Firewall "
                                    "blockt Verbindungen von außen; das Programm läuft trotzdem weiter.")
        for c, h in enumerate(("PORT", "PROGRAMM", "WOFÜR", "STATUS", "")):
            self.ports_grid.addWidget(Label(h, "FieldLabel"), 0, c)
        for i, (proto, addr, port, proc) in enumerate(ports, start=1):
            pr = "udp" if proto.startswith("udp") else "tcp"
            self.ports_grid.addWidget(Label(f"{port}/{pr}", "Value"), i, 0)
            self.ports_grid.addWidget(Label(proc if proc != "?" else "unbekannt", "Muted"), i, 1)
            self.ports_grid.addWidget(Label(self.PORT_NAMES.get(port, "—"), "Muted"), i, 2)
            if backend is None:
                open_ = True          # ohne Firewall ist jeder dieser Ports erreichbar
            elif rules is None:
                open_ = None
            else:
                open_ = rules.get((port, pr), rules.get("__default__", False))
            badge = StatusBadge("off", "unbekannt") if open_ is None else \
                (StatusBadge("warn", "Erreichbar" if backend is None else "Freigegeben") if open_
                 else StatusBadge("ok", "Gesperrt"))
            self.ports_grid.addWidget(badge, i, 3)
            if backend and rules is not None:
                b = Button("Sperren" if open_ else "Freigeben", "ghost" if open_ else "primary",
                           lambda _=False, p=port, q=pr, o=open_, n=proc: self.toggle_port(backend, p, q, not o, n))
            elif backend:
                b = Button("Anmelden", "ghost", lambda: (self.app.priv.ensure(self) and self.refresh_ports()))
            else:
                b = None
            if b:
                self.ports_grid.addWidget(b, i, 4)
        self.ports_grid.setColumnStretch(2, 1)

    def toggle_port(self, backend, port, proto, allow, proc):
        what = f"Port {port}/{proto} ({proc})"
        if allow and not ask_confirm(self, "Port freigeben",
                                     f"{what} für Verbindungen aus dem Netz freigeben?\n\n"
                                     "Nur tun, wenn andere Geräte diesen Dienst erreichen sollen.", "Freigeben"):
            return
        if not self.app.priv.ensure(self):
            return
        spec = f"{port}/{proto}"
        if backend == "ufw":
            old, new = ("deny", "allow") if allow else ("allow", "deny")
            steps = [{"cmd": ["ufw", "--force", "delete", old, spec], "needs_sudo": True,
                      "label": f"ufw delete {old} {spec}"},
                     {"cmd": ["ufw", new, spec], "needs_sudo": True, "label": f"ufw {new} {spec}"}]
        else:
            act = "--add-port" if allow else "--remove-port"
            steps = [{"cmd": ["firewall-cmd", "--permanent", f"{act}={spec}"], "needs_sudo": True,
                      "label": f"firewall-cmd --permanent {act}={spec}"},
                     {"cmd": ["firewall-cmd", "--reload"], "needs_sudo": True, "label": "firewall-cmd --reload"}]
        self.app.set_status(f"{what} wird {'freigegeben' if allow else 'gesperrt'} …")
        run_sequence(steps, self.log, on_all_done=lambda: (
            self.app.set_status(f"{what} {'freigegeben' if allow else 'gesperrt'}."), self.refresh_ports()))

    # ======================================================================
    # Mullvad
    # ======================================================================

    @staticmethod
    def _mv_location(status):
        m = re.search(r"Visible location:\s*(.+?)(?:\. IPv4|\n|$)", status) or \
            re.search(r"in (.+?)(?:\n|$)", status)
        relay = re.search(r"Relay:\s*(\S+)", status) or re.search(r"Connected to (\S+)", status)
        parts = []
        if m:
            parts.append(m.group(1).strip())
        if relay:
            parts.append(f"Server {relay.group(1)}")
        return " · ".join(parts)

    def mv_refresh(self):
        if self.mv_loading:
            return
        self.mv_loading = True

        def worker():
            r = {"installed": which("mullvad")}
            if r["installed"]:
                rc, st = _mullvad(["status"])
                r["daemon"] = rc == 0 and "not running" not in st.lower() and "failed to connect" not in st.lower()
                r["status"] = st
                if r["daemon"]:
                    r["account"] = _mullvad(["account", "get"])[1]
                    r["auto"] = _mullvad(["auto-connect", "get"])[1]
                    r["lock"] = _mullvad(["lockdown-mode", "get"])[1]
                    r["lan"] = _mullvad(["lan", "get"])[1]
                    r["dns"] = _mullvad(["dns", "get"])[1]
                    if not self.relays:
                        r["relays"] = _mullvad(["relay", "list"], timeout=20)[1]
                    r["relay_get"] = _mullvad(["relay", "get"])[1]
            ui(lambda: self._mv_show(r))
        threading.Thread(target=worker, daemon=True).start()

    def _mv_show(self, r):
        self.mv_loading = False
        installed = r["installed"]
        daemon = r.get("daemon", False)
        self.mv_setup.setVisible(not (installed and daemon))
        self.mv_main.setVisible(installed and daemon)
        for b in (self.b_connect, self.b_disconnect, self.b_reconnect):
            b.setVisible(installed and daemon)
        if not installed:
            self.mv_badge.set("off", "Nicht installiert")
            self.mv_where.setText("")
            self.mv_setup_text.setText("Mullvad VPN ist nicht installiert. Tuxdex funktioniert auch ohne. Sobald "
                                       "Mullvad auf dem System vorhanden ist, lässt es sich hier bedienen.")
            self.b_mv_daemon.hide()
            return
        if not daemon:
            self.mv_badge.set("warn", "Dienst aus")
            self.mv_where.setText("")
            self.mv_setup_text.setText("Mullvad ist installiert, aber der Hintergrunddienst <b>mullvad-daemon</b> "
                                       "läuft nicht.")
            self.b_mv_daemon.show()
            return
        st = r.get("status", "")
        first = st.splitlines()[0].strip().lower() if st else ""
        if first.startswith("connected"):
            self.mv_badge.set("ok", "Verbunden")
            self.b_connect.hide()
            self.b_disconnect.show()
            self.b_reconnect.show()
        elif first.startswith("connecting"):
            self.mv_badge.set("info", "Verbinde …")
        elif first.startswith("blocked") or "block" in first:
            self.mv_badge.set("warn", "Blockiert")
        else:
            self.mv_badge.set("off", "Getrennt")
            self.b_disconnect.hide()
            self.b_reconnect.hide()
            self.b_connect.show()
        self.mv_where.setText(self._mv_location(st) or ("Kill-Switch aktiv – ohne VPN kein Internet"
                                                         if _on(r.get("lock", ""), "block") and
                                                         not first.startswith("connected") else ""))
        # Konto
        acc = r.get("account", "")
        logged_in = bool(re.search(r"account(?: number)?:\s*\d", acc, re.I)) or "expires" in acc.lower()
        if logged_in:
            num = re.search(r"(\d{4})\s*$", re.search(r"account(?: number)?:\s*([\d ]+)", acc, re.I).group(1)) \
                if re.search(r"account(?: number)?:\s*([\d ]+)", acc, re.I) else None
            exp = re.search(r"Expires at\s*:\s*(.+)", acc, re.I)
            dev = re.search(r"Device name\s*:\s*(.+)", acc, re.I)
            exp_txt = exp.group(1).strip() if exp else "?"
            try:
                exp_dt = datetime.fromisoformat(exp_txt.replace(" UTC", "").replace("Z", "")[:19])
                days = (exp_dt - datetime.now()).days
                exp_txt = exp_dt.strftime("%d.%m.%Y") + (f"  (noch {days} Tage)" if days >= 0 else "  (abgelaufen)")
            except Exception:
                pass
            self.acc_info.setText(f"•••• {num.group(1) if num else ''}  ·  gültig bis {exp_txt}"
                                  + (f"  ·  Gerät „{dev.group(1).strip()}“" if dev else ""))
        else:
            self.acc_info.setText("Nicht angemeldet")
        for w in (self.acc_edit, self.b_login):
            w.setVisible(not logged_in)
        self.b_logout.setVisible(logged_in)
        # Einstellungen
        self.o_auto.setChecked(_on(r.get("auto", ""), "autoconnect", "auto-connect"))
        self.o_lock.setChecked(_on(r.get("lock", ""), "block traffic", "lockdown"))
        self.o_lan.setChecked(_on(r.get("lan", ""), "local network sharing", "lan"))
        dns = r.get("dns", "")
        self.o_ads.setChecked(_on(dns, "block ads"))
        self.o_track.setChecked(_on(dns, "block trackers"))
        self.o_mal.setChecked(_on(dns, "block malware"))
        # Standorte
        if r.get("relays"):
            self._parse_relays(r["relays"])
        cur = r.get("relay_get", "")
        m = re.search(r"country (\w\w)\b", cur) or re.search(r"\(([a-z]{2})\)", cur)
        if m and not getattr(self, "_loc_set", False):
            i = self.cb_country.findData(m.group(1))
            if i >= 0:
                self.cb_country.setCurrentIndex(i)
            self._loc_set = True

    def _parse_relays(self, text):
        self.relays = {}
        country = None
        for line in text.splitlines():
            if not line.strip():
                continue
            if not line.startswith(("\t", " ")):
                m = re.match(r"^(.+?) \((\w+)\)", line)
                if m:
                    country = m.group(2)
                    self.relays[country] = (m.group(1), {})
            elif country and not line.startswith(("\t\t", "        ")):
                m = re.match(r"^\s+(.+?) \((\w+)\)", line)
                if m:
                    self.relays[country][1][m.group(2)] = m.group(1)
        self.cb_country.blockSignals(True)
        self.cb_country.clear()
        self.cb_country.addItem("Beliebig (schnellster)", "any")
        for code, (name, _) in sorted(self.relays.items(), key=lambda kv: kv[1][0]):
            self.cb_country.addItem(name, code)
        self.cb_country.blockSignals(False)
        self._fill_cities()

    def _fill_cities(self, *_):
        code = self.cb_country.currentData()
        self.cb_city.clear()
        self.cb_city.addItem("Beliebige Stadt", None)
        if code in self.relays:
            for c, name in sorted(self.relays[code][1].items(), key=lambda kv: kv[1]):
                self.cb_city.addItem(name, c)
        self.cb_city.setEnabled(code in self.relays)

    def _mv_action(self, args, wait=False, then=None):
        self.log.set_text(f"$ mullvad {' '.join(args)}\n")

        def done(rc):
            self.log.append_text(f"[Exit-Code {rc}]\n")
            if then:
                then(rc)
            if wait:
                self._poll_mv(0)
            else:
                self.mv_refresh()
                QTimer.singleShot(800, self.refresh_all)
        run_streaming(["mullvad"] + args, self.log, clear_first=False, on_done=done)

    def _poll_mv(self, n):
        """nach dem Verbinden ein paar Sekunden den Status verfolgen, dann IP prüfen"""
        def cb():
            rc, st = _mullvad(["status"])
            first = st.splitlines()[0].lower() if st else ""
            if first.startswith("connecting") and n < 15:
                QTimer.singleShot(1000, lambda: self._poll_mv(n + 1))
            else:
                self.refresh_all()
                QTimer.singleShot(1500, self.check_public_ip)
        QTimer.singleShot(700, cb)

    def _toggle_lockdown(self, on):
        if on and not ask_confirm(self, "Kill-Switch aktivieren",
                                  "Mit dem Kill-Switch gibt es nur noch Internet, solange das VPN verbunden ist – "
                                  "auch wenn die App geschlossen ist.\n\nAktivieren?", "Aktivieren"):
            self.o_lock.setChecked(False)
            return
        self._mv_action(["lockdown-mode", "set", "on" if on else "off"])

    def _mv_dns(self):
        args = ["dns", "set", "default"]
        if self.o_ads.isChecked():
            args.append("--block-ads")
        if self.o_track.isChecked():
            args.append("--block-trackers")
        if self.o_mal.isChecked():
            args.append("--block-malware")
        self._mv_action(args)

    def mv_set_location(self):
        c = self.cb_country.currentData()
        city = self.cb_city.currentData()
        if c == "any" or c is None:
            args = ["relay", "set", "location", "any"]
        else:
            args = ["relay", "set", "location", c] + ([city] if city else [])
        connected = self.mv_badge.text().endswith("Verbunden")
        self._mv_action(args, then=(lambda rc: rc == 0 and connected and
                                    self._mv_action(["reconnect"], wait=True)))

    def mv_login(self):
        num = re.sub(r"\D", "", self.acc_edit.text())
        if len(num) != 16:
            show_warning(self, "Kontonummer", "Die Mullvad-Kontonummer hat 16 Ziffern.")
            return
        self.acc_edit.clear()
        self.log.set_text("$ mullvad account login ****\n")
        run_streaming(["mullvad", "account", "login", num], None, clear_first=False,
                      on_done=lambda rc: (self.log.append_text(
                          "Angemeldet.\n" if rc == 0 else "error: Anmeldung fehlgeschlagen – Nummer prüfen oder "
                          "Gerätelimit (5 Geräte) im Mullvad-Konto erreicht.\n"), self.mv_refresh()))

    def mv_logout(self):
        if ask_confirm(self, "Mullvad abmelden", "Dieses Gerät vom Mullvad-Konto abmelden?\n"
                       "Das VPN wird getrennt.", "Abmelden", danger=True):
            self._mv_action(["account", "logout"])

    def mv_start_daemon(self):
        self._root(["systemctl", "enable", "--now", "mullvad-daemon"])

    # ======================================================================
    # Firewall
    # ======================================================================

    def fw_refresh(self):
        def worker():
            active = svc_active("ufw") if self.fw_backend == "ufw" else \
                svc_active("firewalld") if self.fw_backend == "firewalld" else False
            ui(lambda: self._fw_show(active))
        threading.Thread(target=worker, daemon=True).start()

    def _fw_show(self, active):
        b = self.fw_backend
        self.b_fw_install.setVisible(b is None)
        for x in (self.b_fw_on, self.b_fw_status, self.b_fw_off):
            x.setVisible(b is not None)
        if b is None:
            self.fw_badge.set("danger", "Nicht installiert")
            self.fw_label.setText("Weder ufw noch firewalld gefunden.")
            return
        self.fw_badge.set("ok" if active else "danger", "Aktiv" if active else "Aus")
        self.fw_label.setText(f"Backend: {b}")
        self.b_fw_on.setVisible(not active)
        self.b_fw_off.setVisible(active)

    def fw_install(self):
        self._root(["pacman", "-S", "ufw"], interactive=True,
                   then=lambda rc: (setattr(self, "fw_backend", "ufw" if which("ufw") else None),
                                    self.fw_rules.setVisible(self.fw_backend == "ufw")))

    def fw_enable(self):
        if not ask_confirm(self, "Firewall", "Firewall aktivieren? Eingehende Verbindungen werden dann blockiert "
                           "(ausgehende bleiben erlaubt).", "Aktivieren"):
            return
        if self.fw_backend == "ufw":
            if not self.app.priv.ensure(self):
                return
            steps = [{"cmd": ["ufw", "default", "deny", "incoming"], "needs_sudo": True, "label": "ufw default deny incoming"},
                     {"cmd": ["ufw", "default", "allow", "outgoing"], "needs_sudo": True, "label": "ufw default allow outgoing"},
                     {"cmd": ["ufw", "--force", "enable"], "needs_sudo": True, "label": "ufw --force enable"},
                     {"cmd": ["systemctl", "enable", "--now", "ufw"], "needs_sudo": True, "label": "systemctl enable --now ufw"}]
            run_sequence(steps, self.log, on_all_done=lambda: (self.fw_status(), self.refresh_all()))
        elif self.fw_backend == "firewalld":
            self._root(["systemctl", "enable", "--now", "firewalld"])

    def fw_disable(self):
        if not ask_confirm(self, "Firewall", "Firewall wirklich deaktivieren?", "Deaktivieren", danger=True):
            return
        if self.fw_backend == "ufw":
            self._root(["ufw", "disable"])
        else:
            self._root(["systemctl", "disable", "--now", "firewalld"])

    def fw_status(self):
        if not self.app.priv.ensure(self):
            return
        if self.fw_backend == "firewalld":
            self.log.set_text("$ sudo firewall-cmd --list-all\n")
            run_streaming(["firewall-cmd", "--list-all"], self.log, needs_sudo=True, clear_first=False)
            return
        self.log.set_text("$ sudo ufw status numbered\n")
        lines = []

        def on_line(l):
            lines.append(l)

        def done(rc):
            self.rule_table.setRowCount(0)
            for l in lines:
                m = re.match(r"^\[\s*(\d+)\]\s+(.+)$", l.strip())
                if m:
                    r = self.rule_table.rowCount()
                    self.rule_table.insertRow(r)
                    self.rule_table.setItem(r, 0, NumItem(m.group(1), int(m.group(1))))
                    it = QTableWidgetItem(re.sub(r"\s{2,}", "   ", m.group(2)))
                    it.setFont(QFont(FONTS["mono"], 10))
                    self.rule_table.setItem(r, 1, it)
            self.fw_refresh()
        run_streaming(["ufw", "status", "numbered"], self.log, needs_sudo=True, clear_first=False,
                      on_line=on_line, on_done=done)

    def fw_add_rule(self):
        port = self.r_port.text().strip()
        if not re.match(r"^\d{1,5}(:\d{1,5})?$", port):
            show_warning(self, "Port", "Bitte einen Port (z. B. 22) oder Bereich (8000:8100) angeben.")
            return
        proto = self.r_proto.currentText()
        act = "allow" if self.r_act.currentIndex() == 0 else "deny"
        spec = port if proto == "tcp+udp" and ":" not in port else f"{port}/{proto.split('+')[0]}"
        self._root(["ufw", act, spec], then=lambda rc: self.fw_status())

    def fw_del_rule(self):
        rows = sorted({i.row() for i in self.rule_table.selectedIndexes()}, reverse=True)
        if not rows:
            show_info(self, "Regel", "Bitte eine Regel in der Liste auswählen.")
            return
        nums = [self.rule_table.item(r, 0).text() for r in rows]
        if not ask_confirm(self, "Regel löschen", f"Regel(n) {', '.join(nums)} löschen?", "Löschen", danger=True):
            return
        if not self.app.priv.ensure(self):
            return
        steps = [{"cmd": ["ufw", "--force", "delete", n], "needs_sudo": True, "label": f"ufw delete {n}"}
                 for n in sorted(nums, key=int, reverse=True)]
        run_sequence(steps, self.log, on_all_done=self.fw_status)


# --------------------------------------------------------------------------
# Einstellungen (vorerst: Über das Projekt & Autor)
# --------------------------------------------------------------------------

APP_AUTHOR = "PyloGER"
APP_COMPANY = "Voxellab"
APP_AUTHOR_MAIL = "contact@voxellab.de"

GEAR_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{c}"
 stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
<path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z"/>
<path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21
a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8
1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1
a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1
a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>
</svg>"""


def svg_icon(svg, size=18):
    from PySide6.QtSvg import QSvgRenderer
    from PySide6.QtCore import QByteArray
    icon = QIcon()
    for scale in (1, 2):
        px = QPixmap(size * scale, size * scale)
        px.fill(Qt.transparent)
        p = QPainter(px)
        p.setRenderHint(QPainter.Antialiasing)
        QSvgRenderer(QByteArray(svg.encode())).render(p, QRectF(0, 0, size * scale, size * scale))
        p.end()
        px.setDevicePixelRatio(scale)
        icon.addPixmap(px)
    return icon


# --------------------------------------------------------------------------
# Selbst-Aktualisierung (GitHub oder lokale Datei/Ordner)
# --------------------------------------------------------------------------

DEFAULT_REPO = "PyloGER/Tuxdex"   # GitHub-Repository für Updates (in den Einstellungen änderbar)
DEFAULT_BRANCH = "main"
SETTINGS_FILE = os.path.join(os.path.expanduser("~/.config"), "tuxdex", "settings.json")
BUILD_DIR = os.path.join(os.path.expanduser("~/.cache"), "tuxdex", "build")


def load_settings():
    s = {"repo": DEFAULT_REPO, "branch": DEFAULT_BRANCH, "auto_check": True, "ask_on_start": True, "local_dir": "",
         "sys_check_on_start": True}
    s.update(_load_json(SETTINGS_FILE, {}))
    return s


def save_settings(s):
    _save_json(SETTINGS_FILE, s)


def normalize_repo(text):
    """„https://github.com/a/b(.git)“, „git@github.com:a/b.git“ oder „a/b“ → „a/b“"""
    t = (text or "").strip()
    m = re.search(r"github\.com[/:]([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", t) or re.match(r"^([\w.-]+)/([\w.-]+)$", t)
    return f"{m.group(1)}/{m.group(2)}" if m else ""


def version_tuple(v):
    """Vergleichbare Version: 1.6.0 > 1.6.0-beta.2 > 1.6.0-beta.1 > 1.5.4 (auch „1.6.0beta1“ aus dem PKGBUILD)."""
    m = re.match(r"\s*v?(\d+(?:\.\d+)*)(?:[-.]?(alpha|beta|rc)\.?(\d*))?", v or "")
    if not m:
        return (0,)
    nums = [int(x) for x in m.group(1).split(".")][:4]
    nums += [0] * (4 - len(nums))
    stage = {"alpha": -3, "beta": -2, "rc": -1}.get(m.group(2), 0)
    return tuple(nums) + (stage, int(m.group(3) or 0))


def _http_get(url, timeout=15):
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": f"tuxdex/{APP_VERSION}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def latest_commit(repo, branch):
    """SHA des neuesten Commits auf dem Zweig – ohne Zwischenspeicher.
    1. Git-Protokoll (wie „git ls-remote“, kein Abfragelimit), 2. GitHub-API als Reserve."""
    try:
        refs = _http_get(f"https://github.com/{repo}.git/info/refs?service=git-upload-pack",
                         timeout=15).decode(errors="replace")
        m = re.search(r"([0-9a-f]{40}) refs/heads/" + re.escape(branch) + r"(?:\n|\x00|$)", refs)
        if m:
            return m.group(1)
    except Exception:
        pass
    try:
        data = json.loads(_http_get(f"https://api.github.com/repos/{repo}/commits/{branch}",
                                    timeout=15).decode())
        sha = data.get("sha", "")
        if re.fullmatch(r"[0-9a-f]{40}", sha):
            return sha
    except Exception:
        pass
    return None


def remote_info(repo, branch):
    """(version, changelog_markdown, commit) des Repos.
    Liest die Dateien über die Commit-ID statt über den Zweignamen: raw.githubusercontent.com
    speichert Zweig-Adressen bis zu 5 Minuten zwischen, Commit-Adressen ändern sich nie."""
    sha = latest_commit(repo, branch)
    base = f"https://raw.githubusercontent.com/{repo}/{sha or branch}"
    pkgb = _http_get(f"{base}/PKGBUILD").decode(errors="replace")
    m = re.search(r"^pkgver=([\w.]+)", pkgb, re.M)
    if not m:
        raise ValueError("PKGBUILD ohne pkgver gefunden")
    try:
        cl = _http_get(f"{base}/CHANGELOG.md").decode(errors="replace")
    except Exception:
        cl = ""
    # pkgver kennt keinen Bindestrich: „1.6.0beta1“ → „1.6.0-beta.1“ (wie APP_VERSION)
    return re.sub(r"(\d)(alpha|beta|rc)(\d*)$", r"\1-\2.\3", m.group(1)), cl, sha


def fetch_package_sources(repo, ref, dest, progress=None):
    """Lädt PKGBUILD und alle darin unter source=() genannten Dateien einzeln vom Commit `ref`.
    progress(i, n, name) wird nach jeder Datei aufgerufen (aus dem Worker-Thread)."""
    base = f"https://raw.githubusercontent.com/{repo}/{ref}"
    pkgb = _http_get(f"{base}/PKGBUILD", timeout=30)
    text = pkgb.decode(errors="replace")
    if not re.search(r"^pkgname=tuxdex\b", text, re.M):
        raise ValueError("Das PKGBUILD im Repository gehört nicht zu tuxdex")
    m = re.search(r"^source=\((.*?)\)", text, re.S | re.M)
    files = [f.strip("'\"") for f in (m.group(1).split() if m else [])]
    os.makedirs(dest, exist_ok=True)
    with open(os.path.join(dest, "PKGBUILD"), "wb") as fh:
        fh.write(pkgb)
    n = len(files) + 1
    if progress:
        progress(1, n, "PKGBUILD")
    for i, f in enumerate(files, 2):
        if "/" in f or "::" in f or f.startswith(".") or not re.fullmatch(r"[\w.+-]+", f):
            raise ValueError(f"unerwarteter Dateiname im PKGBUILD: {f}")
        with open(os.path.join(dest, f), "wb") as fh:
            fh.write(_http_get(f"{base}/{f}", timeout=60))
        if progress:
            progress(i, n, f)
    return dest


def changes_since(changelog, current):
    """Abschnitte „## x.y.z“ aus dem Changelog, die neuer als die laufende Version sind."""
    out, keep = [], False
    for line in changelog.splitlines():
        h = re.match(r"^##\s+v?(\d[\w.-]*)", line)
        if h:
            keep = version_tuple(h.group(1)) > version_tuple(current)
            if keep:
                out.append(f"<b>Version {h.group(1)}</b>")
            continue
        if keep and line.strip().startswith(("-", "*")):
            item = line.strip()[1:].strip().replace("&", "&amp;").replace("<", "&lt;")
            item = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", item)
            item = re.sub(r"`([^`]+)`", r"<code>\1</code>", item)
            out.append("• " + item)
    return "<br>".join(out)


def _safe_extract(tar, dest):
    base = os.path.realpath(dest)
    for m in tar.getmembers():
        target = os.path.realpath(os.path.join(dest, m.name))
        if not target.startswith(base + os.sep) or m.issym() or m.islnk() or m.isdev():
            raise ValueError(f"unsicherer Eintrag im Archiv: {m.name}")
    tar.extractall(dest)


def find_pkgbuild(root):
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in (".git", "src", "pkg")]
        if "PKGBUILD" in files and re.search(r"^pkgname=tuxdex\b", _read(os.path.join(d, "PKGBUILD")), re.M):
            return d
    return None


def fresh_build_dir():
    d = os.path.join(BUILD_DIR, datetime.now().strftime("%Y%m%d-%H%M%S"))
    shutil.rmtree(BUILD_DIR, ignore_errors=True)
    os.makedirs(d, exist_ok=True)
    return d


class UpdatePanel(QWidget):
    """Einstellungen → Aktualisierung"""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.settings = load_settings()
        self.remote_version = None
        self.remote_sha = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(16)

        p = Panel("Aktualisierung")
        head = QHBoxLayout()
        head.setSpacing(12)
        self.badge = StatusBadge("off", "Noch nicht geprüft")
        head.addWidget(self.badge)
        head.addWidget(Label(f"Installiert: {APP_VERSION}  ·  "
                             f"{'als Paket (pacman)' if SYSTEM_INSTALL else 'als Skript'}", "Value"))
        head.addStretch(1)
        self.b_check = Button("Nach Updates suchen", "ghost", self.check)
        self.b_update = Button("Jetzt aktualisieren", "primary", self.update_from_github)
        self.b_update.hide()
        head.addWidget(self.b_check)
        head.addWidget(self.b_update)
        p.body.addLayout(head)
        self.changes = Label("", "Muted", wrap=True)
        self.changes.setTextFormat(Qt.RichText)
        self.changes.hide()
        p.body.addWidget(self.changes)

        # GitHub-Quelle
        src = QHBoxLayout()
        src.setSpacing(8)
        self.repo_edit = LineEdit(self.settings.get("repo", ""), placeholder="benutzer/tuxdex oder GitHub-Link",
                                  mono=True)
        self.channel = QComboBox()
        self.channel.setMinimumHeight(38)
        self.channel.addItem("Vollversion (empfohlen)", "main")
        self.channel.addItem("Beta – neue Funktionen früher", "beta")
        cur = self.settings.get("branch", "main")
        if self.channel.findData(cur) < 0:
            self.channel.addItem(f"Zweig „{cur}“", cur)
        self.channel.setCurrentIndex(self.channel.findData(cur))
        self.channel.currentIndexChanged.connect(self._channel_changed)
        src.addLayout(Field("GitHub-Repository", self.repo_edit), 1)
        src.addLayout(Field("Version", self.channel))
        sb = QVBoxLayout()
        sb.addStretch(1)
        sb.addWidget(Button("Speichern", "ghost", self.save_source))
        src.addLayout(sb)
        p.body.addLayout(src)
        self.cb_auto = QCheckBox("Beim Start automatisch nach Updates suchen")
        self.cb_auto.setChecked(bool(self.settings.get("auto_check", True)))
        self.cb_auto.toggled.connect(self._auto_changed)
        p.body.addWidget(self.cb_auto)
        self.cb_ask = QCheckBox("Gefundene Updates beim Start in einem Fenster anbieten (sonst nur Hinweis unten rechts)")
        self.cb_ask.setChecked(bool(self.settings.get("ask_on_start", True)))
        self.cb_ask.setEnabled(self.cb_auto.isChecked())
        self.cb_ask.toggled.connect(self._ask_changed)
        p.body.addWidget(self.cb_ask)

        # Lokal
        p.body.addWidget(Label("LOKAL AKTUALISIEREN", "FieldLabel"))
        lr = QHBoxLayout()
        lr.setSpacing(8)
        lr.addWidget(Button("Aus Datei …", "ghost", self.update_from_file,
                            "tuxdex-X.Y.Z.tar.gz oder (bei Skript-Start) eine tuxdex.py"))
        lr.addWidget(Button("Aus Ordner …", "ghost", self.update_from_folder,
                            "Ordner mit PKGBUILD, z. B. dein geklonter Git-Ordner"))
        self.b_last = Button("", "ghost", lambda: self._update_folder(self.settings.get("local_dir", "")))
        lr.addWidget(self.b_last)
        lr.addStretch(1)
        p.body.addLayout(lr)
        self._update_last_btn()
        p.body.addWidget(Label("Ist der Ordner ein Git-Klon, holt Tuxdex vorher die neueste Version (git pull). "
                               "Gebaut wird mit makepkg in einem Arbeitsordner, installiert mit pacman – "
                               "danach startet Tuxdex neu.", "Hint", wrap=True))
        self.step = Label("", "Hint")
        self.step.hide()
        p.body.addWidget(self.step)
        self.progress = ProgressBar()
        self.progress.hide()
        p.body.addWidget(self.progress)
        self.log = LogView(150)
        self.log.hide()
        p.body.addWidget(self.log)
        lay.addWidget(p)

    # ---- Einstellungen ------------------------------------------------------

    def _update_last_btn(self):
        d = self.settings.get("local_dir", "")
        self.b_last.setVisible(bool(d) and os.path.isdir(d))
        if d:
            home = os.path.expanduser("~")
            self.b_last.setText("Erneut aus " + ("~" + d[len(home):] if d.startswith(home) else d))

    def save_source(self):
        repo = normalize_repo(self.repo_edit.text())
        if self.repo_edit.text().strip() and not repo:
            show_warning(self, "Repository", "Bitte „benutzer/repo“ oder einen GitHub-Link angeben.")
            return
        self.settings["repo"] = repo
        self.settings["branch"] = self.channel.currentData() or "main"
        self.repo_edit.setText(repo)
        save_settings(self.settings)
        self.app.set_status("Update-Quelle gespeichert.")
        if repo:
            self.check()

    def _channel_changed(self, _=0):
        branch = self.channel.currentData() or "main"
        if branch == "beta" and self.settings.get("branch") != "beta" and not ask_confirm(
                self, "Beta-Versionen", "Beta-Versionen bekommen neue Funktionen früher, können aber noch Fehler "
                "haben.\n\nZurück zur Vollversion geht jederzeit hier.", "Beta verwenden"):
            self.channel.blockSignals(True)
            self.channel.setCurrentIndex(self.channel.findData(self.settings.get("branch", "main")))
            self.channel.blockSignals(False)
            return
        self.settings["branch"] = branch
        save_settings(self.settings)
        self.app.set_status("Beta-Versionen aktiv." if branch == "beta" else "Vollversion ausgewählt.")
        self.check()

    def _auto_changed(self, on):
        self.settings["auto_check"] = on
        self.cb_ask.setEnabled(on)
        save_settings(self.settings)

    def _ask_changed(self, on):
        self.settings["ask_on_start"] = on
        save_settings(self.settings)

    # ---- GitHub ---------------------------------------------------------------

    def check(self, silent=False):
        repo = self.settings.get("repo") or normalize_repo(self.repo_edit.text())
        if not repo:
            if not silent:
                self.badge.set("warn", "Kein Repository eingetragen")
            return
        self.badge.set("info", "Prüfe …")
        self.b_check.setEnabled(False)
        branch = self.settings.get("branch", "main")

        def worker():
            try:
                ver, cl, sha = remote_info(repo, branch)
                self.remote_sha = sha
                res = (ver, cl, None)
            except Exception as e:
                res = (None, "", str(e))
            ui(lambda: self._checked(*res, silent=silent))
        threading.Thread(target=worker, daemon=True).start()

    def _checked(self, ver, cl, err, silent=False):
        self.b_check.setEnabled(True)
        if err:
            self.badge.set("danger", "Prüfen fehlgeschlagen")
            if not silent:
                self.changes.setText(f"GitHub nicht erreichbar oder Repository falsch: {err}")
                self.changes.show()
            return
        self.remote_version = ver
        newer = version_tuple(ver) > version_tuple(APP_VERSION)
        # Von einer Beta zurück zur Vollversion: ältere Version anbieten, aber nicht beim Start aufdrängen
        back = not newer and self.settings.get("branch", "main") == "main" and \
            version_tuple(ver) < version_tuple(APP_VERSION)
        self.b_update.setText(f"Zur Vollversion {ver} wechseln" if back else "Jetzt aktualisieren")
        self.b_update.setVisible(newer or back)
        self.app.show_update_hint(ver if newer else None)
        if back:
            self.badge.set("info", f"Beta {APP_VERSION} installiert")
            self.changes.setText(f"Die aktuelle Vollversion ist {ver}. Du nutzt noch die Beta {APP_VERSION} – "
                                 "wechseln installiert die Vollversion.")
            self.changes.setVisible(not silent)
        elif newer:
            self.badge.set("warn", f"Version {ver} verfügbar")
            txt = changes_since(cl, APP_VERSION)
            self.changes.setText(txt or f"Neue Version {ver}.")
            self.changes.show()
            if silent and self.settings.get("ask_on_start", True):
                self._offer_update(ver, txt)
        else:
            self.badge.set("ok", "Aktuell")
            self.changes.setText(f"Auf GitHub ist Version {ver} – du bist auf dem neuesten Stand.")
            self.changes.setVisible(not silent)

    def _offer_update(self, ver, changes_html):
        """Beim Start: neue Version in einem Fenster anbieten."""
        box = QMessageBox(self.window())
        box.setWindowTitle("Update verfügbar")
        box.setTextFormat(Qt.RichText)
        box.setText(f"<b>Tuxdex {ver} ist verfügbar</b> – installiert ist {APP_VERSION}.")
        box.setInformativeText(changes_html or "")
        later = box.addButton("Später", QMessageBox.RejectRole)
        later.setProperty("variant", "ghost")
        now = box.addButton("Jetzt aktualisieren", QMessageBox.AcceptRole)
        now.setProperty("variant", "primary")
        box.setDefaultButton(now)
        box.exec()
        if box.clickedButton() is now:
            self.app.open_settings()
            self.update_from_github(confirmed=True)

    # ---- Fortschritt ----------------------------------------------------------

    def _prog(self, value, text):
        """Fortschritt 0–100 (None = unbestimmt) mit Schritt-Beschreibung; Balken läuft nie zurück."""
        if value is not None:
            value = max(value, self.progress.value or 0)
        self.progress.show()
        self.step.show()
        self.step.setText(text)
        self.progress.set(value, "" if value is None else f"{int(value)} %")

    def _prog_fail(self, text):
        self.step.show()
        self.step.setText("✕  " + text)
        self.progress.set(self.progress.value or 0, "Fehler")

    def _need_admin(self):
        """Ohne gültige sudo-Sitzung startet keine Aktualisierung."""
        if not SYSTEM_INSTALL:
            return True
        if self.app.priv.ensure(self):
            return True
        self.badge.set("warn", "Abgebrochen – Admin-Rechte nötig")
        show_warning(self, "Admin-Rechte nötig",
                     "Zum Aktualisieren wird das Paket mit pacman installiert – dafür ist das sudo-Passwort nötig. "
                     "Ohne Anmeldung wird nichts heruntergeladen oder verändert.")
        return False

    def _start_progress(self):
        self.progress.value = 0
        self._prog(0, "Vorbereiten …")

    def update_from_github(self, confirmed=False):
        repo, branch = self.settings.get("repo"), self.settings.get("branch", "main")
        if not repo:
            return
        if not confirmed and not ask_confirm(self, "Aktualisieren",
                                             f"Tuxdex auf Version {self.remote_version} aktualisieren?\n\n"
                                             f"Quelle: github.com/{repo} ({branch})", "Aktualisieren"):
            return
        if not self._need_admin():
            return
        self.log.show()
        self.log.set_text(f"Lade github.com/{repo} ({branch}) …\n")
        self.badge.set("info", "Lade herunter …")
        self._start_progress()
        self._prog(2, "Suche neuesten Stand …")

        def step(i, n, name):
            ui(lambda: self._prog(5 + 20 * i / n, f"Lade Dateien {i}/{n}: {name}"))

        def worker():
            try:
                if SYSTEM_INSTALL:
                    ref = latest_commit(repo, branch) or branch
                    ui(lambda r=ref: (self.log.append_text(f"Commit {r[:7]} – lade Dateien …\n"),
                                      self._prog(5, f"Commit {r[:7]} – lade Dateien …")))
                    src = fetch_package_sources(repo, ref, os.path.join(fresh_build_dir(), "tuxdex"), step)
                    ui(lambda: self._build(src))
                else:
                    ref = latest_commit(repo, branch) or branch
                    code = _http_get(f"https://raw.githubusercontent.com/{repo}/{ref}/tuxdex.py", timeout=60)
                    ui(lambda: self._replace_script(code))
            except Exception as e:
                ui(lambda m=str(e): (self.log.append_text(f"error: {m}\n"),
                                     self.badge.set("danger", "Aktualisierung fehlgeschlagen"),
                                     self._prog_fail("Download fehlgeschlagen")))
        threading.Thread(target=worker, daemon=True).start()

    # ---- Lokal ----------------------------------------------------------------

    def update_from_file(self):
        from PySide6.QtWidgets import QFileDialog
        f, _ = QFileDialog.getOpenFileName(self, "Tuxdex-Update wählen", os.path.expanduser("~"),
                                           "Tuxdex (*.tar.gz *.tgz *.py);;Alle Dateien (*)")
        if not f:
            return
        if not f.endswith(".py") and not self._need_admin():
            return
        if not f.endswith(".py"):
            self._start_progress()
            self._prog(10, "Entpacke Archiv …")
        self.log.show()
        if f.endswith(".py"):
            if SYSTEM_INSTALL:
                show_info(self, "Paket-Installation", "Tuxdex ist als Paket installiert – bitte das Archiv "
                          "(tuxdex-X.Y.Z.tar.gz) oder den Ordner mit PKGBUILD wählen.")
                return
            with open(f, "rb") as fh:
                self._replace_script(fh.read())
            return
        try:
            import tarfile
            d = fresh_build_dir()
            with tarfile.open(f, "r:*") as t:
                _safe_extract(t, d)
            src = find_pkgbuild(d)
            if not src:
                raise ValueError("Im Archiv ist kein PKGBUILD für tuxdex.")
        except Exception as e:
            show_error(self, "Archiv", str(e))
            self._prog_fail("Archiv ungültig")
            return
        if SYSTEM_INSTALL:
            self._confirm_build(src, os.path.basename(f))
        else:
            self._script_from_dir(src)

    def update_from_folder(self):
        from PySide6.QtWidgets import QFileDialog
        d = QFileDialog.getExistingDirectory(self, "Ordner mit Tuxdex (PKGBUILD) wählen",
                                             self.settings.get("local_dir") or os.path.expanduser("~"))
        if d:
            self._update_folder(d)

    def _update_folder(self, d):
        if not d or not os.path.isdir(d):
            return
        if not find_pkgbuild(d):
            show_error(self, "Ordner", "In diesem Ordner liegt kein PKGBUILD für tuxdex.")
            return
        if not self._need_admin():
            return
        self._start_progress()
        self._prog(5, "Hole neueste Version (git pull) …")
        self.settings["local_dir"] = d
        save_settings(self.settings)
        self._update_last_btn()
        self.log.show()
        if os.path.isdir(os.path.join(d, ".git")) and which("git"):
            self.log.set_text(f"$ git -C {d} pull --ff-only\n")
            run_streaming(["git", "-C", d, "pull", "--ff-only"], self.log, clear_first=False,
                          on_done=lambda rc: self._copy_and_build(d))
        else:
            self.log.set_text("")
            self._copy_and_build(d)

    def _copy_and_build(self, d):
        src = find_pkgbuild(d)
        dst = fresh_build_dir()
        shutil.copytree(src, os.path.join(dst, "tuxdex"), ignore=shutil.ignore_patterns(".git", "src", "pkg", "*.pkg.tar*"))
        if SYSTEM_INSTALL:
            self._confirm_build(os.path.join(dst, "tuxdex"), d)
        else:
            self._script_from_dir(os.path.join(dst, "tuxdex"))

    def _script_from_dir(self, d):
        p = os.path.join(d, "tuxdex.py")
        if not os.path.exists(p):
            show_error(self, "Update", "Im Paket fehlt tuxdex.py.")
            return
        with open(p, "rb") as fh:
            self._replace_script(fh.read())

    def _confirm_build(self, src, origin):
        m = re.search(r"^pkgver=([\w.]+)", _read(os.path.join(src, "PKGBUILD")), re.M)
        ver = m.group(1) if m else "?"
        if version_tuple(ver) <= version_tuple(APP_VERSION):
            if not ask_confirm(self, "Gleiche oder ältere Version", f"{origin} enthält Version {ver} – installiert ist "
                               f"{APP_VERSION}. Trotzdem neu installieren?", "Installieren"):
                self._prog_fail("Abgebrochen")
                return
        elif not ask_confirm(self, "Aktualisieren", f"Tuxdex {ver} aus {origin} installieren?", "Aktualisieren"):
            self._prog_fail("Abgebrochen")
            return
        self._build(src)

    # ---- Bauen, installieren, neu starten ------------------------------------

    # makepkg-/pacman-Meldungen → Fortschritt (Prozent, Beschreibung)
    MAKEPKG_STEPS = [
        ("Making package", 30, "Baue Paket …"),
        ("Checking runtime dependencies", 32, "Prüfe Abhängigkeiten …"),
        ("Installing missing dependencies", 35, "Installiere fehlende Abhängigkeiten …"),
        ("Retrieving sources", 45, "Quellen vorbereiten …"),
        ("Validating source", 50, "Prüfe Prüfsummen …"),
        ("Extracting sources", 55, "Entpacke Quellen …"),
        ("Starting package()", 62, "Stelle Paketinhalt zusammen …"),
        ("Tidying install", 68, "Räume auf …"),
        ("Creating package", 72, "Erzeuge Paketdatei …"),
        ("Compressing package", 76, "Komprimiere Paket …"),
        ("Finished making", 80, "Paket gebaut"),
    ]
    PACMAN_STEPS = [
        ("loading packages", 84, "Lade Paket …"),
        ("checking keys", 86, "Prüfe Paket …"),
        ("checking package integrity", 87, "Prüfe Paket …"),
        ("checking for file conflicts", 89, "Prüfe Dateikonflikte …"),
        ("upgrading tuxdex", 92, "Installiere neue Version …"),
        ("installing tuxdex", 92, "Installiere neue Version …"),
        ("Running post-transaction hooks", 96, "Abschluss-Hooks …"),
    ]

    def _progress_from(self, table, line):
        for key, pct, text in table:
            if key.lower() in line.lower():
                if pct >= (self.progress.value or 0):
                    self._prog(pct, text)
                return

    def _build(self, src):
        if not which("makepkg"):
            show_error(self, "makepkg fehlt", "makepkg (Paket pacman, Gruppe base-devel) wird benötigt.")
            self._prog_fail("makepkg fehlt")
            return
        if not self._need_admin():
            self._prog_fail("Keine Admin-Rechte")
            return
        self.log.show()
        self.badge.set("info", "Baue Paket …")
        self._prog(28, "Baue Paket …")
        self.log.append_text(f"\n$ makepkg -f -s   (in {short_path(src)})\n")

        def built(rc):
            pkgs = sorted(f for f in os.listdir(src) if f.startswith("tuxdex-") and ".pkg.tar" in f)
            if rc != 0 or not pkgs:
                self.badge.set("danger", "Bauen fehlgeschlagen")
                self._prog_fail("Bauen fehlgeschlagen")
                self.log.append_text(f"error: Kein Paket gebaut (Exit-Code {rc}) – Meldungen oben prüfen.\n")
                return
            pkg = os.path.join(src, pkgs[-1])
            self._prog(82, "Installiere mit pacman …")
            self.badge.set("info", "Installiere …")
            self.log.append_text(f"\n$ sudo pacman -U {pkgs[-1]}\n")
            run_streaming(["pacman", "-U", "--noconfirm", pkg], self.log, needs_sudo=True, clear_first=False,
                          interactive=True, on_done=self._installed,
                          on_line=lambda l: self._progress_from(self.PACMAN_STEPS, l))
        run_streaming(["makepkg", "-f", "-s", "--noconfirm"], self.log, clear_first=False, interactive=True,
                      cwd=src, on_done=built, on_line=lambda l: self._progress_from(self.MAKEPKG_STEPS, l))

    def _installed(self, rc):
        self.log.append_text(f"[Exit-Code {rc}]\n")
        if rc != 0:
            self.badge.set("danger", "Installation fehlgeschlagen")
            self._prog_fail("Installation fehlgeschlagen")
            return
        self.badge.set("ok", "Installiert")
        self._prog(100, "Fertig – neue Version installiert")
        if ask_confirm(self, "Aktualisiert", "Die neue Version ist installiert. Tuxdex jetzt neu starten?",
                       "Neu starten"):
            self.app.restart()

    def _replace_script(self, code):
        try:
            compile(code, "tuxdex.py", "exec")
        except SyntaxError as e:
            show_error(self, "Update", f"Die neue Datei ist fehlerhaft und wird nicht übernommen: {e}")
            return
        m = re.search(rb'^APP_VERSION = "([\w.-]+)"', code, re.M)
        ver = m.group(1).decode() if m else "?"
        path = os.path.abspath(__file__)
        if not ask_confirm(self, "Aktualisieren", f"Skript auf Version {ver} ersetzen?\n\n{path}\n"
                           "(Die alte Datei bleibt als .bak erhalten.)", "Ersetzen"):
            return
        try:
            shutil.copy2(path, path + ".bak")
            tmp = path + ".new"
            with open(tmp, "wb") as fh:
                fh.write(code)
            os.chmod(tmp, os.stat(path).st_mode)
            os.replace(tmp, path)
        except Exception as e:
            show_error(self, "Update", f"Datei konnte nicht ersetzt werden: {e}")
            return
        self.log.append_text(f"Skript auf {ver} aktualisiert (Sicherung: {path}.bak)\n")
        self.badge.set("ok", "Aktualisiert")
        if ask_confirm(self, "Aktualisiert", "Tuxdex jetzt neu starten?", "Neu starten"):
            self.app.restart()


class SettingsPage(Page):
    def _sys_changed(self, on):
        st = load_settings()
        st["sys_check_on_start"] = on
        save_settings(st)
        self.update_panel.settings["sys_check_on_start"] = on   # gemeinsame Datei nicht mit altem Stand überschreiben
        self.app.set_status("Gespeichert – gilt ab dem nächsten Start.")

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.lay.addLayout(page_header("Einstellungen", Button("← Zurück", "ghost", app.back_from_settings)))
        sysp = Panel("System-Updates")
        self.cb_sys = QCheckBox("Beim Start automatisch nach System-Updates suchen (pacman, AUR, Flatpak)")
        self.cb_sys.setChecked(bool(load_settings().get("sys_check_on_start", True)))
        self.cb_sys.toggled.connect(self._sys_changed)
        sysp.body.addWidget(self.cb_sys)
        sysp.body.addWidget(Label("Gefundene Updates erscheinen als Zahl am Tab „Updates“ und unten rechts – "
                                  "installiert wird erst, wenn du im Tab „Updates“ auf „Update starten“ klickst.",
                                  "Hint", wrap=True))
        self.lay.addWidget(sysp)
        self.update_panel = UpdatePanel(app)
        self.lay.addWidget(self.update_panel)

        # --- Über ---
        about = Panel("Über das Projekt")
        top = QHBoxLayout()
        top.setSpacing(20)
        logo = QLabel()
        logo.setPixmap(logo_pixmap(96, self.devicePixelRatioF() or 1.0))
        logo.setFixedSize(96, 96)
        top.addWidget(logo, 0, Qt.AlignTop)
        txt = QVBoxLayout()
        txt.setSpacing(4)
        txt.addWidget(Label("Tuxdex", "PageTitle"))
        txt.addWidget(Label(f"Version {APP_VERSION}  ·  {'als Paket installiert' if SYSTEM_INSTALL else 'als Skript gestartet'}",
                            "Value"))
        txt.addWidget(Label("Grafische Systemverwaltung für Arch Linux – alles in einem Fenster, ohne Terminal. "
                            "Befehle laufen sichtbar in der Ausgabe, root-Rechte werden nur bei Bedarf und "
                            "einmal pro Sitzung abgefragt.", "Muted", wrap=True))
        txt.addStretch(1)
        top.addLayout(txt, 1)
        about.body.addLayout(top)
        mods = QGridLayout()
        mods.setHorizontalSpacing(24)
        mods.setVerticalSpacing(6)
        desc = {
            "update": "Updates prüfen und einspielen (pacman, AUR, Flatpak), Major-Updates erkennen",
            "software": "Pakete mit Icons, Größe, Version und Datum – per Kästchen auswählen und entfernen",
            "flatpak": "Flatpak-Apps und ihre Rechte (Dateien, Geräte, Netzwerk …) wie mit Flatseal",
            "disks": "Laufwerke einhängen, umbenennen, prüfen, formatieren, sicher entfernen",
            "storage": "Belegung je Festplatte, größte Ordner, Aufräumen",
            "swap": "Fallback-Speicher (Swapfile) und Swappiness",
            "tasks": "Prozesse, Leistung, Hardware- und Netzwerkinfos",
            "antivirus": "ClamAV: Signaturen, Scans, Quarantäne",
            "security": "Sicherheits-Check, offene Ports, Mullvad VPN, Firewall",
            "users": "Benutzerkonten und letzte Anmeldung",
        }
        for i, (key, name, color) in enumerate(MODULES):
            row = QHBoxLayout()
            row.setSpacing(8)
            dot = QLabel()
            dot.setFixedSize(8, 8)
            dot.setStyleSheet(f"background: {color}; border-radius: 2px;")
            row.addWidget(dot)
            row.addWidget(Label(name, "PanelTitle"))
            row.addWidget(Label("– " + desc.get(key, ""), "Hint", wrap=True), 1)
            mods.addLayout(row, i // 2, i % 2)
        about.body.addWidget(Label("MODULE", "FieldLabel"))
        about.body.addLayout(mods)
        self.lay.addWidget(about)

        # --- Autor ---
        au = Panel("Autor")
        g = QGridLayout()
        g.setHorizontalSpacing(24)
        g.setVerticalSpacing(12)
        g.addLayout(Field("Entwickelt von", Label(APP_AUTHOR, "Value")), 0, 0)
        g.addLayout(Field("Unternehmen", Label(APP_COMPANY, "Value")), 0, 2)
        gh = Label(f'<a style="color:{COLORS["accent"]}" href="https://github.com/{DEFAULT_REPO}">'
                   f'github.com/{DEFAULT_REPO}</a>', "Value")
        gh.setTextFormat(Qt.RichText)
        gh.setOpenExternalLinks(True)
        g.addLayout(Field("Projektseite", gh), 1, 2)
        g.addLayout(Field("Entstanden mit", Label("KI-gestützt entwickelt (AI made) – in Zusammenarbeit mit Claude "
                                                    "von Anthropic", "Value", wrap=True)), 2, 0, 1, 3)
        mail = Label(f'<a style="color:{COLORS["accent"]}" href="mailto:{APP_AUTHOR_MAIL}">{APP_AUTHOR_MAIL}</a>',
                     "Value")
        mail.setTextFormat(Qt.RichText)
        mail.setOpenExternalLinks(True)
        g.addLayout(Field("Kontakt", mail), 0, 1)
        g.addLayout(Field("Lizenz", Label("MIT – frei nutzbar, veränderbar und weitergebbar", "Value", wrap=True)), 1, 0)
        g.addLayout(Field("Erstellt", Label("2026", "Value")), 1, 1)
        au.body.addLayout(g)
        self.lay.addWidget(au)

        # --- Technik ---
        from PySide6 import __version__ as pyside_ver
        from PySide6.QtCore import qVersion
        te = Panel("Technik")
        g2 = QGridLayout()
        g2.setHorizontalSpacing(24)
        g2.setVerticalSpacing(12)
        paths = [
            ("Python", sys.version.split()[0]),
            ("Qt / PySide6", f"{qVersion()} / {pyside_ver}"),
            ("Schriften", f"{FONTS['sans']} · {FONTS['mono']}"),
            ("Programmdatei", short_path(os.path.abspath(__file__))),
            ("Zwischenspeicher", short_path(CACHE_DIR)),
            ("Quarantäne", short_path(QUARANTINE_DIR)),
            ("Fehlerprotokoll", "~/tuxdex_error.log"),
        ]
        for i, (k, v) in enumerate(paths):
            lab = Label(v, "Value", wrap=True)
            lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
            g2.addLayout(Field(k, lab), i // 2, i % 2)
        te.body.addLayout(g2)
        self.lay.addWidget(te)
        self.lay.addStretch(1)


# --------------------------------------------------------------------------
# Hauptfenster
# --------------------------------------------------------------------------

class TabButton(QFrame):
    """Tab im Stil des Design-Systems: Farbpunkt + Text, aktiv mit 3px-Strich in Modulfarbe."""

    def __init__(self, text, color, on_click):
        super().__init__()
        self.setObjectName("Tab")
        self.setCursor(Qt.PointingHandCursor)
        self.on_click = on_click
        self.color = color
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        row = QHBoxLayout()
        row.setContentsMargins(11, 12, 11, 9)
        row.setSpacing(8)
        dot = QLabel()
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(f"background: {color}; border-radius: 2px;")
        row.addWidget(dot)
        self.text = Label(text, "TabText")
        row.addWidget(self.text)
        lay.addLayout(row)
        self.bar = QFrame()
        self.bar.setFixedHeight(3)
        bar_row = QHBoxLayout()
        bar_row.setContentsMargins(12, 0, 12, 0)
        bar_row.addWidget(self.bar)
        lay.addLayout(bar_row)
        self.set_selected(False)

    def set_selected(self, sel):
        self.setProperty("selected", "true" if sel else "false")
        self.bar.setStyleSheet(
            f"background: {self.color if sel else 'transparent'}; border-top-left-radius: 2px; "
            "border-top-right-radius: 2px;")
        repolish(self)
        repolish(self.text)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.on_click()


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("Root")
        self.setWindowTitle("Tuxdex")
        self.resize(1240, 900)
        self.setMinimumSize(1140, 640)

        self.priv = PrivilegeManager(self, on_change=self._on_auth_change)
        self._authed = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Kopfleiste
        top = QFrame()
        top.setObjectName("Topbar")
        tl = QHBoxLayout(top)
        tl.setContentsMargins(24, 16, 24, 8)
        tl.setSpacing(12)
        logo = QLabel()
        logo.setPixmap(logo_pixmap(34, self.devicePixelRatioF() or 1.0))
        logo.setFixedSize(34, 34)
        tl.addWidget(logo)
        tl.addSpacing(4)
        tl.addWidget(Label("Tuxdex", "AppTitle"))
        tl.addStretch(1)
        self.auth_badge = StatusBadge("off", "Nicht angemeldet")
        tl.addWidget(self.auth_badge)
        self.auth_btn = Button("Anmelden", "primary", self._toggle_auth)
        tl.addWidget(self.auth_btn)
        root.addWidget(top)

        # Tab-Leiste
        tabbar = QFrame()
        tabbar.setObjectName("TabBar")
        tb = QHBoxLayout(tabbar)
        tb.setContentsMargins(16, 4, 16, 0)
        tb.setSpacing(2)
        root.addWidget(tabbar)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        # Statusleiste
        sb = QFrame()
        sb.setObjectName("Statusbar")
        sl = QHBoxLayout(sb)
        sl.setContentsMargins(14, 4, 24, 4)
        self.gear = QPushButton()
        self.gear.setObjectName("Gear")
        self.gear.setIcon(svg_icon(GEAR_SVG.replace("{c}", COLORS["muted"])))
        self.gear.setIconSize(QSize(18, 18))
        self.gear.setCursor(Qt.PointingHandCursor)
        self.gear.setFocusPolicy(Qt.TabFocus)
        self.gear.setToolTip("Einstellungen")
        self.gear.setCheckable(True)
        self.gear.clicked.connect(self.open_settings)
        sl.addWidget(self.gear)
        sl.addSpacing(8)
        self.status = Label("Bereit.", "StatusText")
        sl.addWidget(self.status)
        sl.addStretch(1)
        self.sys_hint = Button("", "ghost", lambda: self.select([m[0] for m in MODULES].index("update")))
        self.sys_hint.setObjectName("SysHint")
        self.sys_hint.hide()
        sl.addWidget(self.sys_hint)
        sl.addSpacing(8)
        self._sys_updates = (0, 0)
        self.upd_hint = Button("", "ghost", self.open_settings)
        self.upd_hint.setObjectName("UpdHint")
        self.upd_hint.hide()
        sl.addWidget(self.upd_hint)
        sl.addSpacing(12)
        sl.addWidget(Label(f"Version {APP_VERSION}", "StatusText"))
        root.addWidget(sb)

        pages = {
            "update": UpdaterTab, "software": SoftwareTab, "flatpak": FlatpakTab, "swap": SwapTab,
            "disks": DisksTab, "storage": StorageTab, "tasks": TaskTab, "antivirus": AntivirusTab,
            "security": SecurityTab, "users": UsersTab,
        }
        self.tabs = []
        self.pages = {}
        for i, (key, label, color) in enumerate(MODULES):
            self.pages[key] = pages[key](self)
            self.stack.addWidget(self.pages[key])
            t = TabButton(label, color, lambda i=i: self.select(i))
            tb.addWidget(t)
            self.tabs.append(t)
        tb.addStretch(1)
        self.show_sys_updates(*self._sys_updates)
        self.settings_page = SettingsPage(self)
        self.stack.addWidget(self.settings_page)
        if self.settings_page.update_panel.settings.get("auto_check") and \
                self.settings_page.update_panel.settings.get("repo"):
            QTimer.singleShot(2500, lambda: self.settings_page.update_panel.check(silent=True))
        self._last_tab = 0
        self.select(0)

        # sudo-Status beim Start und danach alle 30 s prüfen (sudo-Sitzungen laufen ab)
        # Laufwerke & Einhängepunkte beobachten: USB-Stick einstecken → Listen aktualisieren
        self._dev_state = self._device_state()
        self._dev_timer = QTimer(self)
        self._dev_timer.timeout.connect(self._check_devices)
        self._dev_timer.start(2000)

        if kernel_modules_missing():
            self.set_status("Kernel wurde aktualisiert – bitte neu starten, damit z. B. USB-Sticks erkannt werden.")

        self._poll_auth()
        self._auth_timer = QTimer(self)
        self._auth_timer.timeout.connect(self._poll_auth)
        self._auth_timer.start(30000)

    def _poll_auth(self):
        def worker():
            ok = self.priv.is_authenticated_nonblocking()
            ui(lambda: self._on_auth_change(ok))
        threading.Thread(target=worker, daemon=True).start()

    def _toggle_auth(self):
        if self._authed:
            self._logout()
        elif self.priv.ensure(self):
            self.set_status("Angemeldet – sudo-Sitzung aktiv.")

    @staticmethod
    def _device_state():
        try:
            blocks = sorted(os.listdir("/sys/block"))
        except Exception:
            blocks = []
        sizes = []
        for b in blocks:
            try:
                with open(f"/sys/block/{b}/size") as f:
                    sizes.append(f.read().strip())
            except Exception:
                sizes.append("")
        try:
            with open("/proc/self/mounts") as f:
                mounts = f.read()
        except Exception:
            mounts = ""
        return tuple(blocks), tuple(sizes), mounts

    def _check_devices(self):
        self.pages["disks"]._check_usb()
        state = self._device_state()
        if state == self._dev_state:
            return
        old_blocks = set(self._dev_state[0])
        self._dev_state = state
        added = [b for b in state[0] if b not in old_blocks and not b.startswith(("loop", "zram", "ram"))]
        if added:
            self.set_status("Neues Laufwerk erkannt: " + ", ".join("/dev/" + b for b in added))
        self.pages["disks"].refresh()
        self.pages["storage"].refresh_fs()

    def show_sys_updates(self, n, important):
        """Anzahl offener System-Updates: Hinweis unten rechts + Zahl am Tab „Updates“."""
        self._sys_updates = (n, important)
        if n:
            self.sys_hint.setText(f"{'▲' if important else '●'}  {n} System-Update{'s' if n != 1 else ''}"
                                  + (f" · {important} wichtig" if important else ""))
            self.sys_hint.setProperty("tone", "danger" if important else "warn")
            repolish(self.sys_hint)
            self.sys_hint.show()
        else:
            self.sys_hint.hide()
        tabs = getattr(self, "tabs", None)
        if tabs:
            i = [m[0] for m in MODULES].index("update")
            tabs[i].text.setText("Updates" + (f"  {n}" if n else ""))

    def show_update_hint(self, ver):
        if ver:
            self.upd_hint.setText(f"⬆  Version {ver} verfügbar")
            self.upd_hint.show()
        else:
            self.upd_hint.hide()

    def restart(self):
        """Tuxdex neu starten (nach einem Update)."""
        exe = "/usr/bin/tuxdex" if SYSTEM_INSTALL and os.path.exists("/usr/bin/tuxdex") else None
        args = [exe] if exe else [sys.executable, os.path.abspath(__file__)]
        from PySide6.QtCore import QProcess
        QProcess.startDetached(args[0], args[1:])
        QApplication.quit()

    def open_settings(self):
        if self.stack.currentWidget() is self.settings_page:
            self.back_from_settings()
            return
        self.stack.setCurrentWidget(self.settings_page)
        self.gear.setChecked(True)
        for t in self.tabs:
            t.set_selected(False)

    def back_from_settings(self):
        self.select(self._last_tab)

    def select(self, idx):
        self._last_tab = idx
        self.gear.setChecked(False)
        self.stack.setCurrentIndex(idx)
        if MODULES[idx][0] == "disks":
            self.pages["disks"].refresh()
        for i, t in enumerate(self.tabs):
            t.set_selected(i == idx)

    def _on_auth_change(self, ok):
        if ok == self._authed:
            return
        self._authed = ok
        if ok:
            self.auth_badge.set("ok", "Angemeldet – sudo-Sitzung aktiv")
            self.auth_btn.setText("Abmelden")
            self.auth_btn.setProperty("variant", "ghost")
        else:
            self.auth_badge.set("off", "Nicht angemeldet")
            self.auth_btn.setText("Anmelden")
            self.auth_btn.setProperty("variant", "primary")
        repolish(self.auth_btn)

    def _logout(self):
        self.priv.logout()
        self.set_status("Sudo-Sitzung beendet.")

    def set_status(self, text):
        self.status.setText(text)


def main():
    global _INVOKER
    app = QApplication(sys.argv)
    app.setApplicationName("Tuxdex")
    app.setApplicationDisplayName("Tuxdex")
    app.setDesktopFileName(APP_ID)          # Wayland: Taskleiste findet Icon über den Starter
    app.setWindowIcon(logo_icon())          # X11 + Fenster-/Dialog-Icons
    setup_icon_theme()
    migrate_legacy()
    install_desktop_entry()
    _INVOKER = _Invoker()
    apply_theme(app)
    win = MainWindow()
    win.setFocusPolicy(Qt.ClickFocus)
    win.show()
    win.setFocus()
    return app.exec()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        _show_fatal_error("Tuxdex - Fehler", str(e))
        sys.exit(1)
