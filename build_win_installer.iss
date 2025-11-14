#define MyAppVersion GetEnv("APP_VERSION")
// If the version is empty, use a default
#if MyAppVersion == ""
  #define MyAppVersion "1.0.0"
#endif

// Helper to get a valid VersionInfoVersion (must be X.X.X.X)
#define MyAppVersionInfoVersion StrReplace("{#MyAppVersion}", ".", ".", 3)
#if (Pos(".", "{#MyAppVersion}") = 0)
  #define MyAppVersionInfoVersion "{#MyAppVersion}.0.0.0"
#elif (GetStringLength("{#MyAppVersion}") - GetStringLength(StrReplace("{#MyAppVersion}", ".", "")) = 1)
  #define MyAppVersionInfoVersion "{#MyAppVersion}.0.0"
#elif (GetStringLength("{#MyAppVersion}") - GetStringLength(StrReplace("{#MyAppVersion}", ".", "")) = 2)
  #define MyAppVersionInfoVersion "{#MyAppVersion}.0"
#else
  #define MyAppVersionInfoVersion "{#MyAppVersion}"
#endif
#if MyAppVersion == ""
  #define MyAppVersion "1.0.0"
#endif

[Setup]
AppName=Deface
AppVersion={#MyAppVersion}
AppPublisher=Deface App Contributors
AppPublisherURL=https://github.com/aschepis/deface-app
AppSupportURL=https://github.com/aschepis/deface-app/issues
AppUpdatesURL=https://github.com/aschepis/deface-app/releases
DefaultDirName={autopf}\Deface
DefaultGroupName=Deface
OutputDir=Output
OutputBaseFilename=DefaceInstaller
Compression=lzma
SolidCompression=yes
LicenseFile=LICENSE
InfoBeforeFile=
InfoAfterFile=
VersionInfoVersion={#MyAppVersion}.0
VersionInfoCompany=Deface App Contributors
VersionInfoDescription=GUI application for blurring faces in images and videos
VersionInfoCopyright=Copyright (C) 2025
VersionInfoProductName=Deface
VersionInfoProductVersion={#MyAppVersion}

[Files]
Source: "dist\Deface\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Deface"; Filename: "{app}\Deface.exe"
Name: "{group}\Uninstall Deface"; Filename: "{uninstallexe}"
Name: "{userdesktop}\Deface"; Filename: "{app}\Deface.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"; Flags: unchecked

[Run]
Filename: "{app}\Deface.exe"; Description: "Launch Deface"; Flags: nowait postinstall skipifsilent
