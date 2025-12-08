// Get version from preprocessor variable (set via /DAPP_VERSION=value) or environment variable
#ifndef APP_VERSION
  #define MyAppVersion GetEnv("APP_VERSION")
  #if MyAppVersion == ""
    #define MyAppVersion "1.0.0"
  #endif
#else
  #define MyAppVersion APP_VERSION
#endif

#pragma message "DEBUG: MyAppVersion = " + MyAppVersion

// Extract numeric version part (strip "v" prefix and pre-release suffixes like -rc2, -beta, etc.)
// VersionInfoVersion requires exactly 4 numeric components (X.X.X.X)
// We need to extract just the numeric part (e.g., "1.0.0" from "v1.0.0-rc2")
// and convert it to "1.0.0.0" format
// Handle versions with "v" prefix, pre-release suffixes, or both

// Check if version starts with "v" prefix
#if Copy(MyAppVersion, 1, 1) == "v"
  // Version starts with "v", strip it first
  #define VersionWithoutPrefix Copy(MyAppVersion, 2, 999)
  #pragma message "DEBUG: Version starts with 'v', stripped to: " + VersionWithoutPrefix
#else
  // No "v" prefix
  #define VersionWithoutPrefix MyAppVersion
  #pragma message "DEBUG: Version has no 'v' prefix, using: " + VersionWithoutPrefix
#endif

// Find dash position (if any) to extract numeric part
#define DashPos Pos("-", VersionWithoutPrefix)
#pragma message "DEBUG: DashPos = " + Str(DashPos)
#if DashPos > 0
  // Version has a dash, extract substring before it
  #define MyNumericVersion Copy(VersionWithoutPrefix, 1, DashPos - 1)
  #pragma message "DEBUG: Version has dash, extracted numeric part: " + MyNumericVersion
#else
  // No dash, use full version
  #define MyNumericVersion VersionWithoutPrefix
  #pragma message "DEBUG: Version has no dash, using full version: " + MyNumericVersion
#endif

// Convert 3-component version (X.Y.Z) to 4-component (X.Y.Z.0) for VersionInfoVersion
// This handles both regular versions (1.0.0 -> 1.0.0.0) and pre-release versions (v1.0.0-rc2 -> 1.0.0.0)
#define MyAppVersionInfoVersion MyNumericVersion + ".0"
#pragma message "DEBUG: MyNumericVersion = " + MyNumericVersion
#pragma message "DEBUG: MyAppVersionInfoVersion (final) = " + MyAppVersionInfoVersion

[Setup]
AppName=Sightline
AppVersion={#MyAppVersion}
AppPublisher=Sightline App Contributors
AppPublisherURL=https://github.com/aschepis/sightline
AppSupportURL=https://github.com/aschepis/sightline/issues
AppUpdatesURL=https://github.com/aschepis/sightline/releases
DefaultDirName={autopf}\Sightline
DefaultGroupName=Sightline
OutputDir=Output
OutputBaseFilename=SightlineInstaller
Compression=lzma
SolidCompression=yes
LicenseFile=LICENSE
InfoBeforeFile=
InfoAfterFile=
VersionInfoVersion={#MyAppVersionInfoVersion}
VersionInfoTextVersion={#MyAppVersion}
VersionInfoCompany=Sightline App Contributors
VersionInfoDescription=Powerful tools for face blurring, manual redaction, and audio transcription in a single application.
VersionInfoCopyright=Copyright (C) 2025
VersionInfoProductName=Sightline
VersionInfoProductVersion={#MyAppVersionInfoVersion}

[Files]
Source: "dist\Sightline\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Sightline"; Filename: "{app}\Sightline.exe"
Name: "{group}\Uninstall Sightline"; Filename: "{uninstallexe}"
Name: "{userdesktop}\Sightline"; Filename: "{app}\Sightline.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"; Flags: unchecked

[Run]
Filename: "{app}\Sightline.exe"; Description: "Launch Sightline"; Flags: nowait postinstall skipifsilent
