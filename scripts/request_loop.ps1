# Usage: .\scripts\request_loop.ps1 -Label rolling_update
# Sends a POST /api/emi request every 200 ms until you press Ctrl+C.
# Every request is logged with time, HTTP result and pod name. Summary printed at the end.
param(
  [string]$Label = "loop",
  [string]$BaseUrl = "http://emi.local",
  [int]$DelayMs = 200
)

New-Item -ItemType Directory -Force -Path "results" | Out-Null
$log = "results\loop_$Label.log"
"time,status,pod" | Out-File -Encoding ascii $log
$ok = 0; $fail = 0

try {
  while ($true) {
    $body = @{ principal = 500000; rate = 12; months = 24 } | ConvertTo-Json
    $t = Get-Date -Format "HH:mm:ss.fff"
    try {
      $r = Invoke-RestMethod -Uri "$BaseUrl/api/emi" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 5
      $ok++
      "$t,OK,$($r.servedBy)" | Out-File -Append -Encoding ascii $log
      Write-Host "$t OK   $($r.servedBy)"
    } catch {
      $fail++
      "$t,FAILED," | Out-File -Append -Encoding ascii $log
      Write-Host "$t FAILED" -ForegroundColor Red
    }
    Start-Sleep -Milliseconds $DelayMs
  }
} finally {
  Write-Host ""
  Write-Host "Total OK: $ok   Failed: $fail   (log: $log)"
}
