# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for OnlyLauncher.

Two layouts are produced from this spec, selected by ``ONLYLAUNCHER_MODE``:

* ``onedir`` (default): ``dist/onedir/OnlyLauncher/`` — the folder packed into
  the AppImage. Startup is fast because nothing is extracted at runtime.
* ``onefile``: ``dist/onefile/OnlyLauncher`` — a single self-extracting binary.

Everything the launcher reads at runtime is embedded: the ``images`` folder,
the ``switchs`` pictures, the two HTML fragments and the Qt login helper
script, which the frozen binary executes itself through the runtime hook.

The build is driven by ``packaging/build_release.py``; the environment
variables below are the only interface between the two.
"""

import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = os.path.dirname(SPECPATH)
MC_DIR = os.path.join(ROOT, "mcLaunch")

MODE = os.environ.get("ONLYLAUNCHER_MODE", "onedir").strip().lower()
NAME = os.environ.get("ONLYLAUNCHER_NAME", "OnlyLauncher")
CONSOLE = os.environ.get("ONLYLAUNCHER_CONSOLE", "1").strip() != "0"
#: Optional icon (``.ico`` on Windows, ``.png``/``.icns`` elsewhere).
ICON = os.environ.get("ONLYLAUNCHER_ICON") or None
if ICON and not os.path.isfile(ICON):
    print(f"[spec] icone ignoree (introuvable): {ICON}")
    ICON = None

ONEFILE = MODE == "onefile"

#: Files read at runtime with paths relative to the script that reads them.
datas = [
    (os.path.join(MC_DIR, "mcfrheaders.html"), "."),
    # Started as a subprocess by McOptions: it must be a real file on disk.
    (os.path.join(MC_DIR, "portablemc_login.py"), "."),
]

#: ``cache.html`` is the offline fallback for the news tab. It is a *cache*:
#: git-ignored, and therefore absent from a clean CI checkout. Embed it only
#: when it happens to exist, so the build never fails on it — at runtime
#: NewsFrame falls back to the live download and writes its own copy.
_CACHE_HTML = os.path.join(MC_DIR, "cache.html")
if os.path.isfile(_CACHE_HTML):
    datas.append((_CACHE_HTML, "."))
else:
    print("[spec] cache.html absent : l'onglet Actualites le telechargera")

#: ``images`` is loaded with ``os.path.dirname(__file__)``. The GIMP sources
#: (``.xcf``) and the unused ``.webp`` stay out of the bundle: 11 MB saved.
for _entry in sorted(os.listdir(os.path.join(MC_DIR, "images"))):
    if os.path.splitext(_entry)[1].lower() in (".xcf", ".webp"):
        continue
    datas.append((os.path.join(MC_DIR, "images", _entry), "images"))

#: ``switchs`` loads its pictures with ``os.path.dirname(__file__)``.
for _entry in sorted(os.listdir(os.path.join(MC_DIR, "switchs"))):
    if _entry.endswith(".png"):
        datas.append((os.path.join(MC_DIR, "switchs", _entry), "switchs"))

#: TkinterWeb ships HTML/JS resources next to its modules.
datas += collect_data_files("tkinterweb")

#: Portable Git (MinGit) is a *build-time* dependency only: pip needs a ``git``
#: binary to install the project fork
#: (``git+https://github.com/pi-dev500/portablemc.git``). It is never embedded
#: into the produced executable, so nothing from ``packaging/gitwin`` is added
#: to ``datas`` here.

hiddenimports = [
    # PIL/ImageTk: ``_imagingtk`` (a C extension) imports ``PIL._tkinter_finder``
    # from its own init function, and ``ImageTk`` imports ``_imagingtk`` lazily
    # inside ``_pyimagingtkcall``. Static analysis sees neither, so the frozen
    # app crashed with "No module named 'PIL._tkinter_finder'". Note that
    # PyInstaller's hook-PIL excludes tkinter, hence the explicit entries.
    "PIL.ImageTk",
    "PIL._imagingtk",
    "PIL._tkinter_finder",
    # bs4 picks its parser at runtime.
    "lxml",
    "lxml.etree",
    "lxml._elementpath",
    "bs4.builder._lxml",
    # Imported only by portablemc_login.py, which the launcher never imports
    # (it runs as a subprocess): declare them explicitly.
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "PyQt6.QtWidgets",
    "PyQt6.QtNetwork",
    "PyQt6.QtWebEngineCore",
    "PyQt6.QtWebEngineWidgets",
    "tkinterweb",
    "tkinterweb_tkhtml",
]
hiddenimports += collect_submodules("portablemc")

#: Python modules the launcher never touches.
excludes = [
    "PyQt6.Qt3DAnimation",
    "PyQt6.Qt3DCore",
    "PyQt6.Qt3DExtras",
    "PyQt6.Qt3DInput",
    "PyQt6.Qt3DLogic",
    "PyQt6.Qt3DRender",
    "PyQt6.QtBluetooth",
    "PyQt6.QtCharts",
    "PyQt6.QtDataVisualization",
    "PyQt6.QtDesigner",
    "PyQt6.QtHelp",
    "PyQt6.QtNfc",
    "PyQt6.QtPositioning",
    "PyQt6.QtSerialPort",
    "PyQt6.QtSql",
    "PyQt6.QtTest",
    "PyQt6.QtTextToSpeech",
    "pydoc_data",
    "tkinter.test",
]

a = Analysis(
    [os.path.join(MC_DIR, "__main__.py")],
    pathex=[MC_DIR],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[os.path.join(SPECPATH, "rthook_login_subprocess.py")],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

#: QML modules shipped by Qt that neither the launcher nor QtWebEngineWidgets
#: ever load (3D, charts, KDE/Plasma desktop, test tooling...). Removing them
#: keeps the AppImage several tens of megabytes smaller.
UNUSED_QML = (
    "QtQuick3D/",
    "QtCharts/",
    "QtGraphs/",
    "QtGraphs2D/",
    "QtTest/",
    "QtSensors/",
    "QtTextToSpeech/",
    "QtLocation/",
    "QtMultimedia/",
    "QtPdf/",
    "QtWayland/",
    "QtWebView/",
    "QtQuick/VirtualKeyboard/",
    "QtQuick/Pdf/",
    "org/kde/",
    "Quickshell/",
    "SddmComponents/",
    "QML/",
    "QmlTime/",
)


def _keep_data(entry):
    """Return False for QML modules listed in ``UNUSED_QML``."""
    dest = str(entry[0]).replace("\\", "/")
    if "qml/" in dest:
        tail = dest.split("qml/", 1)[1]
        return not any(tail.startswith(prefix) for prefix in UNUSED_QML)
    return True


a.datas = [entry for entry in a.datas if _keep_data(entry)]

pyz = PYZ(a.pure)

if ONEFILE:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name=NAME,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=CONSOLE,
        disable_windowed_traceback=False,
        runtime_hooks=None,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=ICON,
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name=NAME,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=CONSOLE,
        disable_windowed_traceback=False,
        runtime_hooks=None,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=ICON,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name=NAME,
    )
