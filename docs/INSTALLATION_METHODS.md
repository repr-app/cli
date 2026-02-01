# Installation Methods for Repr CLI

This document describes all available installation methods for the Repr CLI, including Homebrew tap and curl installer setup.

## For End Users

### Option 1: Homebrew (macOS/Linux)

**One-time setup** (if using from this repo directly):
```bash
brew tap repr-app/tap https://github.com/repr-app/cli
brew install repr
```

**Or use a dedicated tap repository** (recommended for production):
```bash
brew tap repr-app/tap
brew install repr
```

**Update:**
```bash
brew upgrade repr
```

**Uninstall:**
```bash
brew uninstall repr
```

### Option 2: Curl Installer (macOS/Linux)

**One-line install:**
```bash
curl -sSL https://repr.dev/install.sh | sh
```

**With custom install directory:**
```bash
INSTALL_DIR=$HOME/.local/bin curl -sSL https://repr.dev/install.sh | sh
```

**Uninstall:**
```bash
sudo rm /usr/local/bin/repr
# or
rm $HOME/.local/bin/repr
```

### Option 3: Direct Binary Download

Download from [releases page](https://github.com/repr-app/cli/releases/latest):
- macOS: `repr-macos.tar.gz`
- Linux: `repr-linux.tar.gz` or `repr-cli.deb`
- Windows: `repr-windows.exe`

### Option 4: Python Package Manager

```bash
pipx install repr-cli
# or
pip install repr-cli
```

---

## For Maintainers

### Setting Up Homebrew Tap

You have two options for Homebrew distribution:

#### Option A: Use Main Repository as Tap (Simpler)

Users can tap directly from your main CLI repository:

```bash
brew tap repr-app/tap https://github.com/repr-app/cli
brew install repr
```

**Pros:**
- No separate repository needed
- Formula auto-updates in main repo
- Simpler to maintain

**Cons:**
- Taps entire repository (includes source code)
- Less conventional for Homebrew

**Setup:**
1. Formula is already in `Formula/repr.rb`
2. GitHub Action auto-updates it on release
3. Users tap from `https://github.com/repr-app/cli`

#### Option B: Create Dedicated Homebrew Tap (Recommended for Production)

Create a separate repository called `homebrew-tap`:

**Step 1: Create new repository**
```bash
# On GitHub, create: repr-app/homebrew-tap
git clone https://github.com/repr-app/homebrew-tap
cd homebrew-tap
mkdir Formula
```

**Step 2: Copy formula**
```bash
cp ../cli/Formula/repr.rb Formula/repr.rb
git add Formula/repr.rb
git commit -m "Add repr formula"
git push origin main
```

**Step 3: Set up auto-sync (optional)**

Add this to `.github/workflows/sync-formula.yml` in the tap repo:

```yaml
name: Sync Formula from CLI Repo

on:
  repository_dispatch:
    types: [formula-update]
  workflow_dispatch:

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Download latest formula
        run: |
          curl -sSL https://raw.githubusercontent.com/repr-app/cli/main/Formula/repr.rb \
            -o Formula/repr.rb
      
      - name: Commit changes
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add Formula/repr.rb
          git diff --staged --quiet || git commit -m "Update repr formula"
          git push
```

**Step 4: Configure tap dispatch in main repo**

In `.github/workflows/update-homebrew.yml`, uncomment the dispatch section and add `TAP_REPO_TOKEN` secret.

**Users then install with:**
```bash
brew tap repr-app/tap
brew install repr
```

### Setting Up Curl Installer

The curl installer is already created at `scripts/install.sh`.

#### Host it on your website

**Option 1: Host on GitHub Pages**

1. Create a `gh-pages` branch or use `docs/` folder
2. Copy `scripts/install.sh` to `docs/install.sh`
3. Enable GitHub Pages in repo settings
4. Users can then run:
   ```bash
   curl -sSL https://repr-app.github.io/cli/install.sh | sh
   ```

**Option 2: Host on custom domain (repr.dev)**

1. Add `scripts/install.sh` to your website's static files
2. Make it accessible at `https://repr.dev/install.sh`
3. Update your web server to serve it with proper headers:
   ```
   Content-Type: text/plain; charset=utf-8
   ```

**Option 3: Use GitHub raw URL (temporary)**

```bash
curl -sSL https://raw.githubusercontent.com/repr-app/cli/main/scripts/install.sh | sh
```

#### Test the installer

```bash
# Test locally first
bash scripts/install.sh

# Test from URL (after hosting)
curl -sSL https://repr.dev/install.sh | bash -x  # -x for debug output

# Test with custom install dir
INSTALL_DIR=$HOME/test-install curl -sSL https://repr.dev/install.sh | sh
```

### Workflow Overview

When you create a new release:

1. **GitHub Actions triggers** (on tag push like `v0.2.0`)
2. **Builds binaries** for macOS, Linux, Windows
3. **Creates GitHub release** with binary assets
4. **Auto-updates Homebrew formula** with new version and SHA256s
5. **Optionally dispatches to tap repo** (if configured)

Users can then:
- `brew upgrade repr` - Gets the new version
- `curl -sSL https://repr.dev/install.sh | sh` - Gets the latest release

### Maintenance Checklist

When releasing a new version:

- [ ] Update version in `pyproject.toml`
- [ ] Create and push git tag: `git tag v0.2.0 && git push origin v0.2.0`
- [ ] Wait for GitHub Actions to complete
- [ ] Verify formula updated in `Formula/repr.rb`
- [ ] Test Homebrew install: `brew reinstall repr`
- [ ] Test curl installer: `curl -sSL URL | sh`
- [ ] Update website with new version number

### Troubleshooting

#### Homebrew formula SHA256 mismatch

If users get SHA256 errors:
1. Download the release asset manually
2. Calculate SHA256: `shasum -a 256 repr-macos.tar.gz`
3. Update `Formula/repr.rb` with correct hash
4. Commit and push

#### Curl installer can't find latest release

Check:
- GitHub release is marked as "latest" (not pre-release)
- Release assets are properly named (`repr-macos.tar.gz`, etc.)
- GitHub API is accessible: `curl https://api.github.com/repos/repr-app/cli/releases/latest`

#### Homebrew audit fails

Run locally:
```bash
brew audit --new-formula Formula/repr.rb
brew install --build-from-source Formula/repr.rb
brew test repr
```

Fix any issues and update the formula.

### Security Considerations

#### For curl installer:
- Always use HTTPS URLs
- Host on trusted domains
- Consider adding signature verification
- Users should review script before piping to shell

#### For Homebrew:
- SHA256 checksums are automatically verified
- Binaries come from GitHub releases
- Homebrew's built-in security checks apply

### Advanced: Code Signing (Optional)

To eliminate security warnings:

**macOS:**
```bash
# Sign the binary
codesign --sign "Developer ID" dist/repr

# Notarize with Apple
xcrun notarytool submit dist/repr.zip --wait
```

**Windows:**
```bash
# Sign with Authenticode
signtool sign /f cert.pfx /p password /tr http://timestamp.digicert.com dist/repr.exe
```

Update GitHub Actions to sign binaries before release.

---

## Quick Reference

| Method | Command | Best For |
|--------|---------|----------|
| **Homebrew** | `brew install repr` | macOS/Linux developers |
| **Curl** | `curl -sSL URL \| sh` | Quick one-line installs |
| **Binary** | Download + extract | Offline installs |
| **pipx** | `pipx install repr-cli` | Python developers |

## User Documentation

Add to your README.md:

```markdown
## Installation

### macOS/Linux (Homebrew)
\`\`\`bash
brew tap repr-app/tap
brew install repr
\`\`\`

### macOS/Linux (curl)
\`\`\`bash
curl -sSL https://repr.dev/install.sh | sh
\`\`\`

### Windows
Download from [releases](https://github.com/repr-app/cli/releases/latest)

### Python (cross-platform)
\`\`\`bash
pipx install repr-cli
\`\`\`
```

---

## Resources

- [Homebrew Formula Cookbook](https://docs.brew.sh/Formula-Cookbook)
- [Homebrew Acceptable Formulae](https://docs.brew.sh/Acceptable-Formulae)
- [GitHub Releases API](https://docs.github.com/en/rest/releases)








































