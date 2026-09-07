; Inno Setup script for Task Manager — per-user installer (no UAC).
;
; Builds TaskManager-Setup.exe, which installs the portable PyInstaller exe into
; %LocalAppData%\Programs\TaskManager, creates Start Menu + (optional) Desktop
; shortcuts, and registers a per-user Add/Remove Programs entry.
;
; Because the install directory is user-writable, the app's in-app auto-updater
; (which swaps TaskManager.exe in place — see services/updater.py) keeps working
; unchanged; no elevation is ever required.
;
; Build (from the repo root, after `pyinstaller task_manager.spec`):
;   iscc /DAppVersion=1.4.1 installer\task_manager.iss
; AppVersion must be passed on the command line so it tracks version.py.

#ifndef AppVersion
  #error AppVersion is not defined. Build with: iscc /DAppVersion=x.y.z installer\task_manager.iss
#endif

#define AppName "Task Manager"
#define AppExeName "TaskManager.exe"
#define AppPublisher "Efat Sikder"
#define AppURL "https://github.com/efat1531/task-manager"

[Setup]
; A fixed AppId ties upgrades and uninstall together — never change it.
AppId={{CBA57473-76C9-4FE0-9AE2-3E1B1CD03CCB}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
VersionInfoVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}/releases

; Per-user install, no administrator rights / UAC prompt.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={localappdata}\Programs\TaskManager
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes

; Reinstalling over a running instance: close it first so the exe is unlocked.
CloseApplications=yes
RestartApplications=no

; Installer look + output.
WizardStyle=modern
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#AppExeName}
OutputDir=..\dist
OutputBaseFilename=TaskManager-Setup
Compression=lzma2
SolidCompression=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
