<#
Install-WinVMApps.ps1

Installs the few applications you actually need in your Windows 11 VM.
Currently:
- iTunes (via winget, optional – only if you sync iPhone/iPad)
SilverFast + Plustek drivers must be installed manually from vendor sites.
#>

Write-Host "=== Windows 11 VM App Installer ===" -ForegroundColor Cyan

# Check for winget
if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
    Write-Warning "winget is not available. Install 'App Installer' from the Microsoft Store and rerun this script."
} else {
    $answer = Read-Host "Install iTunes using winget? (y/N)"
    if ($answer -match '^[Yy]$') {
        Write-Host "Installing iTunes with winget..." -ForegroundColor Green
        try {
            winget install -e --id Apple.iTunes
        }
        catch {
            Write-Warning "winget failed to install iTunes. You may need to install it manually from Apple/Microsoft Store."
        }
    } else {
        Write-Host "Skipping iTunes installation."
    }
}

Write-Host ""
Write-Host "==================================================================" -ForegroundColor DarkCyan
Write-Host "Manual installs still required:" -ForegroundColor Yellow
Write-Host "  - SilverFast (LaserSoft Imaging) for Plustek OpticFilm 7600i"
Write-Host "  - Plustek OpticFilm 7600i driver"
Write-Host ""
Write-Host "Download and install those from the official vendor websites inside" -ForegroundColor Yellow
Write-Host "the VM, then you are done." -ForegroundColor Yellow
Write-Host "==================================================================" -ForegroundColor DarkCyan
