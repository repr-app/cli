# 🚀 Quick Start: Test Your New CI/CD Setup

Follow these steps to verify your GitHub Actions setup is working correctly.

## Prerequisites

- [ ] Code is pushed to GitHub repository
- [ ] GitHub Actions are enabled (Settings → Actions → General)
- [ ] Repository has write permissions for Actions

## Step 1: Test Local Build (5 minutes)

First, verify the build works locally:

### On macOS/Linux:

```bash
cd /Users/mendrika/Projects/everdraft/code/repr/cli

# Run the local build script
./scripts/build-local.sh

# Test the binary
./dist/repr --help
./dist/repr config --json
```

### On Windows:

```cmd
cd C:\path\to\repr\cli

# Run the local build script
scripts\build-local.bat

# Test the binary
dist\repr.exe --help
dist\repr.exe config --json
```

**Expected result**: Binary builds successfully and responds to commands.

---

## Step 2: Push to GitHub (2 minutes)

Commit and push all the new files:

```bash
cd /Users/mendrika/Projects/everdraft/code/repr/cli

# Check what's new
git status

# Add all new files
git add .github/ docs/ scripts/ repr.spec setup.py
git add Makefile README.md .gitignore SETUP_COMPLETE.md

# Commit
git commit -m "Add GitHub Actions CI/CD workflows

- Add build-release.yml for multi-platform binaries
- Add test.yml for continuous testing
- Add build-msi.yml for optional Windows installer
- Add PyInstaller configuration (repr.spec)
- Add local build scripts for development
- Update README with binary download instructions
- Add comprehensive documentation"

# Push to main
git push origin main
```

**Expected result**: Code pushed to GitHub successfully.

---

## Step 3: Test the Test Workflow (5-10 minutes)

The test workflow should trigger automatically on push to main.

1. **Go to your repository on GitHub**
2. **Click the "Actions" tab**
3. **Find the "Test Build" workflow run**
4. **Watch it execute**

You should see:
- ✅ Matrix of 9 jobs (3 platforms × 3 Python versions)
- ✅ All jobs turn green
- ✅ Tests pass on all platforms

**If any jobs fail**: Click on the failed job to see logs, fix the issue, and push again.

---

## Step 4: Create a Test Release (10-15 minutes)

Now test the full release workflow:

### 4a. Create and Push a Test Tag

```bash
# Make sure you're on the latest main
git checkout main
git pull

# Create a test tag
git tag test-v0.1.0 -m "Test release for CI/CD validation"

# Push the tag (this triggers the build-release workflow)
git push origin test-v0.1.0
```

### 4b. Monitor the Build

1. **Go to Actions tab** in your GitHub repository
2. **Find the "Build and Release" workflow run**
3. **Watch the matrix of builds**:
   - macOS build
   - Linux build
   - Windows build
   - DEB package build
   - Release creation

**This will take 8-12 minutes total.**

### 4c. Verify the Release

1. **Go to the "Releases" page** on GitHub
2. **Find the "test-v0.1.0" release**
3. **Verify 4 assets are attached**:
   - `repr-macos.tar.gz`
   - `repr-linux.tar.gz`
   - `repr-windows.exe`
   - `repr-cli.deb`

### 4d. Test a Binary

Download and test one of the binaries:

**macOS:**
```bash
# Download
curl -L https://github.com/YOUR-USERNAME/cli/releases/download/test-v0.1.0/repr-macos.tar.gz -o test-repr.tar.gz

# Extract
tar -xzf test-repr.tar.gz

# Test
./repr --help
./repr config --json
```

**Linux:**
```bash
# Download
curl -L https://github.com/YOUR-USERNAME/cli/releases/download/test-v0.1.0/repr-linux.tar.gz -o test-repr.tar.gz

# Extract
tar -xzf test-repr.tar.gz

# Test
./repr --help
```

**Windows:**
```powershell
# Download from GitHub release page
# Run in PowerShell:
.\repr.exe --help
```

### 4e. Clean Up Test Release

After verifying everything works:

```bash
# Delete the test tag locally
git tag -d test-v0.1.0

# Delete the test tag on GitHub
git push origin :refs/tags/test-v0.1.0
```

Then manually delete the test release from the GitHub Releases page.

---

## Step 5: Create Your First Real Release (5 minutes)

Once everything is working, create your first official release:

### 5a. Update Version

Edit `pyproject.toml`:

```toml
[project]
version = "0.2.0"  # Update this
```

### 5b. Commit and Tag

```bash
# Commit version bump
git add pyproject.toml
git commit -m "Release v0.2.0"

# Create release tag
git tag v0.2.0 -m "Release version 0.2.0

Features:
- Multi-platform binary distribution
- Automated CI/CD with GitHub Actions
- Support for macOS, Linux, and Windows

Installation:
- Download pre-built binaries from releases
- Or install via: pipx install repr-cli"

# Push
git push origin main
git push origin v0.2.0
```

### 5c. Monitor and Verify

1. Wait for Actions to complete (~10 minutes)
2. Check the release is created properly
3. Download and test binaries
4. Share with users! 🎉

---

## Success Checklist

After completing all steps, verify:

- [ ] Local build script works (`./scripts/build-local.sh`)
- [ ] Local binary runs (`./dist/repr --help`)
- [ ] Code pushed to GitHub successfully
- [ ] Test workflow passes on all platforms
- [ ] Build workflow completes successfully
- [ ] Release is created with 4 binary assets
- [ ] Downloaded binary works on your platform
- [ ] Test tag/release cleaned up
- [ ] Official release created and verified

---

## 🎉 You're Done!

Your CLI now has:
- ✅ Automated multi-platform builds
- ✅ Continuous integration testing
- ✅ One-command releases
- ✅ Binary distribution for end users
- ✅ Professional documentation

## Next Steps

### For Development
- Merge PRs: Test workflow runs automatically
- Create features: Binaries rebuild on every tag
- Monitor: Check Actions tab for build status

### For Users
Update your documentation with:
```markdown
## Installation

Download pre-built binaries from the [latest release](https://github.com/YOUR-ORG/cli/releases/latest):

- **macOS**: Download `repr-macos.tar.gz`
- **Linux**: Download `repr-linux.tar.gz` or `repr-cli.deb`
- **Windows**: Download `repr-windows.exe`

No Python installation required!
```

### Optional Enhancements

Consider adding:
1. **Code Signing** - Eliminates security warnings
2. **Homebrew Formula** - Enable `brew install repr`
3. **Chocolatey Package** - Enable `choco install repr-cli`
4. **Auto-Update** - Built-in version check and update
5. **Download Statistics** - Track binary downloads

---

## Troubleshooting

### Local build fails
→ Check Python version: `python3 --version` (need 3.10+)
→ Install dependencies: `pip install -e ".[dev]"`

### GitHub Actions fails
→ Check workflow logs in Actions tab
→ Verify all files are committed and pushed
→ Check repository permissions

### Binary doesn't work
→ On macOS: Run `xattr -cr ./repr` to remove quarantine
→ On Linux: Run `chmod +x ./repr` to make executable
→ On Windows: Right-click → Properties → Unblock

### Need help?
→ Check docs: `docs/CI_CD.md`
→ See diagrams: `docs/WORKFLOW_DIAGRAM.md`
→ Read setup: `SETUP_COMPLETE.md`

---

**Happy releasing! 🚀**

