#ifndef AppName
#define AppName "IDV Login"
#endif

#ifndef AppVersion
#define AppVersion "dev"
#endif

#ifndef OutputBaseFilename
#define OutputBaseFilename "idv-login"
#endif

#ifndef OutputDir
#define OutputDir "."
#endif

#ifndef LangFile
#ifexist "ChineseSimplified.isl"
#define LangFile "ChineseSimplified.isl"
#else
#define LangFile "compiler:Languages\ChineseSimplified.isl"
#endif
#endif

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={code:GetDefaultDir}
CreateUninstallRegKey=no
Uninstallable=no
OutputBaseFilename={#OutputBaseFilename}
PrivilegesRequired=lowest
Compression=lzma
SolidCompression=yes
OutputDir={#OutputDir}
SetupIconFile=..\assets\icon.ico
LicenseFile=LICENSE.txt
ShowLanguageDialog=no
LanguageDetectionMethod=none

[Languages]
Name: "chinesesimplified"; MessagesFile: "{#LangFile}"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加图标"

[Files]
Source: "..\dist\python-embed\*"; DestDir: "{app}\python-embed"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\dist\src\*"; DestDir: "{app}\src"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\dist\点我启动工具.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\assets\icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autodesktop}\IDV Login"; Filename: "{app}\点我启动工具.bat"; Tasks: desktopicon; IconFilename: "{app}\icon.ico"

[Run]
Filename: "{app}\点我启动工具.bat"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
Filename: "https://www.yuque.com/keygen/kg2r5k/izpgpf4g3ecqsbf3"; Description: "查看教程"; Flags: postinstall shellexec runasoriginaluser

[Code]
function CanWriteToDir(Dir: String): Boolean;

function GetDefaultDir(Param: String): String;
var
  DDir: String;
  CDir: String;
  FallbackDir: String;
  FlagPath: String;
  SavedDir: String;
  SavedDirAnsi: AnsiString;
begin
  FlagPath := ExpandConstant('{commonappdata}\idv-login\install_root.flag');
  if LoadStringFromFile(FlagPath, SavedDirAnsi) then
  begin
    SavedDir := String(SavedDirAnsi);
    SavedDir := Trim(SavedDir);
    if (SavedDir <> '') and DirExists(SavedDir) then
    begin
      Result := SavedDir;
      Exit;
    end;
  end;
  DDir := 'D:\ProgramData\IDV-Login';
  CDir := 'C:\ProgramData\IDV-Login';
  FallbackDir := ExpandConstant('{commondocs}\IDV-Login');
  if CanWriteToDir(DDir) then
    Result := DDir
  else if CanWriteToDir(CDir) then
    Result := CDir
  else
    Result := FallbackDir;
end;

function CanWriteToDir(Dir: String): Boolean;
var
  TestFile: String;
begin
  Result := False;
  try
    if not DirExists(Dir) then
      if not ForceDirectories(Dir) then
        Exit;
    TestFile := AddBackslash(Dir) + '.__write_test';
    if SaveStringToFile(TestFile, 'test', False) then
    begin
      DeleteFile(TestFile);
      Result := True;
    end;
  except
    Result := False;
  end;
end;

procedure InitializeWizard;
begin
  WizardForm.DiskSpaceLabel.Visible := False;
end;

function IsASCII(s: string): Boolean;
var
  i: Integer;
begin
  Result := True;
  for i := 1 to Length(s) do
  begin
    if Ord(s[i]) > 127 then
    begin
      Result := False;
      Exit;
    end;
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = wpSelectDir then
  begin
    if not IsASCII(WizardDirValue) then
    begin
      MsgBox('为了保证软件稳定运行，安装路径只能包含英文字母和数字。' + #13#10 +
             '检测到路径中包含非 ASCII 字符（如中文）。' + #13#10 +
             '请修改路径。', mbError, MB_OK);
      Result := False;
    end;
  end;
end;
