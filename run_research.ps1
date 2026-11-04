param(
    [ValidateSet('verify', 'replay', 'benchmark')][string]$Mode = 'verify',
    [ValidateRange(2, 100000)][int]$Episodes = 50,
    [int]$SeedStart = 1000,
    [string]$OutputPath
)
$ErrorActionPreference = 'Stop'
$taskPython = $env:RISKWEAVE_PYTHON
$pyLauncherArgs = @()
if (-not $taskPython -or -not (Test-Path -LiteralPath $taskPython)) {
    $pythonCommand = Get-Command python3.exe, python.exe -ErrorAction SilentlyContinue |
        Where-Object { $_.Source -notlike '*\WindowsApps\*' } | Select-Object -First 1
    if ($pythonCommand) {
        $taskPython = $pythonCommand.Source
    } elseif (Get-Command py.exe -ErrorAction SilentlyContinue) {
        # Windows py launcher fallback: "py -3" resolves an installed Python 3.
        $taskPython = (Get-Command py.exe).Source
        $pyLauncherArgs = @('-3')
    }
}
if (-not $taskPython -or -not (Test-Path -LiteralPath $taskPython)) {
    throw 'Set RISKWEAVE_PYTHON to a Python 3.10+ executable path.'
}
function Invoke-Python([string[]]$ScriptArgs) {
    & $taskPython @pyLauncherArgs -B @ScriptArgs
    if ($LASTEXITCODE -ne 0) { throw "Python exited with code $LASTEXITCODE." }
}
Push-Location $PSScriptRoot
try {
    if ($Mode -eq 'verify') {
        foreach ($script in @('tools/verify_workspace.py', 'tools/check_runtime_storage.py', 'tools/check_selective_replanning.py', 'tools/check_fortress_overlay.py', 'tools/check_randomized_invariants.py', 'tools/check_simulation_resources.py')) {
            Invoke-Python @($script)
        }
    } elseif ($Mode -eq 'replay') {
        Invoke-Python @('tools/run_selective_replay.py')
    } else {
        if (-not $OutputPath) {
            $runId = [Guid]::NewGuid().ToString('N').Substring(0, 8)
            $OutputPath = Join-Path 'artifacts' "benchmark-$runId"
        }
        Invoke-Python @('tools/run_selective_benchmark.py', '--episodes', $Episodes, '--seed-start', $SeedStart, '--output', $OutputPath)
    }
} finally {
    Pop-Location
}
