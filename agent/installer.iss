; ComputerOff Agent - Inno Setup Installer Script
; Bundles x64, x86, win7_x64 EXE variants and auto-detects OS to install the correct one.
;
; Build command:
;   iscc /DMyAppVersion=1.0.0 installer.iss

#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif

#define MyAppName "ComputerOff Agent"
#define MyAppPublisher "유진레이저목형"
#define MyAppExeName "computeroff_agent.exe"
#define MyServerURL "http://office.yjlaser.net:8000"

[Setup]
AppId={{B3F7E8A1-4D2C-4F5A-9B8E-1C3D5A7F9E2B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName=C:\ComputerOff
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
OutputDir=..\dist
OutputBaseFilename=ComputerOff_Setup_v{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=admin
CreateAppDir=yes
Uninstallable=yes
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
CloseApplications=force
CloseApplicationsFilter=computeroff_agent.exe
ArchitecturesAllowed=x86 x64
ArchitecturesInstallIn64BitMode=x64
; No desktop icon, no start menu
CreateUninstallRegKey=yes
; Minimum Windows 7
MinVersion=6.1

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Files]
; Bundle all 3 EXE variants - extract to temp, Pascal Script picks the right one
Source: "..\dist\agent_windows_x64.exe"; DestDir: "{tmp}"; Flags: ignoreversion dontcopy
Source: "..\dist\agent_windows_x86.exe"; DestDir: "{tmp}"; Flags: ignoreversion dontcopy
Source: "..\dist\agent_windows_win7_x64.exe"; DestDir: "{tmp}"; Flags: ignoreversion dontcopy

[Run]
; Post-install: register Task Scheduler tasks only (--install skips admin check and config overwrite)
Filename: "{app}\{#MyAppExeName}"; Parameters: "--install"; StatusMsg: "작업 스케줄러 등록 중..."; Flags: runhidden waituntilterminated

[UninstallRun]
; Pre-uninstall: remove Task Scheduler tasks
Filename: "{app}\{#MyAppExeName}"; Parameters: "--uninstall"; Flags: runhidden waituntilterminated

[Code]
var
  SelectedVariant: String;

function BoolToStr(Value: Boolean): String;
begin
  if Value then
    Result := 'True'
  else
    Result := 'False';
end;

function GetWindowsVersionMajor: Cardinal;
var
  Version: TWindowsVersion;
begin
  GetWindowsVersionEx(Version);
  Result := Version.Major;
end;

function GetWindowsVersionMinor: Cardinal;
var
  Version: TWindowsVersion;
begin
  GetWindowsVersionEx(Version);
  Result := Version.Minor;
end;

function IsWindows7: Boolean;
var
  Version: TWindowsVersion;
begin
  GetWindowsVersionEx(Version);
  // Windows 7 = version 6.1
  Result := (Version.Major = 6) and (Version.Minor = 1);
end;

function Is64BitInstallMode_Custom: Boolean;
begin
  Result := Is64BitInstallMode;
end;

procedure DetectAgentVariant;
begin
  if not Is64BitInstallMode_Custom then
  begin
    // 32-bit OS
    SelectedVariant := 'agent_windows_x86.exe';
    Log('Detected 32-bit OS -> selecting x86 variant');
  end
  else if IsWindows7 then
  begin
    // Windows 7 64-bit (version 6.1)
    SelectedVariant := 'agent_windows_win7_x64.exe';
    Log('Detected Windows 7 64-bit -> selecting win7_x64 variant');
  end
  else
  begin
    // Windows 8+ 64-bit
    SelectedVariant := 'agent_windows_x64.exe';
    Log('Detected Windows 8+ 64-bit -> selecting x64 variant');
  end;
end;

function GetVariantLabel: String;
begin
  if SelectedVariant = 'agent_windows_x86.exe' then
    Result := 'x86'
  else if SelectedVariant = 'agent_windows_win7_x64.exe' then
    Result := 'win7_x64'
  else
    Result := 'x64';
end;

procedure CreateConfigJson;
var
  ConfigPath: String;
  Lines: TArrayOfString;
begin
  ConfigPath := ExpandConstant('{app}\config.json');
  SetArrayLength(Lines, 5);
  Lines[0] := '{';
  Lines[1] := '  "server_url": "{#MyServerURL}",';
  Lines[2] := '  "agent_variant": "' + GetVariantLabel + '",';
  Lines[3] := '  "version": "{#MyAppVersion}"';
  Lines[4] := '}';
  SaveStringsToFile(ConfigPath, Lines, False);
  Log('Created config.json at ' + ConfigPath);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  SourcePath, DestPath: String;
begin
  if CurStep = ssInstall then
  begin
    // Detect which variant to install
    DetectAgentVariant;

    // Extract the selected EXE from the archive
    ExtractTemporaryFile(SelectedVariant);

    // Copy the selected EXE as computeroff_agent.exe to install dir
    SourcePath := ExpandConstant('{tmp}\') + SelectedVariant;
    DestPath := ExpandConstant('{app}\{#MyAppExeName}');

    // Ensure install directory exists
    ForceDirectories(ExpandConstant('{app}'));

    if not FileCopy(SourcePath, DestPath, False) then
    begin
      MsgBox('에이전트 파일 복사에 실패했습니다.' + #13#10 +
             'Source: ' + SourcePath + #13#10 +
             'Dest: ' + DestPath, mbError, MB_OK);
      Log('ERROR: Failed to copy ' + SourcePath + ' to ' + DestPath);
    end
    else
    begin
      Log('Copied ' + SelectedVariant + ' -> ' + DestPath);
    end;

    // Create config.json
    CreateConfigJson;
  end;
end;

function InitializeSetup: Boolean;
begin
  Result := True;
  // Detect variant early for logging
  DetectAgentVariant;
  Log('ComputerOff Agent Installer v{#MyAppVersion}');
  Log('Selected variant: ' + SelectedVariant);
  Log('OS: Windows ' + IntToStr(GetWindowsVersionMajor) + '.' + IntToStr(GetWindowsVersionMinor));
  Log('64-bit install mode: ' + BoolToStr(Is64BitInstallMode_Custom));
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ConfigPath: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    // Clean up config.json and any remaining files
    ConfigPath := ExpandConstant('{app}\config.json');
    if FileExists(ConfigPath) then
      DeleteFile(ConfigPath);

    // Remove state.json if present
    if FileExists(ExpandConstant('{app}\state.json')) then
      DeleteFile(ExpandConstant('{app}\state.json'));

    // Remove agent.log if present
    if FileExists(ExpandConstant('{app}\agent.log')) then
      DeleteFile(ExpandConstant('{app}\agent.log'));

    // Try to remove the install directory (only if empty)
    RemoveDir(ExpandConstant('{app}'));
  end;
end;
