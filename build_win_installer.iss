// Get version from preprocessor variable (set via /DAPP_VERSION=value) or environment variable
#ifndef APP_VERSION
  #define MyAppVersion GetEnv("APP_VERSION")
  #if MyAppVersion == ""
    #define MyAppVersion "1.0.0"
  #endif
#else
  #define MyAppVersion APP_VERSION
#endif

// VersionInfoVersion requires exactly 4 numeric components (X.X.X.X)
// Standard semantic versions are X.Y.Z (3 components), so append .0
// This converts "1.0.0" to "1.0.0.0" for Windows version info
#define MyAppVersionInfoVersion MyAppVersion + ".0"

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
VersionInfoCompany=Sightline App Contributors
VersionInfoDescription=Powerful tools for face blurring, manual redaction, and audio transcription in a single application.
VersionInfoCopyright=Copyright (C) 2025
VersionInfoProductName=Sightline
VersionInfoProductVersion={#MyAppVersion}

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
