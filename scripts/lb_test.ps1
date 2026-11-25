# Usage: .\scripts\lb_test.ps1 -Label replicas3
# 30 POST requests to /api/emi through the Ingress, counts how many each pod served.
param(
  [string]$Label = "run",
  [int]$Count = 30,
  [string]$BaseUrl = "http://emi.local"
)

$served = @()
for ($i = 1; $i -le $Count; $i++) {
  $body = @{
    principal = Get-Random -Minimum 100000 -Maximum 1000000
    rate      = Get-Random -Minimum 5 -Maximum 25
    months    = Get-Random -Minimum 6 -Maximum 60
  } | ConvertTo-Json
  try {
    $r = Invoke-RestMethod -Uri "$BaseUrl/api/emi" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 5
    $served += $r.servedBy
  } catch {
    $served += "FAILED"
  }
}

$table = $served | Group-Object | Sort-Object Name | Select-Object @{n="Pod";e={$_.Name}}, @{n="Requests";e={$_.Count}}
$table | Format-Table -AutoSize
"Total: $($served.Count)"

New-Item -ItemType Directory -Force -Path "results" | Out-Null
$table | Export-Csv -NoTypeInformation -Path "results\lb_$Label.csv"
Write-Host "Saved results\lb_$Label.csv"
