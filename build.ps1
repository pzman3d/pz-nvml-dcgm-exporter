$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$py = "C:\Users\xyima\AppData\Local\Programs\Python\Python312\python.exe"
if (-not (Test-Path $py)) {
    $py = "python"
}

& $py -m pip install -r requirements.txt
& $py -m PyInstaller --noconfirm --clean pz-nvml-dcgm-exporter.spec

Write-Host ""
Write-Host "Built: $PSScriptRoot\dist\pz-nvml-dcgm-exporter.exe"
Write-Host "Prometheus: http://127.0.0.1:9400/metrics"
