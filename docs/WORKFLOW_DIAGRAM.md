# GitHub Actions Workflow Diagram

## Release Workflow (Triggered by Version Tag)

```
Developer Actions                    GitHub Actions
─────────────────                    ──────────────

1. Update version                    
   in pyproject.toml                 
   (e.g., 0.2.0)                     
          │                          
          ▼                          
2. git commit                        
   "Release v0.2.0"                  
          │                          
          ▼                          
3. git tag v0.2.0                    
          │                          
          ▼                          
4. git push origin v0.2.0            
          │                          
          └──────────────────────────► Tag Push Detected
                                                │
                    ┌───────────────────────────┼───────────────────────────┐
                    │                           │                           │
                    ▼                           ▼                           ▼
              ┌──────────┐              ┌──────────┐              ┌──────────┐
              │  macOS   │              │  Linux   │              │ Windows  │
              │ Runner   │              │ Runner   │              │ Runner   │
              └──────────┘              └──────────┘              └──────────┘
                    │                           │                           │
                    ▼                           ▼                           ▼
           • Setup Python 3.11          • Setup Python 3.11        • Setup Python 3.11
           • Install dependencies       • Install dependencies     • Install dependencies
           • pip install pyinstaller    • pip install pyinstaller  • pip install pyinstaller
           • pip install -e .           • pip install -e .         • pip install -e .
                    │                           │                           │
                    ▼                           ▼                           ▼
           • Build with PyInstaller     • Build with PyInstaller   • Build with PyInstaller
           • pyinstaller repr.spec      • pyinstaller repr.spec    • pyinstaller repr.spec
                    │                           │                           │
                    ▼                           ▼                           ▼
           • Test binary                • Test binary              • Test binary
           • ./dist/repr --help         • ./dist/repr --help       • dist\repr.exe --help
                    │                           │                           │
                    ▼                           ▼                           ▼
           • Package as tar.gz          • Package as tar.gz        • Keep as .exe
           • tar -czf repr-macos...     • tar -czf repr-linux...   • repr-windows.exe
                    │                           │                           │
                    ▼                           ▼                           ▼
           • Upload artifact            • Upload artifact          • Upload artifact
           • repr-macos.tar.gz          • repr-linux.tar.gz        • repr-windows.exe
                    │                           │                           │
                    └───────────────────────────┼───────────────────────────┘
                                                │
                                                ▼
                                        ┌──────────────┐
                                        │ Build DEB    │
                                        │ Package Job  │
                                        └──────────────┘
                                                │
                                                ▼
                                        • Download Linux artifact
                                        • Setup Python + stdeb
                                        • python setup.py bdist_deb
                                        • Upload repr-cli.deb
                                                │
                                                ▼
                                        ┌──────────────┐
                                        │Create Release│
                                        │     Job      │
                                        └──────────────┘
                                                │
                                                ▼
                                        • Download all artifacts
                                        • Create GitHub Release
                                        • Upload binaries:
                                          - repr-macos.tar.gz
                                          - repr-linux.tar.gz
                                          - repr-windows.exe
                                          - repr-cli.deb
                                        • Generate release notes
                                                │
                                                ▼
                                        📦 Release Published!
                                                │
                                                ▼
                                    Users can download binaries
```

## Test Workflow (Triggered by PR/Push)

```
Developer Actions                    GitHub Actions
─────────────────                    ──────────────

1. Create PR or                      
   push to main                      
          │                          
          └──────────────────────────► Workflow Triggered
                                                │
                    ┌───────────────────────────┼──────────────────────────┐
                    │                           │                          │
              Platform Matrix            Python Version Matrix      Quick Tests
                    │                           │                          │
        ┌───────────┼───────────┐     ┌─────────┼─────────┐               │
        │           │           │     │         │         │               │
        ▼           ▼           ▼     ▼         ▼         ▼               ▼
     macOS       Linux      Windows  3.10     3.11      3.12         Each combo
                    │                           │                          │
                    └──────────────────┬────────┘                          │
                                       ▼                                   │
                            For each combination:                          │
                            • Install dependencies                         │
                            • Run pytest -v tests/                         │
                            • Test CLI: repr --help                        │
                            • Test CLI: repr config --json                 │
                            • PyInstaller build test (Python 3.11 only)    │
                                       │                                   │
                                       ▼                                   │
                            ✅ All tests pass → Merge allowed              │
                            ❌ Tests fail → Fix required                   │
```

## Local Build Workflow

```
Developer Machine                    Local Script
─────────────                        ────────────

1. cd repr/cli                       
          │                          
          ▼                          
2. ./scripts/build-local.sh          
   (or build-local.bat on Windows)   
          │                          
          └──────────────────────────► Script Starts
                                              │
                                              ▼
                                      • Check Python ≥ 3.10
                                              │
                                              ▼
                                      • pip install pyinstaller
                                      • pip install -e .
                                              │
                                              ▼
                                      • pyinstaller repr.spec
                                              │
                                              ▼
                                      • Test: ./dist/repr --help
                                              │
                                              ▼
                                      • tar -czf repr-local.tar.gz
                                              │
                                              ▼
                                      ✅ Binary ready in dist/
                                              │
                                              ▼
                                    Show instructions and summary
```

## Distribution Flow

```
                           ┌─────────────────┐
                           │  GitHub Release │
                           │   (automated)   │
                           └────────┬────────┘
                                    │
                  ┌─────────────────┼─────────────────┐
                  │                 │                 │
                  ▼                 ▼                 ▼
         ┌────────────────┐  ┌────────────┐  ┌────────────┐
         │ macOS Download │  │   Linux    │  │  Windows   │
         │  (tar.gz)      │  │(tar/deb)   │  │   (.exe)   │
         └────────────────┘  └────────────┘  └────────────┘
                  │                 │                 │
                  ▼                 ▼                 ▼
         • curl -L ...      • curl -L ...     • Download from
         • tar -xzf         • tar -xzf          browser
         • mv to /usr/      • dpkg -i         • Add to PATH
           local/bin        • or tar extract  
                  │                 │                 │
                  └─────────────────┼─────────────────┘
                                    │
                                    ▼
                          ✅ repr CLI Ready!
                          • No Python required
                          • Native executable
                          • Full functionality
```

## File Dependencies

```
pyproject.toml ──────┐
                     │
                     ├──► setup.py ──────► DEB Package
                     │
                     └──► repr.spec ─────► PyInstaller ──┬──► repr (macOS)
                              │                          │
                              │                          ├──► repr (Linux)
                              │                          │
                              └─► Hidden imports         └──► repr.exe (Windows)
                                  • typer
                                  • rich
                                  • pygments
                                  • all repr modules

.github/workflows/
├── build-release.yml ─────► Creates releases with binaries
├── test.yml ──────────────► Validates every PR/push
└── build-msi.yml ─────────► Optional Windows installer

Makefile ───────────────────► Local development commands
scripts/build-local.* ──────► Local testing scripts
docs/*.md ──────────────────► Documentation
```

## Timeline (Typical Release)

```
Action                          Time
──────                          ────

Push tag v0.2.0                 0 min
  │
  ├─ macOS build starts         +0 min    ─┐
  ├─ Linux build starts         +0 min     │ Parallel
  └─ Windows build starts       +0 min    ─┘
        │
        ├─ Setup (all)           1-2 min
        ├─ Build (all)           3-5 min
        └─ Test (all)            1 min
              │
              ▼
  All builds complete            5-8 min
              │
              ├─ DEB build        2-3 min
              └─ Create release   1 min
                     │
                     ▼
  Release published              8-12 min total
```

## Success Indicators

```
✅ Workflow completed          → Check Actions tab
✅ All jobs green             → No red X marks
✅ Release created            → Check Releases page
✅ 4 assets attached          → macOS, Linux, Windows, DEB
✅ Binaries tested            → Download & run --help
```

---

**Legend:**
- `│ ▼` = Sequential flow
- `┌─┼─┐` = Parallel execution
- `• Item` = Step in process
- `✅` = Success indicator
- `❌` = Failure indicator








































