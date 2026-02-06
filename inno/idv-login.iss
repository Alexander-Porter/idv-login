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
AppendDefaultDirName=no
CreateUninstallRegKey=no
Uninstallable=no
OutputBaseFilename={#OutputBaseFilename}
PrivilegesRequired=lowest
Compression=lzma
SolidCompression=yes
OutputDir={#OutputDir}

LicenseFile=LICENSE.txt
ShowLanguageDialog=no
LanguageDetectionMethod=none
DirExistsWarning=no

[Languages]
Name: "chinesesimplified"; MessagesFile: "{#LangFile}"

[Messages]
ErrorReplacingExistingFile=尝试替换现有文件时出错，请关闭正在运行的旧版工具后点击重试。原始信息：

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加图标"
Name: "desktopiconbackup"; Description: "创建备用模式快捷方式"; GroupDescription: "附加图标"

[Files]
Source: "..\dist\python-embed\*"; DestDir: "{app}\python-embed"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\dist\src\*"; DestDir: "{app}\src"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\dist\点我启动工具.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\assets\icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[InstallDelete]
Type: filesandordirs; Name: "{app}\*"

[Icons]
Name: "{autodesktop}\IDV Login"; Filename: "{app}\点我启动工具.bat"; Tasks: desktopicon; IconFilename: "{app}\icon.ico"; AfterInstall: MarkShortcutRunAsAdmin(ExpandConstant('{autodesktop}\IDV Login.lnk'))
Name: "{autodesktop}\IDV Login - 备用模式"; Filename: "{app}\点我启动工具.bat"; Parameters: "--mitm"; Tasks: desktopiconbackup; IconFilename: "{app}\icon.ico"; AfterInstall: MarkShortcutRunAsAdmin(ExpandConstant('{autodesktop}\IDV Login - 备用模式.lnk'))

[Run]
Filename: "{app}\点我启动工具.bat"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
Filename: "https://yuque.com/keygen/kg2r5k/izpgpf4g3ecqsbf3"; Description: "查看教程"; Flags: postinstall shellexec runasoriginaluser

[Code]

procedure MarkShortcutRunAsAdmin(ShortcutPath: String);
var
Stream: TFileStream;
Buffer: string;
begin
if not FileExists(ShortcutPath) then exit;
Stream := TFileStream.Create(ShortcutPath, fmOpenReadWrite);
try
if Stream.Size < 21 then exit;
Stream.Seek(21, soFromBeginning);
SetLength(Buffer, 1);
Stream.ReadBuffer(Buffer, 1);
Buffer[1] := Chr(Ord(Buffer[1]) or $20);
Stream.Seek(-1, soFromCurrent);
Stream.WriteBuffer(Buffer, 1);
finally
Stream.Free;
end;
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

function GetSavedInstallDir: String;
var
  FlagPath: String;
  SavedDir: String;
  SavedDirAnsi: AnsiString;
begin
  Result := '';
  FlagPath := ExpandConstant('{commonappdata}\idv-login\install_root.flag');
  if LoadStringFromFile(FlagPath, SavedDirAnsi) then
  begin
    SavedDir := String(SavedDirAnsi);
    SavedDir := Trim(SavedDir);
    if SavedDir <> '' then
      Result := SavedDir;
  end;
end;

function GetDefaultDir(Param: String): String;
var
  DDir: String;
  CDir: String;
  FallbackDir: String;
  SavedDir: String;
begin
  SavedDir := GetSavedInstallDir;
  if (SavedDir <> '') and DirExists(SavedDir) then
  begin
    Result := SavedDir;
    Exit;
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

function IsRootDir(Dir: String): Boolean;
var
  DriveRoot: String;
begin
  DriveRoot := AddBackslash(ExtractFileDrive(Dir));
  Result := (CompareText(AddBackslash(Dir), DriveRoot) = 0);
end;

function DirHasContent(Dir: String): Boolean;
var
  FindRec: TFindRec;
  Path: String;
begin
  Result := False;
  Path := AddBackslash(Dir) + '*';
  if FindFirst(Path, FindRec) then
  begin
    try
      repeat
        if (FindRec.Name <> '.') and (FindRec.Name <> '..') then
        begin
          Result := True;
          Exit;
        end;
      until not FindNext(FindRec);
    finally
      FindClose(FindRec);
    end;
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  SelectedDir: String;
  SavedDir: String;
begin
  Result := True;
  if CurPageID = wpSelectDir then
  begin
    if not IsASCII(WizardDirValue) then
    begin
      MsgBox('为了保证软件稳定运行，安装路径只能包含英文字母和数字。' + #13#10 +
             '请修改路径。', mbError, MB_OK);
      Result := False;
      Exit;
    end;

    SelectedDir := WizardDirValue;
    if IsRootDir(SelectedDir) then
    begin
      WizardForm.DirEdit.Text := AddBackslash(SelectedDir) + 'IDV-Login';
      SelectedDir := WizardForm.DirEdit.Text;
    end;

    if DirExists(SelectedDir) and DirHasContent(SelectedDir) then
    begin
      SavedDir := GetSavedInstallDir;
      if (SavedDir <> '') and (CompareText(AddBackslash(SelectedDir), AddBackslash(SavedDir)) = 0) then
      begin
        if MsgBox('检测到已安装目录。继续将删除该目录下的所有文件并进行更新，是否继续？', mbConfirmation, MB_YESNO) = IDNO then
          Result := False;
      end
      else
      begin
        if MsgBox('该目录不为空。继续将删除目录下的所有文件并进行安装，是否继续？', mbConfirmation, MB_YESNO) = IDNO then
          Result := False;
      end;
    end;
  end;
end;
