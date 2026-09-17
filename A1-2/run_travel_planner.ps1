param(
    [Parameter(Position = 0)]
    [string]$Date
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$entrypoint = Join-Path $projectRoot 'main.py'

Set-Location -LiteralPath $projectRoot

try {
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        throw 'Virtual environment was not found. Run: python -m venv .venv'
    }
    if (-not (Test-Path -LiteralPath $entrypoint -PathType Leaf)) {
        throw 'main.py was not found in the project folder.'
    }

    if ([string]::IsNullOrWhiteSpace($Date)) {
        $today = (Get-Date).ToString('yyyy-MM-dd')
        $useToday = Read-Host "오늘 날짜($today)로 여행하시겠습니까? [Y/n]"
        if ([string]::IsNullOrWhiteSpace($useToday) -or $useToday -match '^(?i)(y|yes|예|네)$') {
            $Date = $today
        }
        else {
            $Date = Read-Host '여행 날짜를 입력하세요 (YYYY-MM-DD)'
        }
    }
    if ([string]::IsNullOrWhiteSpace($Date)) {
        throw '여행 날짜가 필요합니다.'
    }

    & $python '-X' 'utf8' $entrypoint '-date' $Date
    $exitCode = $LASTEXITCODE
    Write-Host "`n프로그램이 종료되었습니다. 종료 코드: $exitCode"
}
catch {
    $exitCode = 1
    Write-Host "`n오류: $($_.Exception.Message)" -ForegroundColor Red
}
finally {
    Read-Host 'Enter 키를 누르면 닫힙니다'
}

exit $exitCode
