# PyInstaller build spec for the Task Manager desktop app.
# Build locally with:  pyinstaller task_manager.spec
# Produces a single-file, windowed Windows executable in dist/.
from PyInstaller.utils.hooks import collect_submodules

# keyring resolves its backend at runtime, and plyer picks a platform-specific
# notifier module dynamically — both need their submodules pulled in explicitly.
hiddenimports = collect_submodules("keyring.backends") + [
    "plyer.platforms.win.notification",
]

# Ship the icons alongside the code so the running app can load them.
# RELEASE_NOTES.md is bundled at the root so the post-update "What's new" popup
# can render the current version's changelog offline.
datas = [
    ("assets/icon.png", "assets"),
    ("assets/icon.ico", "assets"),
    ("assets/fonts", "assets/fonts"),  # bundled Barlow family for the UI theme
    ("RELEASE_NOTES.md", "."),
]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="TaskManager",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # unpacked: UPX-packed exes trip more AV/SmartScreen/SAC heuristics
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # windowed GUI app, no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icon.ico",
)
