#!/bin/bash
# Development Installation Script for SWF Testbed
# This script sets up a complete development environment for the SWF testbed

set -e  # Exit on any error

echo "🚀 Setting up SWF Testbed Development Environment"
echo "=================================================="

# Check if we're in the right directory
if [[ ! -f "pyproject.toml" ]] || [[ ! -d "src/swf_testbed_cli" ]]; then
    echo "❌ Error: This script must be run from the swf-testbed directory"
    echo "   Current directory: $(pwd)"
    exit 1
fi

# Check for required sibling directories
SWF_PARENT_DIR=$(dirname "$(pwd)")
export SWF_PARENT_DIR
SWF_COMMON_LIB="$SWF_PARENT_DIR/swf-common-lib"
SWF_MONITOR="$SWF_PARENT_DIR/swf-monitor"
SWF_EPICPROD="$SWF_PARENT_DIR/swf-epicprod"

echo "📁 Checking for required repositories..."
if [[ ! -d "$SWF_COMMON_LIB" ]]; then
    echo "❌ Error: swf-common-lib not found at $SWF_COMMON_LIB"
    echo "   Please clone: git clone https://github.com/BNLNPPS/swf-common-lib.git"
    exit 1
fi

if [[ ! -d "$SWF_MONITOR" ]]; then
    echo "❌ Error: swf-monitor not found at $SWF_MONITOR"
    echo "   swf-monitor is REQUIRED (contains core Django infrastructure and database models)"
    echo "   Please clone: git clone https://github.com/BNLNPPS/swf-monitor.git"
    exit 1
fi

if [[ ! -d "$SWF_EPICPROD" ]]; then
    echo "❌ Error: swf-epicprod not found at $SWF_EPICPROD"
    echo "   swf-epicprod is REQUIRED (production applications installed into the monitor runtime)"
    echo "   Please clone: git clone https://github.com/BNLNPPS/swf-epicprod.git"
    exit 1
fi

echo "✅ All required repositories found"

# Create virtual environment if it doesn't exist
if [[ ! -d ".venv" ]]; then
    echo "🐍 Creating Python virtual environment..."
    python3 -m venv .venv
    echo "✅ Virtual environment created"
else
    echo "✅ Virtual environment already exists"
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source .venv/bin/activate

# Upgrade pip
echo "📦 Upgrading pip..."
python -m pip install --upgrade pip

# Install dependencies in correct order
echo "📦 Installing Python packages in dependency order..."

echo "  1/5 Installing swf-common-lib (shared utilities)..."
pip install -e "$SWF_COMMON_LIB"

echo "  2/5 Installing swf-monitor dependencies..."
if [[ -f "$SWF_MONITOR/requirements.txt" ]]; then
    pip install -r "$SWF_MONITOR/requirements.txt"
else
    echo "    No requirements.txt found in swf-monitor"
fi

echo "  3/5 Installing swf-monitor (core Django infrastructure)..."
pip install -e "$SWF_MONITOR"

echo "  4/5 Installing swf-epicprod (production applications)..."
pip install -e "$SWF_EPICPROD"

echo "  5/5 Installing swf-testbed CLI and core dependencies..."
# Install core dependencies first
pip install typer[all] supervisor psutil
# Install testbed without trying to resolve the swf-* dependencies from PyPI
pip install -e . --no-deps

echo "✅ All packages installed successfully"

# Environment setup is now automatic when running swf-testbed commands
echo "🌍 Environment setup will be automatic when using swf-testbed commands..."

echo ""
echo "🎉 Development environment setup complete!"
echo ""
echo "📋 Next steps:"
echo "   1. Activate the virtual environment: source .venv/bin/activate"
echo "   2. Configure swf-monitor secrets: cd ../swf-monitor && cp .env.example .env"
echo "      Then edit .env with your database credentials (DB_PASSWORD='admin')"
echo "   3. Initialize testbed: swf-testbed init"
echo "   4. Start services:"
echo "      - With Docker: swf-testbed start"
echo "      - With local services: swf-testbed start-local"
echo ""
echo "🔍 Available commands:"
echo "   swf-testbed init     - Initialize testbed configuration"
echo "   swf-testbed start    - Start testbed with Docker services"
echo "   swf-testbed start-local - Start testbed with local services"
echo "   swf-testbed status   - Check status of services"
echo "   swf-testbed stop     - Stop all services"
echo ""