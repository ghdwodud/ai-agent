param(
  [string]$ConfigPath = "deploy/cloudflared/config.yml"
)

if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
  Write-Error "cloudflared is not installed or not in PATH."
  exit 1
}

if (-not (Test-Path $ConfigPath)) {
  Write-Error "Config file not found: $ConfigPath"
  exit 1
}

Write-Host "Starting Cloudflare Tunnel with config: $ConfigPath"
cloudflared tunnel --config $ConfigPath run

