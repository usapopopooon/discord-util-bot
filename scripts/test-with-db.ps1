# ローカルで PostgreSQL を使ったテストを実行するスクリプト (Windows PowerShell 版)
#
# 使い方:
#   .\scripts\test-with-db.ps1              # 全テストを実行
#   .\scripts\test-with-db.ps1 -v           # verbose モードで実行
#   .\scripts\test-with-db.ps1 -k bump      # bump 関連のテストのみ実行
#   .\scripts\test-with-db.ps1 --keep       # テスト後コンテナを停止しない

param(
    [switch]$keep,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$pytestArgs
)

$ErrorActionPreference = "Stop"

# スクリプトのディレクトリからプロジェクトルートを取得
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir

Push-Location $ProjectDir

try {
    # テスト用 PostgreSQL コンテナを起動
    Write-Host "Starting test PostgreSQL container..." -ForegroundColor Cyan
    docker compose -f docker-compose.test.yml up -d

    # PostgreSQL が準備完了するまで待機
    Write-Host "Waiting for PostgreSQL to be ready..." -ForegroundColor Cyan
    $maxRetries = 30
    $retryCount = 0
    do {
        $result = docker compose -f docker-compose.test.yml exec -T test-db pg_isready -U test_user -d discord_util_bot_test 2>$null
        if ($LASTEXITCODE -eq 0) {
            break
        }
        $retryCount++
        if ($retryCount -ge $maxRetries) {
            throw "PostgreSQL did not become ready in time"
        }
        Start-Sleep -Seconds 1
    } while ($true)

    Write-Host "PostgreSQL is ready!" -ForegroundColor Green

    # 環境変数を設定
    $env:DISCORD_TOKEN = "test-token"
    $env:TEST_DATABASE_URL = "postgresql+asyncpg://test_user:test_pass@localhost:5432/discord_util_bot_test"
    $env:TEST_DATABASE_URL_SYNC = "postgresql://test_user:test_pass@localhost:5432/discord_util_bot_test"

    # テスト実行
    Write-Host "Running tests..." -ForegroundColor Cyan

    # venv のパスを OS に応じて設定
    $pythonPath = if ($IsWindows -or $env:OS -eq "Windows_NT") {
        ".venv\Scripts\python.exe"
    } else {
        ".venv/bin/python"
    }

    if (Test-Path $pythonPath) {
        & $pythonPath -m pytest @pytestArgs
    } else {
        # venv が無い場合はシステムの python を使用
        python -m pytest @pytestArgs
    }

    $testExitCode = $LASTEXITCODE
}
finally {
    # 環境変数をクリア
    Remove-Item Env:DISCORD_TOKEN -ErrorAction SilentlyContinue
    Remove-Item Env:TEST_DATABASE_URL -ErrorAction SilentlyContinue
    Remove-Item Env:TEST_DATABASE_URL_SYNC -ErrorAction SilentlyContinue

    # コンテナを停止 (-keep オプションがない場合)
    if (-not $keep) {
        Write-Host "Stopping test PostgreSQL container..." -ForegroundColor Cyan
        docker compose -f docker-compose.test.yml down
    }

    Pop-Location
}

exit $testExitCode
