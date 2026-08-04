; ============================================================
; School Finance System - Inno Setup script
; ============================================================
; Requires Inno Setup 6: https://jrsoftware.org/isinfo.php
;
; BEFORE compiling this script:
;   1. Run build_windows.bat first, so you have:
;        dist\SchoolFinance.exe
;   2. This .iss file must be in the school_finance folder
;      (same level as the "dist" and "vcredist" folders).
;   3. Open this file in the Inno Setup Compiler (IDE) and press
;      Build > Compile (or Ctrl+F9).
;
; The resulting installer will work on 32-bit and 64-bit Windows,
; from Windows 7 SP1 up through Windows 11, and does not require
; admin rights (installs to the user's own folder by default).
; ============================================================

#define MyAppName "School Finance System"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Your School"
#define MyAppExeName "SchoolFinance.exe"

[Setup]
; Generate your own GUID once (Tools > Generate GUID in the Inno IDE)
; and keep it the same for every future version - it's how Windows
; recognises "this is an update", not a brand new app.
AppId={{6D6B8F3E-6C2C-4B7F-9C0E-7F5A2A0E9AA1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=SchoolFinanceSetup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=assets\app.ico

; ---- Run on the widest possible range of Windows machines ----
; 6.1 = Windows 7 SP1. Since build_windows.bat targets Python 3.8
; specifically so the exe can run on old machines, don't raise this.
MinVersion=6.1
; Allow the installer itself on x86 (32-bit), x64 and arm64 Windows,
; instead of restricting it to 64-bit-only machines.
ArchitecturesAllowed=x86 x64 arm64
ArchitecturesInstallIn64BitMode=x64compatible

; No admin rights required - installs to the current user's own
; folder (AppData/Local Programs). Set to "admin" instead if you
; want it under Program Files for all users on a shared PC.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\SchoolFinance.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "vcredist\vc_redist.x64.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall

[Dirs]
; Pre-create the app's working folders with write access for the
; installing user, so first run doesn't hit a permissions error.
Name: "{app}\data"; Permissions: users-modify
Name: "{app}\receipts"; Permissions: users-modify
Name: "{app}\statements"; Permissions: users-modify
Name: "{app}\backups"; Permissions: users-modify

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "assets\app.ico"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "assets\app.ico"; Tasks: desktopicon

[Run]
Filename: "{tmp}\vc_redist.x64.exe"; Parameters: "/install /quiet /norestart"; StatusMsg: "Installing Visual C++ Redistributable (required for Windows 7/8)..."; Flags: waituntilterminated
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Data/receipts/statements/backups are kept on uninstall by default
; (they're user financial records). Uncomment below only if you
; want "Uninstall" to wipe everything, including the database:
; Type: filesandordirs; Name: "{app}\data"
; Type: filesandordirs; Name: "{app}\receipts"
; Type: filesandordirs; Name: "{app}\statements"
; Type: filesandordirs; Name: "{app}\backups"
