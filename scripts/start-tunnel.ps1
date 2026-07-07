# Expose local dev to the internet (phone off Wi-Fi) via Cloudflare quick tunnel.
# Requires: npm run dev running, cloudflared installed.
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\lib\dev-ports.ps1"

$cloudflared = Get-Command cloudflared -ErrorAction SilentlyContinue
if (-not $cloudflared) {
    Write-Host ""
    Write-Host "cloudflared not found." -ForegroundColor Red
    Write-Host "Install: winget install Cloudflare.cloudflared" -ForegroundColor Yellow
    Write-Host "Or download: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Alternative: npx localtunnel --port $AtlasWebPort" -ForegroundColor Cyan
    exit 1
}

Write-Host ""
Write-Host "=== Atlas tunnel ===" -ForegroundColor Cyan
Write-Host "Local web: http://localhost:$AtlasWebPort"
Write-Host "Make sure npm run dev is running in another terminal."
Write-Host ""
Write-Host "Add the https URL below to Supabase → Auth → URL Configuration (Site URL + Redirect URLs)."
Write-Host ""

& cloudflared tunnel --url "http://localhost:$AtlasWebPort"
