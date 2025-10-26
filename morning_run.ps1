# C:\stocks\kabu_mvp\morning_run.ps1
Set-Location C:\stocks\kabu_mvp

# choose python without using conda activate (works in Task Scheduler too)
$py = Join-Path $env:USERPROFILE 'miniforge3\envs\kabu\python.exe'
if (Test-Path $py) { $python = $py } else { $python = 'python' }

# pass CLI args as an array (no backticks needed)
$args = @(
  '-m','app.run_mock',
  '--max','5',
  '--min-adv','1e8',
  '--min-atr-pct','0.5',
  '--max-atr-pct','10',
  '--gap-min','-5',
  '--gap-max','5',
  '--or-minutes','5',
  '--entry-not-before','4',
  '--min-stop-ticks','5',
  '--tp-rr','1.5',
  '--debug'
)

Write-Host ("Using Python: {0}" -f $python)
& $python @args
Write-Host 'morning_run.ps1 done.'
