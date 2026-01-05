# CI/CD and Release Process

This document describes the automated build and release process for the repr CLI.

## Overview

The project uses GitHub Actions to automatically build cross-platform binaries for every tagged release.

## Build Matrix

| Platform | Runner | Output Format | Notes |
|----------|--------|---------------|-------|
| macOS (Intel/M1) | `macos-latest` | `.tar.gz` binary | Universal binary |
| Linux (Ubuntu) | `ubuntu-latest` | `.tar.gz` binary + `.deb` package | Also creates DEB package |
| Windows | `windows-latest` | `.exe` | Standalone executable |

## Automated Workflow

### Trigger Methods

1. **Tag Push** (Recommended):
   ```bash
   git tag v0.2.0
   git push origin v0.2.0
   ```

2. **Manual Trigger**:
   - Go to Actions tab on GitHub
   - Select "Build and Release" workflow
   - Click "Run workflow"

### Build Process

The workflow performs the following steps for each platform:

1. **Setup**:
   - Checkout code
   - Set up Python 3.11
   - Install dependencies and PyInstaller

2. **Build**:
   - Create standalone binary using PyInstaller
   - Bundle all dependencies (typer, rich, pygments, etc.)
   - Test binary with `--help` command

3. **Package**:
   - macOS/Linux: Create `.tar.gz` archive
   - Windows: Keep as `.exe`
   - Linux: Also create `.deb` package

4. **Upload**:
   - Upload artifacts for download
   - If triggered by tag, create GitHub release with all binaries

### Artifacts

After a successful build, the following artifacts are available:

- `repr-macos.tar.gz` - macOS binary (Intel + Apple Silicon)
- `repr-linux.tar.gz` - Linux binary (x86_64)
- `repr-windows.exe` - Windows executable
- `repr-cli.deb` - Debian package for Ubuntu/Debian

## Local Build

You can build binaries locally for testing:

### Using Make

```bash
# Install dependencies
make install-dev

# Build binary for your platform
make build-binary

# Binary will be in dist/repr (or dist/repr.exe on Windows)
```

### Using PyInstaller Directly

```bash
pip install pyinstaller
pyinstaller repr.spec
```

### Test Local Build

```bash
# Unix
./dist/repr --help
./dist/repr analyze ~/code --offline

# Windows
dist\repr.exe --help
```

## Creating a Release

### Step 1: Update Version

Update version in `pyproject.toml`:

```toml
[project]
version = "0.2.0"
```

### Step 2: Commit and Tag

```bash
git add pyproject.toml
git commit -m "Release v0.2.0"
git tag -a v0.2.0 -m "Release version 0.2.0"
git push origin main
git push origin v0.2.0
```

### Step 3: Monitor Build

1. Go to the Actions tab in GitHub repository
2. Watch the "Build and Release" workflow
3. All platform builds should succeed (~5-10 minutes)

### Step 4: Verify Release

1. Check the Releases page
2. Download and test binaries for each platform
3. Verify release notes are generated

## Installation Instructions for Users

### macOS

```bash
# Download and extract
curl -L https://github.com/repr-app/cli/releases/latest/download/repr-macos.tar.gz -o repr-macos.tar.gz
tar -xzf repr-macos.tar.gz

# Move to PATH
sudo mv repr /usr/local/bin/
chmod +x /usr/local/bin/repr

# Verify
repr --help
```

### Linux

**Using binary:**

```bash
# Download and extract
curl -L https://github.com/repr-app/cli/releases/latest/download/repr-linux.tar.gz -o repr-linux.tar.gz
tar -xzf repr-linux.tar.gz

# Move to PATH
sudo mv repr /usr/local/bin/
chmod +x /usr/local/bin/repr

# Verify
repr --help
```

**Using DEB package:**

```bash
# Download
curl -L https://github.com/repr-app/cli/releases/latest/download/repr-cli.deb -o repr-cli.deb

# Install
sudo dpkg -i repr-cli.deb

# Verify
repr --help
```

### Windows

1. Download `repr-windows.exe` from the latest release
2. Rename to `repr.exe`
3. Move to a directory in your PATH (e.g., `C:\Windows\System32` or create `C:\Program Files\repr\`)
4. Open Command Prompt or PowerShell and run: `repr --help`

## Troubleshooting

### Build Fails

1. Check GitHub Actions logs for error details
2. Common issues:
   - Missing Python dependencies: Update `pyproject.toml`
   - Hidden imports: Add to `repr.spec` file
   - Runtime errors: Test locally first

### Binary Doesn't Run

**macOS: "Cannot be opened because the developer cannot be verified"**

```bash
xattr -cr /usr/local/bin/repr
```

**Linux: Permission denied**

```bash
chmod +x repr
```

**Windows: SmartScreen warning**

Click "More info" → "Run anyway" (first time only)

### Large Binary Size

PyInstaller bundles Python + all dependencies. Typical sizes:
- macOS: ~15-25 MB
- Linux: ~15-20 MB
- Windows: ~15-25 MB

To reduce size:
- Exclude unnecessary packages in `repr.spec`
- Use UPX compression (already enabled)

## Development

### Testing Changes to Workflow

1. Create a branch
2. Modify `.github/workflows/build-release.yml`
3. Push and create a test tag: `git tag test-v0.1.0`
4. Monitor Actions tab
5. Delete test tag and release after verification

### Adding Dependencies

When adding new Python dependencies:

1. Add to `pyproject.toml` dependencies
2. Test local build: `make build-binary`
3. If build fails with import errors, add hidden imports to `repr.spec`
4. Test the binary works: `./dist/repr --help`

### Platform-Specific Code

If adding platform-specific code:
- Test on all platforms or use `sys.platform` checks
- The CI will catch cross-platform issues

## PyPI Release (Optional)

For users who prefer `pip install`, you can still publish to PyPI:

```bash
# Build wheel
make build

# Upload to PyPI (requires credentials)
python3 -m twine upload dist/*
```

Users can then install via:
```bash
pipx install repr-cli
```

## References

- GitHub Actions: `.github/workflows/build-release.yml`
- PyInstaller spec: `repr.spec`
- Build commands: `Makefile`
- Package config: `pyproject.toml`

