#define MyAppName "Moneykeeper"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Moneykeeper"
#define MyAppExeName "Moneykeeper.exe"

[Setup]
AppId={{B7F4D5E0-8A7D-4D0A-9C70-3E8E7D9D1C42}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=installer
OutputBaseFilename=Moneykeeper-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
Uninstallable=yes
CloseApplications=yes

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent