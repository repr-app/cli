# 🎉 Homebrew + Curl Installer Setup Complete!

## ✅ What Was Added

### 1. Curl Installer Script (`scripts/install.sh`)

A production-ready installation script with:
- ✅ OS detection (macOS, Linux)
- ✅ Architecture detection (x86_64, ARM64)
- ✅ Latest release fetching from GitHub API
- ✅ Automatic download and extraction
- ✅ Privilege handling (sudo when needed)
- ✅ Custom install directory support
- ✅ Installation verification
- ✅ Colored output and error handling
- ✅ PATH instructions

**Users can install with:**
```bash
curl -sSL https://repr.dev/install.sh | sh
```

### 2. Homebrew Formula (`Formula/repr.rb`)

A Homebrew formula template with:
- ✅ Platform-specific URLs (macOS/Linux)
- ✅ SHA256 checksums for verification
- ✅ Simple installation logic
- ✅ Built-in tests

**Users can install with:**
```bash
brew tap repr-app/tap
brew install repr
```

### 3. Auto-Update Workflow (`.github/workflows/update-homebrew.yml`)

GitHub Action that automatically:
- ✅ Triggers on new releases
- ✅ Downloads release binaries
- ✅ Calculates SHA256 checksums
- ✅ Updates Formula/repr.rb with new version
- ✅ Commits changes back to repo
- ✅ Optional: Dispatches to dedicated tap repo

### 4. Documentation

- **`docs/INSTALLATION_METHODS.md`** - Comprehensive guide for maintainers
- **`HOMEBREW_SETUP.md`** - Quick setup guide with step-by-step instructions
- **Updated `README.md`** - Added Homebrew and curl install options

### 5. Updated Makefile

Added test targets:
- `make test-install` - Validate install script syntax
- `make test-formula` - Run Homebrew formula audit

## 📊 Installation Methods Summary

| Method | Command | Best For | Pros |
|--------|---------|----------|------|
| **Homebrew** | `brew install repr` | macOS/Linux developers | Updates via brew, dependency management |
| **Curl** | `curl -sSL URL \| sh` | Quick installs | One-liner, no deps |
| **Binary** | Download from releases | Offline/airgapped | Full control, no network |
| **DEB** | `dpkg -i repr-cli.deb` | Ubuntu/Debian | System package manager |
| **pipx** | `pipx install repr-cli` | Python developers | Isolated Python env |

## 🚀 Setup Required

### Step 1: Host Install Script

Choose one option:

**Option A: Custom Domain (repr.dev)** ⭐ Recommended
```bash
# Add to your web server
# Make accessible at: https://repr.dev/install.sh
```

**Option B: GitHub Pages**
```bash
mkdir -p docs
cp scripts/install.sh docs/install.sh
# Enable GitHub Pages → docs/ folder
# Access at: https://repr-app.github.io/cli/install.sh
```

**Option C: Raw GitHub (Quick Test)**
```bash
# Users can use directly:
curl -sSL https://raw.githubusercontent.com/repr-app/cli/main/scripts/install.sh | sh
```

### Step 2: Choose Homebrew Strategy

**Option A: Main Repo as Tap** (Simpler)
- ✅ No extra repo needed
- Users: `brew tap repr-app/tap https://github.com/repr-app/cli`

**Option B: Dedicated Tap Repo** (Recommended for Production)
1. Create `repr-app/homebrew-tap` repository
2. Copy `Formula/repr.rb` to it
3. Users: `brew tap repr-app/tap`

See `HOMEBREW_SETUP.md` for detailed instructions.

### Step 3: Test Everything

```bash
# Test install script
make test-install
bash scripts/install.sh

# Test Homebrew formula (if Homebrew installed)
make test-formula

# Create test release
git tag test-v0.2.1
git push origin test-v0.2.1

# Verify auto-update workflow ran
# Check Formula/repr.rb was updated with SHA256s
```

### Step 4: Update Your Website

Add installation instructions to repr.dev:

```markdown
## Install Repr CLI

### macOS/Linux (Homebrew)
\`\`\`bash
brew tap repr-app/tap
brew install repr
\`\`\`

### macOS/Linux (Curl)
\`\`\`bash
curl -sSL https://repr.dev/install.sh | sh
\`\`\`

### Windows
Download from [releases](https://github.com/repr-app/cli/releases/latest)
```

## 🎯 User Experience

### Before (Manual Steps)
```bash
# User had to:
curl -L https://github.com/.../repr-macos.tar.gz -o repr.tar.gz
tar -xzf repr.tar.gz
sudo mv repr /usr/local/bin/
chmod +x /usr/local/bin/repr
```

### After (One Command)
```bash
# Homebrew
brew install repr

# Or curl
curl -sSL https://repr.dev/install.sh | sh
```

Much better! 🎉

## 🔄 Release Workflow

When you create a new release:

```bash
# 1. Update version
vim pyproject.toml  # version = "0.3.0"

# 2. Commit and tag
git commit -am "Release v0.3.0"
git tag v0.3.0
git push origin main v0.3.0
```

**GitHub Actions automatically:**
1. Builds binaries (macOS, Linux, Windows)
2. Creates GitHub release
3. Updates Homebrew formula with new SHA256s
4. Commits formula back to repo

**Users can upgrade:**
```bash
brew upgrade repr
# or
curl -sSL https://repr.dev/install.sh | sh
```

## 📁 File Structure

```
repr/cli/
├── .github/
│   └── workflows/
│       ├── build-release.yml       # Build binaries
│       ├── test.yml                # Run tests
│       └── update-homebrew.yml     # Auto-update formula ⭐ NEW
├── Formula/
│   └── repr.rb                     # Homebrew formula ⭐ NEW
├── scripts/
│   ├── install.sh                  # Curl installer ⭐ NEW
│   ├── build-local.sh              # Local builds
│   └── build-local.bat             # Windows builds
├── docs/
│   ├── INSTALLATION_METHODS.md     # Full guide ⭐ NEW
│   ├── CI_CD.md                    # CI/CD docs
│   └── ...
├── HOMEBREW_SETUP.md               # Quick setup ⭐ NEW
├── README.md                       # Updated ✏️
└── Makefile                        # Updated ✏️
```

## 🧪 Testing Checklist

Before going live:

- [ ] Test install script locally: `bash scripts/install.sh`
- [ ] Test install script with custom dir: `INSTALL_DIR=$HOME/test curl ... | sh`
- [ ] Validate formula syntax: `make test-formula`
- [ ] Create test release: `git tag test-v0.2.1 && git push origin test-v0.2.1`
- [ ] Verify workflow updates formula automatically
- [ ] Test Homebrew install: `brew install Formula/repr.rb`
- [ ] Test binary works: `repr --help`
- [ ] Update repr.dev with install instructions
- [ ] Clean up test release

## 🎓 Documentation

| File | Purpose |
|------|---------|
| `HOMEBREW_SETUP.md` | Quick setup guide - start here |
| `docs/INSTALLATION_METHODS.md` | Complete reference for all methods |
| `scripts/install.sh` | The actual installer (well commented) |
| `Formula/repr.rb` | Homebrew formula (simple template) |

## 🐛 Troubleshooting

### Install script fails

**Check:**
- Latest release exists and is not a pre-release
- Assets are named correctly (`repr-macos.tar.gz`, `repr-linux.tar.gz`)
- Binary is executable in the archive

**Debug:**
```bash
bash -x scripts/install.sh  # Run with debug output
```

### Homebrew SHA256 mismatch

**Fix:**
```bash
# Download asset
curl -LO https://github.com/repr-app/cli/releases/download/v0.2.0/repr-macos.tar.gz

# Calculate SHA256
shasum -a 256 repr-macos.tar.gz

# Update Formula/repr.rb with correct hash
```

### Formula audit fails

**Run:**
```bash
brew audit --new-formula Formula/repr.rb
brew install --build-from-source Formula/repr.rb
```

Fix any issues it reports.

## 🌟 Benefits

### For Users
- ✅ Multiple convenient installation methods
- ✅ No manual download/extract steps
- ✅ Automatic updates via Homebrew
- ✅ One-line installation
- ✅ Cross-platform support

### For You
- ✅ Automated formula updates on release
- ✅ Better distribution reach
- ✅ Professional installation experience
- ✅ Less support burden
- ✅ Homebrew community integration

## 📈 Next Steps

### Required
1. **Host install script** at `https://repr.dev/install.sh`
2. **Test end-to-end**: Create release, verify auto-update
3. **Update website** with new install commands

### Optional Enhancements
1. **Create dedicated tap repo** (`homebrew-tap`)
2. **Add install analytics** (track downloads)
3. **Code signing** (eliminate security warnings)
4. **Add to official Homebrew** (homebrew/core)
5. **Create Chocolatey package** (Windows package manager)
6. **Add install verification** (GPG signatures)

## 🎉 Result

Your users can now install Repr CLI with:

```bash
# Homebrew (recommended)
brew install repr

# One-liner
curl -sSL https://repr.dev/install.sh | sh
```

Both install the same high-quality, pre-built binary! 🚀

---

**Setup Status:** ✅ Complete - Ready for Testing

See `HOMEBREW_SETUP.md` for step-by-step setup instructions.

