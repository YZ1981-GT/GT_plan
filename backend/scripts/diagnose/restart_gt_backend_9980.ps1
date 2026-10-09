# GT_plan 专用：清理 9980 上残留的 GT backend，再启动唯一 uvicorn 实例。
$ErrorActionPreference = 'Stop'
$backendRoot = 'd:\GT_plan\backend'
$python = 'd:\GT_plan\.venv\Scripts\python.exe'

Write-Host '=== listeners on :9980 (before) ==='
netstat -ano | findstr ':9980' | findstr 'LISTENING'

$pids = @()
netstat -ano | findstr ':9980' | findstr 'LISTENING' | ForEach-Object {
    $parts = ($_ -split '\s+') | Where-Object { $_ -ne '' }
    if ($parts.Length -ge 5) {
        $procId = [int]$parts[-1]
        if ($procId -gt 0) { $pids += $procId }
    }
}
$pids = $pids | Select-Object -Unique

foreach ($procId in $pids) {
    try {
        $proc = Get-Process -Id $procId -ErrorAction Stop
        $path = $proc.Path
        $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$procId").CommandLine
        if ($path -like '*GT_plan*' -or ($cmd -and ($cmd -like '*GT_plan*' -or $cmd -like '*run_uvicorn*'))) {
            Write-Host "Stopping GT backend PID $procId ($($proc.ProcessName))"
            Stop-Process -Id $procId -Force -ErrorAction Stop
        } else {
            Write-Host "Skip non-GT PID $procId path=$path"
        }
    } catch {
        # 🔴 监听 PID 已不存在，但端口仍 LISTENING —— 真实反复踩到的孤儿态：
        # uvicorn 父进程死了，它的 multiprocessing 子进程继承了监听 socket 继续服务，
        # 于是请求打到**旧代码**上，而 `Get-Process/taskkill` 对那个父 PID 都报 not found。
        # 子进程的命令行里带 `spawn_main(parent_pid=<父 PID>`，按它精确找出来杀掉。
        # 不这么做的后果很具体：改完代码重启「成功」（health 200），但行为一点没变，
        # 会被误读成「改动无效」而去改别的地方。
        Write-Host "Skip PID $procId : $_"
        $orphans = Get-CimInstance Win32_Process -Filter "name='python.exe'" |
            Where-Object { $_.CommandLine -and $_.CommandLine -like "*parent_pid=$procId*" }
        foreach ($orphan in $orphans) {
            Write-Host "Stopping orphaned child PID $($orphan.ProcessId) (parent_pid=$procId)"
            Stop-Process -Id $orphan.ProcessId -Force -ErrorAction Continue
        }
    }
}

Start-Sleep -Seconds 2
Write-Host '=== listeners on :9980 (after kill) ==='
netstat -ano | findstr ':9980' | findstr 'LISTENING'

$env:DB_DISABLE_SSL = 'True'
$env:PYTHONIOENCODING = 'utf-8'
Start-Process -FilePath $python `
    -ArgumentList 'run_uvicorn.py','app.main:app','--host','0.0.0.0','--port','9980','--log-level','warning' `
    -WorkingDirectory $backendRoot `
    -WindowStyle Hidden

Start-Sleep -Seconds 12
Write-Host '=== health ==='
try {
    $r = Invoke-WebRequest 'http://127.0.0.1:9980/api/health' -UseBasicParsing -TimeoutSec 15
    Write-Host "health $($r.StatusCode)"
} catch {
    Write-Host "health FAIL: $($_.Exception.Message)"
    exit 1
}

Write-Host '=== listeners on :9980 (after start) ==='
netstat -ano | findstr ':9980' | findstr 'LISTENING'
