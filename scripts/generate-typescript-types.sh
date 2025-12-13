#!/bin/bash
# Generate TypeScript types from Pydantic schemas using TypeSync
# Output: sumii-mobile-app/services/api/types.ts

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MOBILE_APP_DIR="$(cd "$PROJECT_ROOT/../sumii-mobile-app" && pwd)"
TYPESYNC_DIR="$(cd "$PROJECT_ROOT/../typesync" && pwd)"

echo "🔄 Generating TypeScript types from Pydantic schemas..."
echo "📁 Project root: $PROJECT_ROOT"
echo "📁 Mobile app: $MOBILE_APP_DIR"
echo "📁 TypeSync: $TYPESYNC_DIR"

# Check if TypeSync is installed
if [ ! -d "$TYPESYNC_DIR" ]; then
    echo "❌ Error: TypeSync not found at $TYPESYNC_DIR"
    echo "   Please ensure typesync is available in the parent directory"
    exit 1
fi

# Check if mobile app directory exists
if [ ! -d "$MOBILE_APP_DIR" ]; then
    echo "❌ Error: Mobile app directory not found at $MOBILE_APP_DIR"
    echo "   Creating directory structure..."
    mkdir -p "$MOBILE_APP_DIR/services/api"
fi

# Create output directory if it doesn't exist
mkdir -p "$MOBILE_APP_DIR/services/api"

# Activate virtual environment
if [ -d "$PROJECT_ROOT/.venv" ]; then
    echo "🐍 Activating virtual environment..."
    source "$PROJECT_ROOT/.venv/bin/activate"
elif [ -d "$TYPESYNC_DIR/.venv" ]; then
    echo "🐍 Activating TypeSync virtual environment..."
    source "$TYPESYNC_DIR/.venv/bin/activate"
else
    echo "⚠️  Warning: No virtual environment found, using system Python"
fi

# Run TypeSync
echo "🚀 Running TypeSync..."
cd "$TYPESYNC_DIR"

# Install TypeSync if needed
if ! python -c "import typesync" 2>/dev/null; then
    echo "📦 Installing TypeSync..."
    pip install -e .
fi

# Convert all schema files
echo "📝 Converting schemas..."
typesync \
    --input "$PROJECT_ROOT/app/schemas" \
    --output "$MOBILE_APP_DIR/services/api/types.ts" \
    --config "$PROJECT_ROOT/typesync.toml" \
    --naming camel_case \
    --optional

if [ $? -eq 0 ]; then
    echo "✅ TypeScript types generated successfully!"
    echo "📄 Output: $MOBILE_APP_DIR/services/api/types.ts"
    echo ""
    echo "📊 Next steps:"
    echo "   1. Review generated types in sumii-mobile-app/services/api/types.ts"
    echo "   2. Import types in your API client:"
    echo "      import { UserResponse, ConversationResponse, ... } from './types';"
else
    echo "❌ Error: TypeSync conversion failed"
    exit 1
fi
