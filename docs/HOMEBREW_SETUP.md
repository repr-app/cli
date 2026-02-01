# Quick Setup: Homebrew + Curl Installer

This guide will help you set up both Homebrew tap and curl installer for your repr CLI.

## ✅ What Was Created

1. **Curl Installer** (`scripts/install.sh`)
   - Detects OS and architecture
   - Downloads latest release
   - Installs to `/usr/local/bin` or custom location
   - Verifies installation

2. **Homebrew Formula** (`Formula/repr.rb`)
   - Formula template for Homebrew
   - Auto-updates on releases

3. **Auto-Update Workflow** (`.github/workflows/update-homebrew.yml`)
   - Automatically updates formula on new releases
   - Calculates SHA256 checksums
   - Commits updated formula

4. **Documentation** (`docs/INSTALLATION_METHODS.md`)
   - Complete setup guide
   - User documentation
   - Troubleshooting tips

## 🚀 Setup Steps

### Step 1: Host the Install Script

You need to make `scripts/install.sh` accessible at `https://repr.dev/install.sh`.

#### Option A: Custom Domain (repr.dev)

Add to your website's nginx config or static file hosting:

```nginx
location /install.sh {
    alias /path/to/cli/scripts/install.sh;
    add_header Content-Type "text/plain; charset=utf-8";
    add_header Access-Control-Allow-Origin "*";
}
```

#### Option B: GitHub Pages (Temporary)

```bash
# In your cli repo
mkdir -p docs
cp scripts/install.sh docs/install.sh
git add docs/install.sh
git commit -m "Add install script for GitHub Pages"
git push

# Enable GitHub Pages in repo settings → Pages → Source: docs/
# Access at: https://repr-app.github.io/cli/install.sh
```

Update README to use: `curl -sSL https://repr-app.github.io/cli/install.sh | sh`

#### Option C: Use Raw GitHub URL (Quick Test)

Users can use directly:
```bash
curl -sSL https://raw.githubusercontent.com/repr-app/cli/main/scripts/install.sh | sh
```

### Step 2: Test the Curl Installer

```bash
# Test locally first
bash scripts/install.sh

# Test from hosted URL
curl -sSL https://repr.dev/install.sh | bash -x

# Test with custom directory
INSTALL_DIR=$HOME/test-bin curl -sSL https://repr.dev/install.sh | sh
```

### Step 3: Set Up Homebrew

#### Choose Your Approach:

**Option A: Use Main Repo as Tap (Simpler)**

Users install with:
```bash
brew tap repr-app/tap https://github.com/repr-app/cli
brew install repr
```

✅ No extra setup needed - you're done!

**Option B: Create Dedicated Tap Repo (Recommended)**

1. **Create new GitHub repository**: `repr-app/homebrew-tap`

2. **Initialize it:**
```bash
git clone https://github.com/repr-app/homebrew-tap
cd homebrew-tap

# Copy formula
mkdir Formula
cp ../cli/Formula/repr.rb Formula/repr.rb

# Commit
git add Formula/repr.rb
git commit -m "Add repr formula"
git push origin main
```

3. **Users install with:**
```bash
brew tap repr-app/tap
brew install repr
```

4. **Set up auto-sync** (optional):

Create `.github/workflows/sync.yml` in the tap repo:

```yaml
name: Sync Formula

on:
  repository_dispatch:
    types: [formula-update]
  schedule:
    - cron: '0 */6 * * *'  # Every 6 hours
  workflow_dispatch:

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Sync from main repo
        run: |
          curl -sSL https://raw.githubusercontent.com/repr-app/cli/main/Formula/repr.rb \
            -o Formula/repr.rb
      
      - name: Commit if changed
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add Formula/repr.rb
          git diff --staged --quiet || {
            git commit -m "Sync repr formula from main repo"
            git push
          }
```

### Step 4: Test Homebrew Installation

```bash
# If using main repo as tap
brew tap repr-app/tap https://github.com/repr-app/cli
brew install repr

# If using dedicated tap
brew tap repr-app/tap
brew install repr

# Test
repr --help
repr config --json

# Uninstall
brew uninstall repr
brew untap repr-app/tap
```

### Step 5: Create a Test Release

This will trigger the auto-update workflow:

```bash
# Make sure changes are committed
git add .
git commit -m "Add Homebrew and curl installer support"
git push

# Create test release
git tag test-v0.2.1
git push origin test-v0.2.1
```

Monitor:
1. GitHub Actions should run `update-homebrew.yml`
2. `Formula/repr.rb` should be updated with SHA256s
3. Test Homebrew install: `brew reinstall repr`

### Step 6: Update Documentation

Add to your website/docs:

```markdown
## Quick Install

### Homebrew (macOS/Linux)
\`\`\`bash
brew tap repr-app/tap
brew install repr
\`\`\`

### One-Line Installer (macOS/Linux)
\`\`\`bash
curl -sSL https://repr.dev/install.sh | sh
\`\`\`

### Windows
Download from [releases](https://github.com/repr-app/cli/releases/latest)
```

## 📋 Checklist

- [ ] Install script hosted at `https://repr.dev/install.sh`
- [ ] Test curl installer works
- [ ] Decide on Homebrew approach (main repo vs dedicated tap)
- [ ] Test Homebrew installation
- [ ] Create test release to verify auto-update
- [ ] Update README and website with install commands
- [ ] Clean up test release after verification

## 🔧 Maintenance

### When Releasing New Versions

1. Update `pyproject.toml` version
2. Create and push tag: `git tag v0.3.0 && git push origin v0.3.0`
3. GitHub Actions will:
   - Build binaries
   - Create release
   - Auto-update Homebrew formula
4. Users can upgrade: `brew upgrade repr`

### Manual Formula Update (if needed)

If auto-update fails:

```bash
# Download release assets
curl -LO https://github.com/repr-app/cli/releases/download/v0.3.0/repr-macos.tar.gz
curl -LO https://github.com/repr-app/cli/releases/download/v0.3.0/repr-linux.tar.gz

# Calculate SHA256
shasum -a 256 repr-macos.tar.gz
shasum -a 256 repr-linux.tar.gz

# Update Formula/repr.rb with:
# - New version number
# - New download URLs
# - New SHA256 checksums

git add Formula/repr.rb
git commit -m "Update formula to v0.3.0"
git push
```

## 🎯 Final Result

Users can now install with:

```bash
# Homebrew (recommended for developers)
brew install repr

# Curl (quick one-liner)
curl -sSL https://repr.dev/install.sh | sh

# Direct download (offline/air-gapped)
# Download from releases page

# Python (for Python devs)
pipx install repr-cli
```

All methods install the same pre-built binary! 🎉

## 📚 Additional Resources

- Full guide: `docs/INSTALLATION_METHODS.md`
- Homebrew docs: https://docs.brew.sh/Formula-Cookbook
- Testing: `brew audit --new-formula Formula/repr.rb`

