# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for repr CLI."""

import sys
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# Collect all data and imports for key dependencies
typer_datas, typer_binaries, typer_hiddenimports = collect_all('typer')
rich_datas, rich_binaries, rich_hiddenimports = collect_all('rich')
pygments_datas, pygments_binaries, pygments_hiddenimports = collect_all('pygments')

# Entry point script that properly imports the CLI module
entry_script = """
import sys
from repr.cli import app

if __name__ == '__main__':
    app()
"""

# Write the entry point to a temporary file
with open('_repr_entry.py', 'w') as f:
    f.write(entry_script)

a = Analysis(
    ['_repr_entry.py'],
    pathex=[],
    binaries=typer_binaries + rich_binaries + pygments_binaries,
    datas=typer_datas + rich_datas + pygments_datas,
    hiddenimports=[
        'repr',
        'repr.cli',
        'repr.api',
        'repr.auth',
        'repr.config',
        'repr.discovery',
        'repr.doctor',
        'repr.extractor',
        'repr.hooks',
        'repr.keychain',
        'repr.llm',
        'repr.openai_analysis',
        'repr.privacy',
        'repr.storage',
        'repr.templates',
        'repr.tools',
        'repr.ui',
        # Additional hidden imports that might be needed
        'httpx',
        'openai',
        'git',
        'gitdb',
        'smmap',
    ] + typer_hiddenimports + rich_hiddenimports + pygments_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude unnecessary packages to reduce size
        'tkinter',
        'matplotlib',
        'scipy',
        'numpy',
        'pandas',
        'PIL',
        'unittest',
        'test',
        'tests',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='repr',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
