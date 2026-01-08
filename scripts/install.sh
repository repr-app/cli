#!/usr/bin/env bash
# Repr CLI Installation Script
# Usage: curl -sSL https://repr.dev/install.sh | sh

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
REPO="repr-app/cli"
BINARY_NAME="repr"
INSTALL_DIR="${INSTALL_DIR:-/usr/local/bin}"

# Functions
print_header() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Repr CLI Installer"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
}

print_step() {
    echo -e "${BLUE}==>${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

detect_os() {
    local os_name
    os_name="$(uname -s)"
    
    case "$os_name" in
        Darwin*)
            echo "macos"
            ;;
        Linux*)
            echo "linux"
            ;;
        *)
            print_error "Unsupported operating system: $os_name"
            echo ""
            echo "Supported platforms:"
            echo "  - macOS (Intel/Apple Silicon)"
            echo "  - Linux (x86_64)"
            echo ""
            echo "For Windows, download from: https://github.com/$REPO/releases/latest"
            exit 1
            ;;
    esac
}

detect_arch() {
    local arch
    arch="$(uname -m)"
    
    case "$arch" in
        x86_64|amd64)
            echo "x86_64"
            ;;
        aarch64|arm64)
            echo "arm64"
            ;;
        *)
            print_warning "Unknown architecture: $arch (assuming x86_64)"
            echo "x86_64"
            ;;
    esac
}

get_latest_version() {
    local version
    version=$(curl -sSL "https://api.github.com/repos/$REPO/releases/latest" | grep '"tag_name"' | sed -E 's/.*"([^"]+)".*/\1/')
    
    if [ -z "$version" ]; then
        print_error "Failed to fetch latest version"
        exit 1
    fi
    
    echo "$version"
}

get_download_url() {
    local os=$1
    local version=$2
    
    case "$os" in
        macos)
            echo "https://github.com/$REPO/releases/download/$version/repr-macos.tar.gz"
            ;;
        linux)
            echo "https://github.com/$REPO/releases/download/$version/repr-linux.tar.gz"
            ;;
    esac
}

check_dependencies() {
    local missing_deps=()
    
    for cmd in curl tar; do
        if ! command -v "$cmd" &> /dev/null; then
            missing_deps+=("$cmd")
        fi
    done
    
    if [ ${#missing_deps[@]} -gt 0 ]; then
        print_error "Missing required dependencies: ${missing_deps[*]}"
        exit 1
    fi
}

download_and_install() {
    local os=$1
    local version=$2
    local url=$3
    local tmp_dir
    
    tmp_dir=$(mktemp -d)
    trap 'rm -rf "$tmp_dir"' EXIT
    
    print_step "Downloading Repr CLI $version for $os..."
    if ! curl -sSL "$url" -o "$tmp_dir/repr.tar.gz"; then
        print_error "Download failed"
        exit 1
    fi
    print_success "Downloaded successfully"
    
    print_step "Extracting archive..."
    if ! tar -xzf "$tmp_dir/repr.tar.gz" -C "$tmp_dir"; then
        print_error "Extraction failed"
        exit 1
    fi
    print_success "Extracted successfully"
    
    print_step "Installing to $INSTALL_DIR..."
    
    # Check if we need sudo
    if [ -w "$INSTALL_DIR" ]; then
        mv "$tmp_dir/repr" "$INSTALL_DIR/$BINARY_NAME"
        chmod +x "$INSTALL_DIR/$BINARY_NAME"
    else
        print_warning "Need elevated privileges to install to $INSTALL_DIR"
        if command -v sudo &> /dev/null; then
            sudo mv "$tmp_dir/repr" "$INSTALL_DIR/$BINARY_NAME"
            sudo chmod +x "$INSTALL_DIR/$BINARY_NAME"
        else
            print_error "sudo not found. Please run as root or install to a writable directory."
            echo ""
            echo "Example: INSTALL_DIR=\$HOME/.local/bin curl -sSL https://repr.dev/install.sh | sh"
            exit 1
        fi
    fi
    
    print_success "Installed successfully"
}

verify_installation() {
    if command -v "$BINARY_NAME" &> /dev/null; then
        local installed_version
        installed_version=$("$BINARY_NAME" --version 2>&1 || echo "unknown")
        print_success "Repr CLI is ready to use!"
        echo ""
        echo "Installed: $BINARY_NAME → $INSTALL_DIR/$BINARY_NAME"
        return 0
    else
        print_warning "Installation complete, but 'repr' is not in PATH"
        echo ""
        echo "Add to PATH by running:"
        echo "  export PATH=\"$INSTALL_DIR:\$PATH\""
        echo ""
        echo "Or add this line to your shell config (~/.bashrc, ~/.zshrc, etc.):"
        echo "  export PATH=\"$INSTALL_DIR:\$PATH\""
        return 1
    fi
}

print_usage() {
    echo ""
    echo "Quick Start:"
    echo "  repr login              # Authenticate with repr.dev"
    echo "  repr analyze ~/code     # Analyze your repositories"
    echo "  repr --help             # Show all commands"
    echo ""
    echo "Documentation: https://repr.dev/docs"
    echo "Report issues: https://github.com/$REPO/issues"
    echo ""
}

# Main installation flow
main() {
    print_header
    
    # Detect system
    print_step "Detecting system..."
    OS=$(detect_os)
    ARCH=$(detect_arch)
    print_success "Detected: $OS ($ARCH)"
    
    # Check dependencies
    print_step "Checking dependencies..."
    check_dependencies
    print_success "All dependencies found"
    
    # Get latest version
    print_step "Fetching latest version..."
    VERSION=$(get_latest_version)
    print_success "Latest version: $VERSION"
    
    # Get download URL
    DOWNLOAD_URL=$(get_download_url "$OS" "$VERSION")
    
    # Download and install
    download_and_install "$OS" "$VERSION" "$DOWNLOAD_URL"
    
    # Verify installation
    echo ""
    verify_installation
    
    # Print usage
    print_usage
}

# Handle script arguments
case "${1:-}" in
    --help|-h)
        echo "Repr CLI Installer"
        echo ""
        echo "Usage:"
        echo "  curl -sSL https://repr.dev/install.sh | sh"
        echo ""
        echo "Options:"
        echo "  INSTALL_DIR   Set custom installation directory (default: /usr/local/bin)"
        echo ""
        echo "Examples:"
        echo "  # Install to default location"
        echo "  curl -sSL https://repr.dev/install.sh | sh"
        echo ""
        echo "  # Install to custom location"
        echo "  INSTALL_DIR=\$HOME/.local/bin curl -sSL https://repr.dev/install.sh | sh"
        exit 0
        ;;
    --version|-v)
        VERSION=$(get_latest_version)
        echo "$VERSION"
        exit 0
        ;;
    *)
        main
        ;;
esac






































