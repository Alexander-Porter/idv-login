$ErrorActionPreference = "Stop"
$workDir = "test_build_verify"

try {
    Write-Host "Starting experiment in $workDir"
    if (Test-Path $workDir) { Remove-Item -Recurse -Force $workDir }
    New-Item -ItemType Directory -Force -Path $workDir | Out-Null
    
    # We will use absolute paths to avoid changing directory and messing up relative paths for requirement.txt
    $absWorkDir = (Resolve-Path $workDir).Path
    $reqPath = (Resolve-Path "requirements.txt").Path
    
    Push-Location $absWorkDir

    # 1. Download Python
    Write-Host "Downloading Python 3.12.10 embed..."
    Invoke-WebRequest -Uri "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip" -OutFile "python-embed.zip"
    Expand-Archive "python-embed.zip" -DestinationPath "python-embed"

    # 2. Modify ._pth
    $pthFile = Get-ChildItem -Path "python-embed" -Filter "python*._pth" | Select-Object -First 1
    # 读取内容，取消注释 "import site"，或者如果不存在则追加
    $content = Get-Content $pthFile.FullName
    if ($content -match "#\s*import site") {
        $content = $content -replace "#\s*import site", "import site"
    } else {
        $content += "import site"
    }
    $content | Set-Content $pthFile.FullName -Encoding ASCII

    # 3. Get pip
    Write-Host "Installing pip..."
    Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile "get-pip.py"
    .\python-embed\python.exe get-pip.py
    .\python-embed\python.exe -m pip install --upgrade pip

    # 4. Install setuptools wheel (The Fix)
    Write-Host "Installing setuptools wheel..."
    .\python-embed\python.exe -m pip install setuptools wheel

    # 5. Install requirements
    Write-Host "Installing requirements from $reqPath..."
    .\python-embed\python.exe -m pip install -r $reqPath
    
    Write-Host "Experiment SUCCESS: Dependencies installed correctly."
}
catch {
    Write-Error "Experiment FAILED: $_"
    exit 1
}
finally {
    Pop-Location
    # Cleanup
    if (Test-Path $workDir) { 
        Write-Host "Cleaning up $workDir..."
        Remove-Item -Recurse -Force $workDir 
    }
}