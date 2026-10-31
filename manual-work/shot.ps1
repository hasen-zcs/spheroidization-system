$ErrorActionPreference = 'Continue'
$edge = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
$out  = 'D:\项目组学习\项目工作\东贝生产线\系统架构\1.2\球化监测系统 (1)\spheroidization-system\manual-work'
if (-not (Test-Path $out)) { New-Item -ItemType Directory -Force -Path $out | Out-Null }

$pages = @(
  @{ name = '01_monitor';            url = 'http://localhost:5173/' },
  @{ name = '02_home';               url = 'http://localhost:5173/records/home' },
  @{ name = '03_records';            url = 'http://localhost:5173/records/spheroidization' },
  @{ name = '04_records_create';     url = 'http://localhost:5173/records/spheroidization?create=1' },
  @{ name = '05_abnormal';           url = 'http://localhost:5173/records/abnormal' },
  @{ name = '06_detail';             url = 'http://localhost:5173/spheroidization/7' },
  @{ name = '07_detail_processed';   url = 'http://localhost:5173/spheroidization/1' },
  @{ name = '08_detail_unprocessed'; url = 'http://localhost:5173/spheroidization/6' },
  @{ name = '09_standard';           url = 'http://localhost:5173/records/standard' }
)

foreach ($p in $pages) {
  $target = Join-Path $out ($p.name + '.png')
  if (Test-Path $target) { Remove-Item $target -Force }
  $log = & $edge --headless --no-sandbox --disable-gpu --no-first-run --disable-extensions `
      --hide-scrollbars --window-size=1440,1000 `
      --virtual-time-budget=15000 --timeout=30000 `
      --screenshot="$target" $p.url 2>&1
  if (Test-Path $target) {
    Write-Host ("OK   {0}  {1} bytes" -f $p.name, (Get-Item $target).Length)
  } else {
    Write-Host ("FAIL {0}  :: {1}" -f $p.name, (($log | Out-String).Trim()))
  }
}
