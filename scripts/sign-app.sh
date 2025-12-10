#!/bin/bash
# Sign a macOS app bundle with proper code signing
#
# Usage: sign-app.sh <DIST_APP> <SIGNING_IDENTITY> <APP_NAME>
#
# Example: sign-app.sh dist/Sightline.app "-" Sightline

set -e

DIST_APP="$1"
SIGNING_IDENTITY="$2"
APP="$3"

if [ -z "$DIST_APP" ] || [ -z "$SIGNING_IDENTITY" ] || [ -z "$APP" ]; then
    echo "Error: Missing required arguments"
    echo "Usage: sign-app.sh <DIST_APP> <SIGNING_IDENTITY> <APP_NAME>"
    exit 1
fi

echo "→ Signing $DIST_APP with identity: $SIGNING_IDENTITY"

if [ "$SIGNING_IDENTITY" = "-" ]; then
    echo "Using ad-hoc signing (for local testing only)"
    codesign --force --deep --sign "$SIGNING_IDENTITY" "$DIST_APP"
else
    echo "Using proper signing with hardened runtime"
    echo "→ Step 1: Signing nested frameworks and libraries..."
    find "$DIST_APP/Contents/Frameworks" -type f \( -name "*.dylib" -o -name "*.so" \) 2>/dev/null | while read -r lib; do
        echo "  Signing: $lib"
        codesign --force --sign "$SIGNING_IDENTITY" \
            --timestamp \
            --options runtime \
            "$lib" 2>/dev/null || true
    done
    echo "→ Step 2: Signing executable helpers inside Frameworks (e.g. ffmpeg)..."
    find "$DIST_APP/Contents/Frameworks" -type f -perm +111 ! \( -name "*.dylib" -o -name "*.so" \) 2>/dev/null | while read -r binary; do
        echo "  Signing: $binary"
        codesign --force --sign "$SIGNING_IDENTITY" \
            --timestamp \
            --options runtime \
            "$binary" 2>/dev/null || true
    done
    echo "→ Step 3: Signing nested executables..."
    find "$DIST_APP/Contents/MacOS" -type f -perm +111 ! -name "$APP" 2>/dev/null | while read -r binary; do
        echo "  Signing: $binary"
        codesign --force --sign "$SIGNING_IDENTITY" \
            --timestamp \
            --options runtime \
            "$binary" 2>/dev/null || true
    done
    find "$DIST_APP/Contents/Resources" -type f -perm +111 2>/dev/null | while read -r binary; do
        echo "  Signing: $binary"
        codesign --force --sign "$SIGNING_IDENTITY" \
            --timestamp \
            --options runtime \
            "$binary" 2>/dev/null || true
    done
    echo "→ Step 4: Signing main executable..."
    if [ -f "$DIST_APP/Contents/MacOS/$APP" ]; then
        codesign --force --sign "$SIGNING_IDENTITY" \
            --timestamp \
            --options runtime \
            --entitlements entitlements.plist \
            "$DIST_APP/Contents/MacOS/$APP"
    fi
    echo "→ Step 5: Signing app bundle..."
    codesign --force --sign "$SIGNING_IDENTITY" \
        --timestamp \
        --options runtime \
        --entitlements entitlements.plist \
        "$DIST_APP"
fi

echo "→ Verifying signature..."
if codesign --verify --verbose=2 "$DIST_APP"; then
    echo "✓ Signature verified!"
else
    echo "⚠ Signature verification failed!"
    exit 1
fi

echo "✓ Signing complete!"
