#!/usr/bin/env bash
# Local build and test script for repr CLI

set -e

echo "🔨 Repr CLI - Local Build & Test Script"
echo "========================================"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check Python version
echo "📋 Checking Python version..."
PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
echo "   Python version: $PYTHON_VERSION"

if ! python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"; then
    echo -e "${RED}❌ Python 3.10+ required${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Python version OK${NC}"
echo ""

# Install dependencies
echo "📦 Installing dependencies..."
python3 -m pip install --upgrade pip > /dev/null 2>&1
pip install pyinstaller > /dev/null 2>&1
pip install -e . > /dev/null 2>&1
echo -e "${GREEN}✓ Dependencies installed${NC}"
echo ""

# Build binary
echo "🏗️  Building binary with PyInstaller..."
if [ -f "repr.spec" ]; then
    pyinstaller repr.spec --clean
else
    echo -e "${YELLOW}⚠️  repr.spec not found, using inline build${NC}"
    pyinstaller --onefile \
        --name repr \
        --console \
        --hidden-import=repr \
        --collect-all=typer \
        --collect-all=rich \
        --collect-all=pygments \
        repr/cli.py
fi
echo -e "${GREEN}✓ Binary built${NC}"
echo ""

# Test binary
echo "🧪 Testing binary..."
if [ ! -f "dist/repr" ]; then
    echo -e "${RED}❌ Binary not found in dist/repr${NC}"
    exit 1
fi

chmod +x dist/repr

echo "   Running: ./dist/repr --help"
if ./dist/repr --help > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Binary works!${NC}"
else
    echo -e "${RED}❌ Binary failed${NC}"
    exit 1
fi
echo ""

# Show binary info
echo "📊 Binary Information:"
echo "   Location: $(pwd)/dist/repr"
echo "   Size: $(du -h dist/repr | cut -f1)"
echo "   Type: $(file dist/repr | cut -d: -f2)"
echo ""

# Package binary
echo "📦 Creating distribution archive..."
cd dist
tar -czf repr-local.tar.gz repr
cd ..
echo -e "${GREEN}✓ Archive created: dist/repr-local.tar.gz${NC}"
echo ""

# Final instructions
echo "🎉 Build complete!"
echo ""
echo "To test the binary:"
echo "  ./dist/repr --help"
echo "  ./dist/repr config --json"
echo ""
echo "To install locally:"
echo "  sudo cp dist/repr /usr/local/bin/"
echo ""
echo "Distribution archive:"
echo "  dist/repr-local.tar.gz"
echo ""

