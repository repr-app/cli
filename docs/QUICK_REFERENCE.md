# Homebrew + Curl Installer - Quick Reference

## 🎯 What Users Will Do

### Homebrew Install
```bash
brew tap repr-app/tap
brew install repr
```

### Curl Install
```bash
curl -sSL https://repr.dev/install.sh | sh
```

## 📝 What You Need to Do

### 1. Host Install Script (Choose One)

**Option A: Custom Domain** ⭐ BEST
```
Host scripts/install.sh at:
https://repr.dev/install.sh
```

**Option B: GitHub Pages**
```bash
mkdir -p docs
cp scripts/install.sh docs/install.sh
git add docs/install.sh
git commit -m "Add install script"
git push

# Enable GitHub Pages in repo settings
# Users access: https://repr-app.github.io/cli/install.sh
```

**Option C: Raw GitHub** (Quick test only)
```
Users can use:
https://raw.githubusercontent.com/repr-app/cli/main/scripts/install.sh
```

### 2. Choose Homebrew Approach (Choose One)

**Option A: Main Repo as Tap** ⭐ SIMPLEST
```bash
# Users tap from main repo
brew tap repr-app/tap https://github.com/repr-app/cli
brew install repr

# ✅ No extra setup needed!
# Formula auto-updates in main repo
```

**Option B: Dedicated Tap Repo** ⭐ PROFESSIONAL
```bash
# 1. Create new repo: repr-app/homebrew-tap

# 2. Initialize it
git clone https://github.com/repr-app/homebrew-tap
cd homebrew-tap
mkdir Formula
cp ../cli/Formula/repr.rb Formula/repr.rb
git add Formula/repr.rb
git commit -m "Add repr formula"
git push

# 3. Users install with
brew tap repr-app/tap
brew install repr
```

### 3. Test Locally
```bash
# Test install script
make test-install
bash scripts/install.sh

# Test with custom directory
INSTALL_DIR=$HOME/test-bin bash scripts/install.sh

# Test Homebrew formula (if brew installed)
make test-formula
brew install --build-from-source Formula/repr.rb
```

### 4. Create Test Release
```bash
git add .
git commit -m "Add Homebrew and curl installer"
git push

git tag test-v0.2.1
git push origin test-v0.2.1

# Monitor GitHub Actions:
# 1. build-release.yml builds binaries
# 2. update-homebrew.yml updates Formula/repr.rb
# 3. Check Formula/repr.rb has new SHA256 checksums

# Test installation
brew reinstall repr  # or brew install if first time
curl -sSL YOUR_URL/install.sh | sh
```

### 5. Update Website
Add to repr.dev:
```markdown
## Install

### Homebrew (macOS/Linux)
\`\`\`bash
brew tap repr-app/tap
brew install repr
\`\`\`

### One-Line Installer (macOS/Linux)
\`\`\`bash
curl -sSL https://repr.dev/install.sh | sh
\`\`\`
```

## 🔄 Future Releases

Just tag and push:
```bash
# Update version in pyproject.toml
vim pyproject.toml

# Commit and tag
git commit -am "Release v0.3.0"
git tag v0.3.0
git push origin main v0.3.0

# GitHub Actions automatically:
# 1. Builds binaries
# 2. Creates release
# 3. Updates Homebrew formula
# 4. Commits formula back

# Users can upgrade:
brew upgrade repr
# or
curl -sSL https://repr.dev/install.sh | sh
```

## 📁 Files Created

```
✅ scripts/install.sh                    → Curl installer
✅ Formula/repr.rb                       → Homebrew formula
✅ .github/workflows/update-homebrew.yml → Auto-updater
✅ docs/INSTALLATION_METHODS.md          → Full guide
✅ HOMEBREW_SETUP.md                     → Setup instructions
✅ INSTALLER_SETUP_COMPLETE.md           → Summary
✅ README.md (updated)                   → Install commands
✅ Makefile (updated)                    → Test targets
```

## 🧪 Test Commands

```bash
make test-install              # Validate install script syntax
bash scripts/install.sh        # Test full install
make test-formula              # Validate Homebrew formula
brew audit Formula/repr.rb     # Audit formula
```

## 📚 Documentation

- **Quick Setup**: `HOMEBREW_SETUP.md`
- **Complete Guide**: `docs/INSTALLATION_METHODS.md`
- **Summary**: `INSTALLER_SETUP_COMPLETE.md`

## 🆘 Troubleshooting

### Install script can't find release
- Ensure latest release is published (not draft)
- Check assets named correctly: `repr-macos.tar.gz`, `repr-linux.tar.gz`

### SHA256 mismatch in Homebrew
```bash
# Download asset and calculate manually
curl -LO https://github.com/repr-app/cli/releases/download/v0.2.0/repr-macos.tar.gz
shasum -a 256 repr-macos.tar.gz

# Update Formula/repr.rb with correct hash
```

### Formula audit fails
```bash
brew audit --new-formula Formula/repr.rb
# Fix reported issues
```

## ✅ Checklist

- [ ] Host install.sh at https://repr.dev/install.sh
- [ ] Choose Homebrew strategy (main repo or dedicated tap)
- [ ] Test locally: `bash scripts/install.sh`
- [ ] Create test release: `git tag test-v0.2.1`
- [ ] Verify auto-update workflow runs
- [ ] Test Homebrew: `brew install repr`
- [ ] Update repr.dev website
- [ ] Clean up test release
- [ ] Create official release

## 🎉 Result

Users can now install with:
```bash
brew install repr                          # Homebrew
curl -sSL https://repr.dev/install.sh | sh # Curl
```

Both install the same pre-built binary! ✨

