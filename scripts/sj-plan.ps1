# ============================================================
# gt-sj-plan 容器环境管理脚本（sj-dev1.0 分支专用）
#
# 用法（在仓库根执行）：
#   .\scripts\sj-plan.ps1 up      # 启动 postgres + redis + onlyoffice
#   .\scripts\sj-plan.ps1 down    # 停止并移除容器（数据卷保留）
#   .\scripts\sj-plan.ps1 ps      # 查看状态
#   .\scripts\sj-plan.ps1 logs    # 跟随日志
#   .\scripts\sj-plan.ps1 env     # 打印后端应使用的连接串（写进根 .env）
#
# 存在意义：手敲完整 compose 命令必须同时带对 -p / --env-file / 两个 -f，
# 漏任何一个都会连到其他分支的容器或抢占其端口。本脚本把这组参数固定下来。
# 写法照 scripts/sw-plan.ps1。
# ============================================================
param(
    [Parameter(Position = 0)]
    [ValidateSet('up', 'down', 'ps', 'logs', 'env', 'restart')]
    [string]$Action = 'ps'
)

$ErrorActionPreference = 'Stop'

# 脚本在 scripts/ 下，仓库根是上一级；不依赖调用者的当前目录
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$Project = 'gt-sj-plan'
$EnvFile = '.env.sj-plan'

if (-not (Test-Path $EnvFile)) {
    Write-Error "缺少 $EnvFile，无法确定 gt-sj-plan 的端口与库名。"
    exit 1
}

# onlyoffice 在基础文件里带 profiles:[onlyoffice]，不显式启用 profile 就不会出现在解析结果里
$Base = @(
    'compose',
    '-p', $Project,
    '--env-file', $EnvFile,
    '-f', 'docker-compose.yml',
    '-f', 'docker-compose.sj-plan.yml',
    '--profile', 'onlyoffice'
)

# 默认只拉起开发必需的三个服务；metabase / ollama 等按需单独启动
$CoreServices = @('postgres', 'redis', 'onlyoffice')

function Get-EnvValue([string]$Key) {
    $line = Select-String -Path $EnvFile -Pattern "^$Key=" | Select-Object -First 1
    if ($null -eq $line) { return $null }
    return ($line.Line -split '=', 2)[1].Trim()
}

switch ($Action) {
    'up' {
        Write-Host "[gt-sj-plan] 启动容器：$($CoreServices -join ', ')" -ForegroundColor Cyan
        & docker @Base up -d @CoreServices
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        Write-Host ''
        & docker @Base ps
        Write-Host ''
        & $PSCommandPath env
    }
    'down' {
        # 不加 -v：数据卷保留，下次 up 数据仍在
        Write-Host '[gt-sj-plan] 停止容器（数据卷保留）' -ForegroundColor Cyan
        & docker @Base down
    }
    'restart' {
        & docker @Base restart @CoreServices
    }
    'ps' {
        & docker @Base ps
    }
    'logs' {
        & docker @Base logs -f --tail 100 @CoreServices
    }
    'env' {
        $pgPort = Get-EnvValue 'PG_PORT'
        $pgDb = Get-EnvValue 'PG_DB'
        $pgUser = Get-EnvValue 'PG_USER'
        $pgPass = Get-EnvValue 'PG_PASSWORD'
        $redisPort = Get-EnvValue 'REDIS_PORT'
        $officePort = Get-EnvValue 'OFFICE_PORT'

        # 用 127.0.0.1 不用 localhost：Windows 上 localhost 先解析 ::1，每个新连接多等约 300ms
        Write-Host '[gt-sj-plan] 后端连接串（宿主机 start-dev.bat 读根 .env，填这三项）' -ForegroundColor Cyan
        Write-Host "  DATABASE_URL=postgresql+asyncpg://${pgUser}:${pgPass}@127.0.0.1:${pgPort}/${pgDb}"
        Write-Host "  REDIS_URL=redis://127.0.0.1:${redisPort}/0"
        Write-Host "  ONLYOFFICE_URL=http://127.0.0.1:${officePort}"
    }
}
