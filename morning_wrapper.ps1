$ts  = Get-Date -Format yyyyMMdd_HHmm
$log = "C:\stocks\kabu_mvp\logs\morning_$ts.log"

# 失敗しても実行が続くように最低限のエラーハンドリング
try { Start-Transcript -Path $log -Append -ErrorAction Stop } catch {}

& 'C:\stocks\kabu_mvp\morning_run.ps1' 2>&1 | Tee-Object -FilePath $log -Append

try { Stop-Transcript | Out-Null } catch {}
