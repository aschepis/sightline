# Release Process

This document describes how to create a new release of Sightline, including building and distributing signed binaries for macOS, Windows, and Linux.

## Overview

The release process is automated via GitHub Actions. When you push a version tag or manually trigger the release workflow, it will:

1. Build binaries for macOS, Windows, and Linux
2. Sign and notarize the macOS app (if certificates are configured)
3. Create installers/packages for each platform
4. Create a GitHub release with all artifacts attached

## Prerequisites

### For Automated Releases (GitHub Actions)

You need to set up GitHub secrets for signing. See [Setting Up GitHub Secrets](#setting-up-github-secrets) below.

### For Local Testing

1. Conda environment set up: `make conda-env`
2. Dependencies installed: `make install-dev`
3. For macOS signing: Apple Developer account with certificates
4. For Windows: Inno Setup installed
5. For Linux: Standard build tools

## Creating a Release

### Method 1: Automatic Release via Git Tag (Recommended)

1. **Update version numbers** in relevant files:

   - `sightline.spec` (CFBundleVersion and CFBundleShortVersionString in info_plist)
   - Update `CHANGELOG.md` with new version notes

2. **Commit your changes**:

   ```bash
   git add .
   git commit -m "Prepare release v1.2.3"
   ```

3. **Create and push a version tag**:

   ```bash
   git tag v1.2.3
   git push origin main
   git push origin v1.2.3
   ```

4. **Monitor the release**:
   - Go to the Actions tab in GitHub
   - Watch the "Release" workflow execute
   - Once complete, check the Releases page for your new release

### Method 2: Manual Trigger via GitHub Actions UI

1. Go to your repository on GitHub
2. Click on the "Actions" tab
3. Select "Release" workflow from the left sidebar
4. Click "Run workflow" button
5. Enter the version number (e.g., `1.2.3`) - do NOT include the 'v' prefix
6. Click "Run workflow"

## Setting Up GitHub Secrets

To enable automatic signing and notarization, you need to configure the following GitHub secrets.

### Accessing GitHub Secrets

GitHub secrets can be stored at the repository level or in an environment. The workflow is configured to use the **Release** environment.

**Option 1: Using an Environment (Recommended)**

1. Go to your repository on GitHub
2. Click **Settings** → **Environments**
3. Click **New environment** and name it `Release`
4. Click **Add secret** under "Environment secrets" for each secret below

**Option 2: Using Repository Secrets**

1. Go to your repository on GitHub
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret** for each secret below
4. Remove the `environment: Release` line from `.github/workflows/release.yml`

Using environments provides better security and allows you to add deployment protection rules (like requiring approval before releases).

### Required Secrets for macOS Signing & Notarization

#### 1. `APPLE_CERTIFICATE_BASE64`

Your Apple Developer ID Application certificate in base64 format.

**How to obtain:**

```bash
# Export your certificate from Keychain Access as a .p12 file
# Then convert to base64:
base64 DeveloperIDApplication.p12 | pbcopy
```

This copies the base64 string to your clipboard. Paste it as the secret value.

#### 2. `APPLE_CERTIFICATE_PASSWORD`

The password you used when exporting the .p12 certificate.

#### 3. `APPLE_SIGNING_IDENTITY`

The full name of your signing identity, exactly as it appears in Keychain Access.

**Example:**

```
Developer ID Application: Your Name (TEAM123456)
```

**How to find:**

```bash
# List all your signing identities:
security find-identity -v -p codesigning
```

#### 4. `APPLE_ID`

Your Apple ID email address (the one associated with your Apple Developer account).

#### 5. `APPLE_TEAM_ID`

Your 10-character Apple Developer Team ID.

**How to find:**

- Log in to https://developer.apple.com/account
- Your Team ID is shown in the top right or in Membership section

#### 6. `APPLE_APP_SPECIFIC_PASSWORD`

An app-specific password for notarization.

**How to create:**

1. Go to https://appleid.apple.com/account/manage
2. Sign in with your Apple ID
3. In the "Sign-In and Security" section, click "App-Specific Passwords"
4. Click "Generate an app-specific password"
5. Enter a label (e.g., "Sightline Notarization")
6. Copy the generated password and save it as the secret

### Optional: Windows Code Signing

If you want to sign Windows executables (currently not implemented but can be added):

- `WINDOWS_CERTIFICATE_BASE64`: Base64-encoded PFX certificate
- `WINDOWS_CERTIFICATE_PASSWORD`: Certificate password

## Testing Your Signing Setup Locally

Before pushing to GitHub, test your certificate and signing setup locally using the provided test script:

```bash
# Export your certificate from Keychain Access as a .p12 file
# Then run the test script:
./test-signing.sh path/to/your/certificate.p12

# The script will:
# 1. Import your certificate to a test keychain
# 2. Show available signing identities
# 3. Build and sign the app
# 4. Verify the signature
# 5. Provide the exact values to use in GitHub secrets
```

**Quick identity check without building:**

```bash
# List all available signing identities in your keychain
security find-identity -v -p codesigning

# Copy the EXACT identity string (including quotes) for use in APPLE_SIGNING_IDENTITY
```

## Platform-Specific Build Instructions

### macOS

#### Local Build and Sign

```bash
# Build the app
make build-macos

# Sign with your Developer ID (ad-hoc signing by default)
make sign SIGNING_IDENTITY="Developer ID Application: Your Name (TEAMID)"

# Notarize (requires APPLE_ID, APPLE_TEAM_ID, APPLE_APP_SPECIFIC_PASSWORD env vars)
export APPLE_ID="your@email.com"
export APPLE_TEAM_ID="TEAM123456"
export APPLE_APP_SPECIFIC_PASSWORD="xxxx-xxxx-xxxx-xxxx"
make notarize

# Create DMG
make create-dmg VERSION=1.2.3

# Or do everything at once:
make dist-macos VERSION=1.2.3 SIGNING_IDENTITY="Developer ID Application: Your Name (TEAMID)"
```

#### Testing Signed and Notarized Apps

1. After building and signing locally, copy the .app to a different Mac
2. Try to open it - if properly signed and notarized, it should open without warnings
3. Right-click → Open for the first time if you get a warning

#### Verifying Code Signatures

Use these commands to inspect and verify the signature:

```bash
# Basic signature verification
codesign --verify --verbose=4 dist/Sightline.app

# Display detailed signing information
codesign --display --verbose=4 dist/Sightline.app

# Verify all nested code (deep verification)
codesign --verify --deep --strict --verbose=2 dist/Sightline.app

# Check if it will pass Gatekeeper
spctl --assess --verbose=4 --type execute dist/Sightline.app

# Check notarization status
stapler validate dist/Sightline.app

# Find unsigned components (if verification fails)
find dist/Sightline.app -type f \( -name "*.dylib" -o -name "*.so" -o -perm +111 \) | while read file; do
  codesign --verify "$file" 2>&1 | grep -q "not signed" && echo "Unsigned: $file"
done
```

**Expected output for properly signed app:**

- `codesign --verify`: No output (success)
- `spctl --assess`: `dist/Sightline.app: accepted`
- `stapler validate`: `The validate action worked!` (if notarized)

### Windows

#### Local Build

Requires Windows machine with Conda and Inno Setup installed.

```bash
# Set up conda environment
conda create -n sightline-build python=3.12
conda activate sightline-build

# Install dependencies
pip install -r requirements.txt
pip install pyinstaller

# Build executable
python -m PyInstaller sightline.spec --clean --noconfirm

# Create installer (set version)
set APP_VERSION=1.2.3
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" build_win_installer.iss
```

The installer will be created in the `Output/` directory.

### Linux

#### Local Build

```bash
# Set up conda environment
conda create -n sightline-build python=3.12
conda activate sightline-build

# Install dependencies
pip install -r requirements.txt
pip install pyinstaller

# Build executable
python -m PyInstaller sightline.spec --clean --noconfirm

# Create tarball
cd dist
tar -czf Sightline-1.2.3-Linux-x86_64.tar.gz Sightline/
```

## Troubleshooting

### macOS Signing Fails

**Error: "No identity found"**

- Make sure `APPLE_SIGNING_IDENTITY` secret matches exactly what's in your keychain
- Verify the certificate hasn't expired
- Check that the certificate is properly imported in the keychain

**Error: "User interaction is not allowed"**

- The keychain needs to be unlocked
- In CI, this is handled automatically by the certificate import step

### Notarization Fails

**Error: "Invalid credentials"**

- Double-check `APPLE_ID`, `APPLE_TEAM_ID`, and `APPLE_APP_SPECIFIC_PASSWORD`
- Make sure you're using an app-specific password, not your regular Apple ID password

**Error: "Invalid binary"**

- The app must be properly signed before notarization
- Check that all executables and libraries within the .app are signed

### Windows Build Fails

**Error: "PyInstaller not found"**

- Make sure pyinstaller is installed in the conda environment
- Try: `conda run -n sightline-build pip install pyinstaller`

**Error: "Inno Setup not found"**

- Verify Inno Setup is installed at `C:\Program Files (x86)\Inno Setup 6\`
- Or adjust the path in the workflow

### Linux Build Fails

Usually related to missing system libraries. Check PyInstaller output for specific missing dependencies.

## Version Management

Update version numbers in these locations before releasing:

1. **sightline.spec**: Update `CFBundleVersion` and `CFBundleShortVersionString` in the `info_plist` dictionary
2. **CHANGELOG.md**: Add release notes for the new version
3. **Git tag**: Create matching version tag (e.g., `v1.2.3`)

The Windows installer and DMG will automatically use the version from the git tag or workflow input.

## Post-Release Checklist

After a successful release:

- [ ] Verify all three platform builds are attached to the GitHub release
- [ ] Download and test the macOS DMG on a clean Mac
- [ ] Download and test the Windows installer
- [ ] Download and test the Linux tarball
- [ ] Announce the release (social media, Discord, etc.)
- [ ] Update documentation if needed
- [ ] Close any resolved issues/PRs related to this release

## Emergency Rollback

If you need to remove a bad release:

1. Go to the Releases page on GitHub
2. Click on the release
3. Click "Delete" (top right)
4. Delete the git tag:
   ```bash
   git tag -d v1.2.3
   git push origin :refs/tags/v1.2.3
   ```

## Support

For questions or issues with the release process:

- Open an issue on GitHub
- Check existing issues for similar problems
- Review GitHub Actions logs for detailed error messages
