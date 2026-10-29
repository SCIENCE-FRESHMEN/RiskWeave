param(
    [ValidateSet('verify', 'replay', 'benchmark')][string]$Mode = 'verify',
    [ValidateRange(2, 100000)][int]$Episodes = 50,
    [int]$SeedStart = 1000,
    [string]$OutputPath
)
$ErrorActionPreference = 'Stop'
$taskPython = $env:RISKWEAVE_PYTHON
if (-not $taskPython) {
    $bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    if (Test-Path -LiteralPath $bundledPython) {
        $taskPython = $bundledPython
    } else {
        $pythonCommand = Get-Command python3.exe, python.exe -ErrorAction SilentlyContinue |
            Where-Object { $_.Source -notlike '*\WindowsApps\*' } | Select-Object -First 1
        if ($pythonCommand) { $taskPython = $pythonCommand.Source }
    }
}
if (-not $taskPython -or -not (Test-Path -LiteralPath $taskPython)) {
    throw 'Set RISKWEAVE_PYTHON to a Python 3.10+ executable path.'
}
Push-Location $PSScriptRoot
try {
    if ($Mode -eq 'verify') {
        foreach ($script in @('tools/verify_workspace.py', 'tools/check_runtime_storage.py', 'tools/check_selective_replanning.py', 'tools/check_fortress_overlay.py', 'tools/check_randomized_invariants.py', 'tools/check_simulation_resources.py')) {
            & $taskPython -B $script
            if ($LASTEXITCODE -ne 0) { throw "Verification failed: $script" }
        }
    } elseif ($Mode -eq 'replay') {
        & $taskPython -B tools/run_selective_replay.py
        if ($LASTEXITCODE -ne 0) { throw 'Replay failed.' }
    } else {
        if (-not $OutputPath) {
            $runId = [Guid]::NewGuid().ToString('N').Substring(0, 8)
            $OutputPath = Join-Path 'artifacts' "benchmark-$runId"
        }
        & $taskPython -B tools/run_selective_benchmark.py --episodes $Episodes --seed-start $SeedStart --output $OutputPath
        if ($LASTEXITCODE -ne 0) { throw 'Benchmark failed.' }
    }
} finally {
    Pop-Location
}
