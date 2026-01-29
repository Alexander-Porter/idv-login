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

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autodesktop}\IDV-Login
CreateUninstallRegKey=no
Uninstallable=no
OutputBaseFilename={#OutputBaseFilename}
PrivilegesRequired=lowest
Compression=lzma
SolidCompression=yes
OutputDir={#OutputDir}

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加图标"

[Files]
Source: "..\dist\python-embed\*"; DestDir: "{app}\python-embed"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\dist\src\*"; DestDir: "{app}\src"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\dist\点我启动工具.bat"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autodesktop}\IDV Login"; Filename: "{app}\点我启动工具.bat"; Tasks: desktopicon

[Code]
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
