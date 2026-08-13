#!/usr/bin/env pwsh
# bin/leafctl.ps1 -- LeafOS CLI entry for Windows / PowerShell 7+
# Usage: pwsh -File bin/leafctl.ps1 <command> [args]
# Parse manually so child flags such as `python -c` are never rebound as
# abbreviated parameters of this wrapper.
$Command = if ($args.Count -gt 0) { [string]$args[0] } else { 'home' }
[string[]]$Rest = @($args | Select-Object -Skip 1)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

switch ($Command) {
    'q'   { $Command = 'quick' }
    'h'   { $Command = 'home' }
    's'   { $Command = 'status' }
    'd'   { $Command = 'doctor' }
    'r'   { $Command = 'runtime'; $Rest = @('select') + $Rest }
    'p'   { $Command = 'provider-stack'; $Rest = @('check') + $Rest }
    't'   { $Command = 'trace'; $Rest = @('latest') + $Rest }
    'ref' { $Command = 'reference' }
    'b'   { $Command = 'bloom'; $Rest = @('status') + $Rest }
    'm'   { $Command = 'flower-monitor' }
    'c'   { $Command = 'chat' }
    'go'  { $Command = 'live' }
    'vtop' { $Command = 'vtop' }
    'identity' { $Command = 'pack-identity'; $Rest = @('generate') + $Rest }
}

$ScriptDir = Split-Path $MyInvocation.MyCommand.Path
$RootDir   = Split-Path $ScriptDir
if (-not $env:LEAF_ROOT) { $env:LEAF_ROOT = $RootDir }

$ModPath = Join-Path $RootDir 'core' 'powershell' 'LeafOS.psm1'
if (-not (Test-Path $ModPath)) { Write-Error "LeafOS.psm1 not found: $ModPath"; exit 1 }
Import-Module $ModPath -Force

switch ($Command) {
    'doctor' {
        $unknownDoctorArgs = @($Rest | Where-Object { $_ -ne '--json' })
        if ($unknownDoctorArgs.Count -gt 0) {
            Write-Error "unknown doctor option: $($unknownDoctorArgs[0])"
            exit 2
        }
        if ($Rest -contains '--json') {
            $report = Get-LeafDoctorReport -Root $RootDir
            $report | ConvertTo-Json -Depth 10 -Compress
            if (-not $report.ready) { exit 1 }
        } elseif (-not (Invoke-LeafDoctor -Root $RootDir)) {
            exit 1
        }
    }
    'status'   { Invoke-LeafStatus  -Root $RootDir }
    { $_ -in @('flower-monitor', 'monitor') } {
        & (Join-Path $RootDir 'bin\flower-monitor.ps1') @Rest
        exit $LASTEXITCODE
    }
    'vtop' {
        # leaf-monitor.ps1 expects -DurationSeconds.
        # Rebuild named parameter from remaining tokens.
        $monitorArgs = @{}
        for ($i = 0; $i -lt $Rest.Count; $i++) {
            switch ($Rest[$i]) {
                '--duration-seconds'  { $monitorArgs['DurationSeconds'] = [int]$Rest[++$i] }
                '-duration-seconds'   { $monitorArgs['DurationSeconds'] = [int]$Rest[++$i] }
            }
        }
        & (Join-Path $RootDir 'bin\leaf-monitor.ps1') @monitorArgs
        exit 0
    }
    'loaders'  { Get-LeafLoaders }
    'loader'   { Invoke-LeafLoader  -Name ($Rest[0] ?? 'orbit') -Label ($Rest[1] ?? 'loading') }
    'glyph' {
        $knownFlags = @('--ascii', '--json')
        $unknownFlags = @($Rest | Where-Object { $_.StartsWith('--') -and $_ -notin $knownFlags })
        $positionals = @($Rest | Where-Object { $_ -notin $knownFlags })
        if ($unknownFlags.Count -gt 0) { Write-Error "unknown glyph option: $($unknownFlags[0])"; exit 1 }
        if ($positionals.Count -ne 1) { Write-Error 'glyph requires exactly one ALIAS'; exit 1 }
        try {
            $glyphObject = Get-LeafGlyphObject -Alias $positionals[0] -Ascii:($Rest -contains '--ascii')
        } catch {
            Write-Error $_.Exception.Message
            exit 1
        }
        if ($Rest -contains '--json') {
            $glyphObject | ConvertTo-Json -Depth 8 -Compress
        } else {
            '{0}{1}{2}' -f $glyphObject.glyph, "`t", $glyphObject.meaning
        }
    }
    'glyphs' {
        $knownFlags = @('--ascii', '--json')
        $unknownFlags = @($Rest | Where-Object { $_.StartsWith('--') -and $_ -notin $knownFlags })
        $positionals = @($Rest | Where-Object { $_ -notin $knownFlags })
        if ($unknownFlags.Count -gt 0) { Write-Error "unknown glyphs option: $($unknownFlags[0])"; exit 1 }
        if ($positionals.Count -gt 1) { Write-Error 'glyphs accepts at most one CATEGORY'; exit 1 }
        $category = if ($positionals.Count -eq 1) { $positionals[0] } else { '' }
        $asciiMode = $Rest -contains '--ascii'
        if ($Rest -contains '--json') {
            Get-LeafGlyphRegistry -Category $category -Ascii:$asciiMode |
                ConvertTo-Json -Depth 12 -Compress
        } else {
            Get-LeafGlyphList -Category $category -Ascii:$asciiMode |
                Select-Object @{Name='Glyph';Expression={$_.glyph}},
                    @{Name='Alias';Expression={$_.alias}},
                    @{Name='Category';Expression={$_.category}},
                    @{Name='Severity';Expression={$_.severity}},
                    @{Name='Meaning';Expression={$_.meaning}} |
                Format-Table -AutoSize
        }
    }
    'alert'    { Write-LeafAlert -Severity ($Rest[0] ?? 'warn') -Message (($Rest | Select-Object -Skip 1) -join ' ') }
    'versions' { Get-LeafVersions }
    'platform' { Get-LeafPlatform | Format-List }
    { $_ -in @('home','next','menu','trace','accelerator','model-profile','tui','quick','reference') } {
        $bash = (Get-Command bash -ErrorAction SilentlyContinue)?.Source
        $preferBash = $env:LEAF_PREFER_BASH -eq '1'
        function Invoke-LeafPy {
            param([string]$ScriptRel)
            $py = (Get-Command python3 -ErrorAction SilentlyContinue)?.Source ??
                  (Get-Command python  -ErrorAction SilentlyContinue)?.Source
            if (-not $py) {
                if (-not $bash) { Write-Error 'python3 not found'; exit 1 }
                & $bash (Join-Path $RootDir $ScriptRel) @Rest
            } else {
                & $py (Join-Path $RootDir $ScriptRel) @Rest
            }
            exit $LASTEXITCODE
        }
        switch ($Command) {
            'home'        { Invoke-LeafPy 'core\ui\home.py' }
            'next'        { Invoke-LeafPy 'core\ui\home.py' --next @Rest }
            'menu'        { Invoke-LeafPy 'core\ui\menu.py' }
            'trace'       { Invoke-LeafPy 'core\ui\trace.py' }
            'accelerator' { Invoke-LeafPy 'core\ui\accelerator_state.py' }
            'model-profile' { Invoke-LeafPy 'core\runtime\model_profiles.py' }
            'tui'         { Invoke-LeafPy 'core\ui\tui\main.py' }
            'quick' {
                if ($preferBash -and $bash) { & $bash (Join-Path $RootDir 'core' 'ui' 'quick_syntax') @Rest }
                else { Invoke-LeafPy 'core\ui\quick_syntax.py' }
            }
            'reference' {
                if ($preferBash -and $bash) { & $bash (Join-Path $RootDir 'core' 'ui' 'reference') @Rest }
                else { Invoke-LeafPy 'core\ui\reference.py' }
            }
        }
        exit $LASTEXITCODE
    }
    'memory' {
        & (Join-Path $RootDir 'bin' 'leaf-memory.ps1') @Rest
        exit $LASTEXITCODE
    }
    'pack-identity' {
        $py = (Get-Command python3 -ErrorAction SilentlyContinue)?.Source ??
              (Get-Command python  -ErrorAction SilentlyContinue)?.Source
        if (-not $py) { Write-Error 'python3 not found'; exit 1 }
        & $py (Join-Path $RootDir 'core' 'pack_identity_cli.py') @Rest
        exit $LASTEXITCODE
    }
    'provider-stack' {
        $providerScript = Join-Path $RootDir 'bin' 'vulkan-provider.ps1'
        if (-not (Test-Path $providerScript -PathType Leaf)) {
            Write-Error "vulkan-provider.ps1 not found: $providerScript"
            exit 1
        }
        & $providerScript -Action ($Rest[0] ?? 'check') -Json:($Rest -contains '--json')
        exit $LASTEXITCODE
    }
    'oneshot' {
        $oneShotScript = Join-Path $RootDir 'bin\leaf-oneshot.ps1'
        if (-not (Test-Path $oneShotScript -PathType Leaf)) {
            Write-Error "leaf-oneshot.ps1 not found: $oneShotScript"
            exit 1
        }
        & $oneShotScript @Rest
        if ($?) { exit 0 }
        exit 1
    }
    'wakeup' {
        $py = (Get-Command python3 -ErrorAction SilentlyContinue)?.Source ??
              (Get-Command python  -ErrorAction SilentlyContinue)?.Source
        if (-not $py) { Write-Error 'python3 not found'; exit 1 }
        & $py (Join-Path $RootDir 'examples' 'WO-004-C' 'wakeup.py') @Rest
        exit $LASTEXITCODE
    }
    'wakeup-export' {
        $py = (Get-Command python3 -ErrorAction SilentlyContinue)?.Source ??
              (Get-Command python  -ErrorAction SilentlyContinue)?.Source
        if (-not $py) { Write-Error 'python3 not found'; exit 1 }
        & $py (Join-Path $RootDir 'examples' 'WO-004-C' 'export.py') @Rest
        exit $LASTEXITCODE
    }
    'runtime' {
        $RestItems = @($Rest)
        $Sub = if ($RestItems.Count -gt 0) { $RestItems[0] } else { 'select' }
        [string[]]$RuntimeArgsList = if ($RestItems.Count -gt 1) { @($RestItems | Select-Object -Skip 1) } else { @() }
        $AsJson = $RuntimeArgsList -contains '--json'
        $ValueOf = {
            param([string]$Name)
            [object[]]$items = @()
            if ($null -ne $RuntimeArgsList) { $items = @($RuntimeArgsList) }
            for ($i = 0; $i -lt $items.Length; $i++) {
                if ($items[$i] -eq $Name -and ($i + 1) -lt $items.Length) { return $items[$i + 1] }
                if ($items[$i] -like "$Name=*") { return $items[$i].Substring($Name.Length + 1) }
            }
            return ''
        }

        switch ($Sub) {
            { $_ -in @('select','status') } {
                $sel = New-LeafRuntimeSelection `
                    -Root $RootDir `
                    -MainModel (& $ValueOf '--main') `
                    -SchedulerModel (& $ValueOf '--scheduler') `
                    -CoderModel (& $ValueOf '--coder') `
                    -CodingLanguage (& $ValueOf '--language') `
                    -CodingModelChoice (& $ValueOf '--coding-model') `
                    -CodingTier (& $ValueOf '--coding-tier') `
                    -Persona (& $ValueOf '--persona') `
                    -Mode (& $ValueOf '--mode')
                if ($AsJson) {
                    $sel | ConvertTo-Json -Depth 16 -Compress
                } else {
                    Write-LeafMsg 'LeafOS runtime selection'
                    Write-Host "  main          : $($sel.MainModel.key) ($($sel.MainModel.quant))"
                    Write-Host "  scheduler     : $($sel.SchedulerModel.key) ($($sel.SchedulerModel.quant))"
                    Write-Host "  coder         : $($sel.CoderModel.key) ($($sel.CoderModel.default_quant))"
                    Write-Host "  coding choice : $($sel.CodingChoice.language) / $($sel.CodingChoice.model_key) / $($sel.CodingChoice.tier)"
                    Write-Host "  persona       : $($sel.Persona.key) / $($sel.Persona.voice)"
                    Write-Host "  mode          : $($sel.Mode)"
                    Write-Host "  language hint : $($sel.LanguageHint)"
                    Write-Host "  workers       : $(if (@($sel.Workers).Count) { (@($sel.Workers).name -join ', ') } else { 'suppressed' })"
                }
            }
            { $_ -in @('validate','doctor') } {
                $null = New-LeafRuntimeSelection -Root $RootDir
                Write-LeafMsg 'runtime config valid'
            }
            'personas' {
                $items = Get-LeafPersonas -Root $RootDir
                if ($AsJson) { $items | ConvertTo-Json -Depth 10 -Compress }
                else { $items | Select-Object key, voice, code_policy, default_language, care_mode | Format-Table -AutoSize }
            }
            'models' {
                $rt = (Get-LeafRuntimeConfig -Root $RootDir).leafos_runtime
                if ($AsJson) {
                    [pscustomobject]@{ main_models = $rt.main_models; scheduler_models = $rt.main_models; coder_models = $rt.coder_models; role_policy = $rt.role_policy } |
                        ConvertTo-Json -Depth 16 -Compress
                } else {
                    Write-LeafMsg 'runtime main models'
                    $rt.main_models | Select-Object key, role, quant | Format-Table -AutoSize
                    Write-LeafMsg 'runtime scheduler models'
                    $rt.main_models | Select-Object key, role, quant | Format-Table -AutoSize
                    Write-LeafMsg 'runtime coder models'
                    $rt.coder_models | Select-Object key, role, default_quant | Format-Table -AutoSize
                }
            }
            'workers' {
                if ($RuntimeArgsList.Count -lt 1) { Write-Error 'runtime workers requires CONFIDENCE'; exit 1 }
                $confidence = [double]$RuntimeArgsList[0]
                if ($confidence -lt 0 -or $confidence -gt 1) { Write-Error 'confidence must be 0.0 through 1.0'; exit 1 }
                $reasons = @($RuntimeArgsList | Select-Object -Skip 1 | Where-Object { $_ -ne '--json' })
                $sel = New-LeafRuntimeSelection -Root $RootDir
                $names = @('scout','sketch','builder')
                if ($confidence -lt 0.8) { $names += 'reviewer' }
                if ($confidence -lt 0.5) { $names += 'hardcheck' }
                if ($reasons.Count -gt 0) { $names += @('reviewer','hardcheck') }
                if ($reasons | Where-Object { $_ -in @('finalizer','final_pass','checkpoint') }) { $names += 'finalizer' }
                $names = $names | Select-Object -Unique
                $workers = @($sel.CoderModel.tiers | Where-Object { $_.name -in $names })
                $out = [pscustomobject]@{ confidence_score = ('{0:0.###}' -f $confidence); coder_model = $sel.CoderModel.key; reasons = $reasons; workers = $workers }
                if ($AsJson) { $out | ConvertTo-Json -Depth 12 -Compress }
                else { $workers | Select-Object name, quant, mode, purpose | Format-Table -AutoSize }
            }
            'event' {
                if ($RuntimeArgsList.Count -lt 2) { Write-Error 'runtime event requires TYPE CONFIDENCE CONTENT'; exit 1 }
                $content = if ($RuntimeArgsList.Count -gt 2) { ($RuntimeArgsList | Select-Object -Skip 2) -join ' ' } else { '' }
                New-LeafRuntimeEvent -Root $RootDir -ResponseType $RuntimeArgsList[0] -ConfidenceScore ([double]$RuntimeArgsList[1]) -Content $content |
                    ConvertTo-Json -Compress
            }
            default {
                Write-LeafMsg "unknown runtime subcommand: $Sub" -Level error
                exit 1
            }
        }
    }
    'web-state' {
        $py = (Get-Command python3 -ErrorAction SilentlyContinue)?.Source ??
              (Get-Command python  -ErrorAction SilentlyContinue)?.Source
        if (-not $py) { Write-Error 'python3 not found'; exit 1 }
        & $py (Join-Path $RootDir 'core' 'web' 'state.py') @Rest
        exit $LASTEXITCODE
    }
    'fullstackbench' {
        $py = (Get-Command python3 -ErrorAction SilentlyContinue)?.Source ??
              (Get-Command python  -ErrorAction SilentlyContinue)?.Source
        if (-not $py) { Write-Error 'python3 not found'; exit 1 }
        & $py (Join-Path $RootDir 'core' 'bench' 'fullstackbench.py') @Rest
        exit $LASTEXITCODE
    }
    'telemetry' {
        $py = (Get-Command python3 -ErrorAction SilentlyContinue)?.Source ??
              (Get-Command python  -ErrorAction SilentlyContinue)?.Source
        if (-not $py) { Write-Error 'python3 not found'; exit 1 }
        & $py (Join-Path $RootDir 'core' 'python' 'leaf_telemetry.py') @Rest
        exit $LASTEXITCODE
    }
    'bloom' {
        $py = (Get-Command python3 -ErrorAction SilentlyContinue)?.Source ??
              (Get-Command python  -ErrorAction SilentlyContinue)?.Source
        if (-not $py) { Write-Error 'python3 not found (continual bloom requires Python 3.10+)'; exit 1 }
        & $py (Join-Path $RootDir 'core' 'python' 'leaf_continual_bloom.py') @Rest
        exit $LASTEXITCODE
    }
    'realbench' {
        $py = (Get-Command python3 -ErrorAction SilentlyContinue)?.Source ??
              (Get-Command python  -ErrorAction SilentlyContinue)?.Source
        if (-not $py) { Write-Error 'python3 not found'; exit 1 }
        & $py (Join-Path $RootDir 'core' 'bench' 'realbench.py') @Rest
        exit $LASTEXITCODE
    }
    'live' {
        $py = (Get-Command python3 -ErrorAction SilentlyContinue)?.Source ??
              (Get-Command python  -ErrorAction SilentlyContinue)?.Source
        if (-not $py) { Write-Error 'python3 not found'; exit 1 }
        & $py (Join-Path $RootDir 'core' 'python' 'leaf_live_project.py') @Rest
        exit $LASTEXITCODE
    }
    'resident' {
        $py = (Get-Command python3 -ErrorAction SilentlyContinue)?.Source ??
              (Get-Command python  -ErrorAction SilentlyContinue)?.Source
        if (-not $py) { Write-Error 'python3 not found'; exit 1 }
        & $py (Join-Path $RootDir 'core' 'python' 'leaf_resident_supervisor.py') @Rest
        exit $LASTEXITCODE
    }
    'chat' {
        $bash = (Get-Command bash -ErrorAction SilentlyContinue)?.Source
        if ($bash) {
            & $bash (Join-Path $RootDir 'core' 'ui' 'chat_json') @Rest
        } else {
            $py = (Get-Command python3 -ErrorAction SilentlyContinue)?.Source ??
                  (Get-Command python  -ErrorAction SilentlyContinue)?.Source
            if (-not $py) { Write-Error 'python3 not found'; exit 1 }
            & $py (Join-Path $RootDir 'core' 'ui' 'chat.py') @Rest
        }
        exit $LASTEXITCODE
    }
    'model' {
        $bash = (Get-Command bash -ErrorAction SilentlyContinue)?.Source
        if ($bash) {
            & $bash (Join-Path $RootDir 'core' 'ui' 'chat_json') model @Rest
        } else {
            $py = (Get-Command python3 -ErrorAction SilentlyContinue)?.Source ??
                  (Get-Command python  -ErrorAction SilentlyContinue)?.Source
            if (-not $py) { Write-Error 'python3 not found'; exit 1 }
            & $py (Join-Path $RootDir 'core' 'ui' 'chat.py') model @Rest
        }
        exit $LASTEXITCODE
    }
    'dashboard' {
        $preferBash = $env:LEAF_PREFER_BASH -eq '1'
        if ($preferBash -and ($Rest -contains '--json' -or $Rest -contains '--watch')) {
            $bash = (Get-Command bash -ErrorAction SilentlyContinue)?.Source
            if ($bash) { & $bash (Join-Path $RootDir 'core' 'ui' 'dashboard_json') @Rest; exit $LASTEXITCODE }
        }
        $py = (Get-Command python3 -ErrorAction SilentlyContinue)?.Source ??
              (Get-Command python  -ErrorAction SilentlyContinue)?.Source
        if (-not $py) { Write-Error 'python3 not found'; exit 1 }
        & $py (Join-Path $RootDir 'core' 'ui' 'dashboard.py') @Rest
        exit $LASTEXITCODE
    }
    'test' {
        $py = (Get-Command python3 -ErrorAction SilentlyContinue)?.Source ??
              (Get-Command python  -ErrorAction SilentlyContinue)?.Source
        if (-not $py) { Write-Error 'python3 not found'; exit 1 }
        [string[]]$TestArgs = @($Rest)
        if ($TestArgs.Count -gt 0 -and $TestArgs[0] -eq 'visual') {
            $TestArgs = @($TestArgs | Select-Object -Skip 1)
        } elseif ($TestArgs.Count -gt 0 -and -not $TestArgs[0].StartsWith('--')) {
            Write-Error "unknown test mode: $($TestArgs[0])"
            exit 1
        }
        & $py (Join-Path $RootDir 'core' 'testing' 'visual_test_runner.py') @TestArgs
        exit $LASTEXITCODE
    }
    'loop' {
        $py = (Get-Command python3 -ErrorAction SilentlyContinue)?.Source ??
              (Get-Command python  -ErrorAction SilentlyContinue)?.Source
        if (-not $py) { Write-Error 'python3 not found (loop inlet requires Python 3.10+)'; exit 1 }
        & $py (Join-Path $RootDir 'core' 'python' 'leaf_loop_inlet.py') @Rest
        exit $LASTEXITCODE
    }
    'transport' {
        if ($Rest.Count -lt 1 -or $Rest[0] -ne 'usb') {
            Write-Error 'transport requires the usb subcommand'
            exit 1
        }
        $py = (Get-Command python3 -ErrorAction SilentlyContinue)?.Source ??
              (Get-Command python  -ErrorAction SilentlyContinue)?.Source
        if (-not $py) { Write-Error 'python3 not found (USB interceptor requires Python 3.10+)'; exit 1 }
        [string[]]$TransportArgs = @($Rest | Select-Object -Skip 1)
        & $py (Join-Path $RootDir 'core' 'python' 'leaf_usb_interceptor.py') @TransportArgs
        exit $LASTEXITCODE
    }
    'passive-report' {
        $reportScript = Join-Path $RootDir 'bin' 'leaf-passive-report.ps1'
        if (-not (Test-Path -LiteralPath $reportScript -PathType Leaf)) {
            Write-Error "passive-report script not found: $reportScript"
            exit 1
        }
        $pwsh = (Get-Command pwsh -ErrorAction SilentlyContinue)?.Source
        if (-not $pwsh) {
            Write-Error 'pwsh is required for the passive-report forwarding boundary'
            exit 1
        }
        if ($Rest -contains '--help' -or $Rest -contains '-h') {
            & $pwsh -NoProfile -File $reportScript -Help
        } else {
            & $pwsh -NoProfile -File $reportScript @Rest
        }
        exit $LASTEXITCODE
    }
    { $_ -in @('agent-loop-start','sandbox-create') } {
        $py = (Get-Command python3 -ErrorAction SilentlyContinue)?.Source ??
              (Get-Command python  -ErrorAction SilentlyContinue)?.Source
        if (-not $py) { Write-Error 'python3 not found'; exit 1 }
        if ($Command -eq 'agent-loop-start' -and $Rest -contains '--work-order') {
            & $py (Join-Path $RootDir 'core' 'python' 'leaf_loop_inlet.py') start @Rest
        } else {
            & $py (Join-Path $RootDir 'core' 'python' 'leaf_agent_loop.py') create @Rest
        }
        exit $LASTEXITCODE
    }
    'agent-loop-status' {
        $py = (Get-Command python3 -ErrorAction SilentlyContinue)?.Source ??
              (Get-Command python  -ErrorAction SilentlyContinue)?.Source
        if (-not $py) { Write-Error 'python3 not found'; exit 1 }
        & $py (Join-Path $RootDir 'core' 'python' 'leaf_agent_loop.py') status @Rest
        exit $LASTEXITCODE
    }
    { $_ -in @('agent-loop-tick','sandbox-run') } {
        $py = (Get-Command python3 -ErrorAction SilentlyContinue)?.Source ??
              (Get-Command python  -ErrorAction SilentlyContinue)?.Source
        if (-not $py) { Write-Error 'python3 not found'; exit 1 }
        & $py (Join-Path $RootDir 'core' 'python' 'leaf_agent_loop.py') tick @Rest
        exit $LASTEXITCODE
    }
    'agent-loop-resume' {
        $py = (Get-Command python3 -ErrorAction SilentlyContinue)?.Source ??
              (Get-Command python  -ErrorAction SilentlyContinue)?.Source
        if (-not $py) { Write-Error 'python3 not found'; exit 1 }
        & $py (Join-Path $RootDir 'core' 'python' 'leaf_agent_loop.py') resume @Rest
        exit $LASTEXITCODE
    }
    'agent-loop-stop' {
        $py = (Get-Command python3 -ErrorAction SilentlyContinue)?.Source ??
              (Get-Command python  -ErrorAction SilentlyContinue)?.Source
        if (-not $py) { Write-Error 'python3 not found'; exit 1 }
        & $py (Join-Path $RootDir 'core' 'python' 'leaf_agent_loop.py') stop @Rest
        exit $LASTEXITCODE
    }
    'agent-loop-report' {
        $py = (Get-Command python3 -ErrorAction SilentlyContinue)?.Source ??
              (Get-Command python  -ErrorAction SilentlyContinue)?.Source
        if (-not $py) { Write-Error 'python3 not found'; exit 1 }
        & $py (Join-Path $RootDir 'core' 'python' 'leaf_agent_loop.py') report @Rest
        exit $LASTEXITCODE
    }
    'chat' {
        $py = (Get-Command python3 -ErrorAction SilentlyContinue)?.Source ??
              (Get-Command python  -ErrorAction SilentlyContinue)?.Source
        if (-not $py) { Write-Error 'python3 not found'; exit 1 }
        & $py (Join-Path $RootDir 'core' 'ui' 'chat.py') @Rest
    }
    'model' {
        $py = (Get-Command python3 -ErrorAction SilentlyContinue)?.Source ??
              (Get-Command python  -ErrorAction SilentlyContinue)?.Source
        if (-not $py) { Write-Error 'python3 not found'; exit 1 }
        & $py (Join-Path $RootDir 'core' 'ui' 'chat.py') model @Rest
    }
    'hf' {
        $hfScript = Join-Path $RootDir 'bin' 'leaf-hf'
        if (-not (Test-Path -LiteralPath $hfScript -PathType Leaf)) {
            Write-Error "leaf-hf not found: $hfScript"; exit 1
        }
        $bash = @(Get-Command bash -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source;
                  'C:\msys64\usr\bin\bash.exe', 'C:\Program Files\Git\bin\bash.exe') |
                Where-Object { Test-Path $_ } | Select-Object -First 1
        if (-not $bash) { Write-Error 'bash is required for leaf-hf'; exit 1 }
        & $bash -l "$hfScript" @Rest
        exit $LASTEXITCODE
    }
    'stack' {
        $py = (Get-Command python3 -ErrorAction SilentlyContinue)?.Source ??
              (Get-Command python  -ErrorAction SilentlyContinue)?.Source
        if (-not $py) { Write-Error 'python3 not found'; exit 1 }
        & $py (Join-Path $RootDir 'core' 'stack' 'stack_cli.py') @Rest
        exit $LASTEXITCODE
    }
    'pack' {
        $py = (Get-Command python3 -ErrorAction SilentlyContinue)?.Source ??
              (Get-Command python  -ErrorAction SilentlyContinue)?.Source
        if (-not $py) { Write-Error 'python3 not found'; exit 1 }
        & $py (Join-Path $RootDir 'core' 'pack_constructor_cli.py') @Rest
        exit $LASTEXITCODE
    }
    'indicator' {
        & (Join-Path $RootDir 'bin' 'leaf-indicator.ps1') @Rest
        if ($?) { exit 0 }
        exit 1
    }
    { $_ -eq 'ccis' -or ($_ -eq 'task' -and $Rest.Count -gt 0 -and $Rest[0] -eq 'accept') } {
        $py = (Get-Command python3 -ErrorAction SilentlyContinue)?.Source ??
              (Get-Command python  -ErrorAction SilentlyContinue)?.Source
        if (-not $py -and (Test-Path 'C:\msys64\ucrt64\bin\python.exe')) {
            $py = 'C:\msys64\ucrt64\bin\python.exe'
        }
        if (-not $py) { Write-Error 'python3 not found'; exit 1 }
        $RepoRoot = Split-Path (Split-Path $RootDir)
        $CcisCli = Join-Path $RepoRoot 'ccis\cli.py'
        if (-not (Test-Path -LiteralPath $CcisCli -PathType Leaf)) {
            Write-Error "CCIS CLI not found: $CcisCli"; exit 1
        }
        [string[]]$CcisArgs = if ($Command -eq 'task') {
            @('accept') + @($Rest | Select-Object -Skip 1)
        } else {
            @($Rest)
        }
        & $py $CcisCli @CcisArgs
        exit $LASTEXITCODE
    }
    'models-install' {
        $modelsInstallDir = Join-Path (Split-Path $RootDir) 'leaf_model_installer'
        $venvPython = Join-Path $modelsInstallDir '.venv' 'Scripts' 'python.exe'
        if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
            Write-Error "model installer venv not found: $venvPython"
            exit 1
        }
        # Prefer a project-local venv; fall back to system python for the module.
        $env:PYTHONPATH = $modelsInstallDir
        & $venvPython -c "from leaf_models.install_cli import main; import sys; sys.exit(main(sys.argv[1:]))" @Rest
        exit $LASTEXITCODE
    }
    '' {
        Write-Host 'Usage: leaf <command> [args]'
        Write-Host ''
        Write-Host 'Native PS:  home  tui  live  resident  next  trace  accelerator  doctor  status  flower-monitor  monitor  vtop  loaders  loader  glyph  glyphs  alert  versions  platform  memory  runtime  model-profile  web-state  fullstackbench  realbench  telemetry  test  loop  transport  passive-report  agent-loop-start/status/tick/resume/stop/report  oneshot  wakeup  wakeup-export  chat  model  pack  indicator  pack-identity  models-install'
        Write-Host 'Loop monitor: loop monitor [RUN|active] [--interactive|--noninteractive] [--json|--jsonl] [--once]'
        Write-Host 'USB interceptor: transport usb init|status|pump|publish|validate ...'
        Write-Host 'Passive HTML: passive-report [-RunRoot RUN] [-StartProject -Project DIR] [-Open] [-Watch] [-Json]'
        Write-Host 'Glyph objects: glyph ALIAS [--ascii] [--json]; glyphs [CATEGORY] [--ascii] [--json]'
        Write-Host 'Via bash:   node  nodes  task  agent-task  agent-plan  agent-route  agent-validate  agent-dry-run  agent-run  agent-report  serve  download  dist-*  motd  spin  provider-status  ...'
        exit 1
    }
    default {
        $nativeCommands = @(
            'home','next','trace','accelerator','doctor','status','flower-monitor','monitor',
            'loaders','loader','glyph','glyphs','alert','versions','platform','memory','runtime',
            'model-profile','tui','quick','reference','dashboard','web-state','fullstackbench',
            'realbench','telemetry','test','loop','transport','passive-report',
            'agent-loop-start','agent-loop-status','agent-loop-tick','agent-loop-resume',
            'agent-loop-stop','agent-loop-report','oneshot','wakeup','wakeup-export','chat',
            'model','stack','bloom','flower-monitor','live','resident','provider-stack','ccis','task',
            'vtop','pack','indicator','pack-identity','models-install'
        )
        $ls = ($Command | Select-String '^[a-zA-Z0-9_-]+$') ? $Command : ''
        $suggestion = if ($ls) { ($nativeCommands | Where-Object { $_ -like "$ls*" -or $ls -like "$_*" } | Select-Object -First 3) -join ', ' } else { '' }

        # GAP-003 fix: bash-forward fallback -- full 40+ command surface from PowerShell
        $candidates = @(
            'C:\msys64\usr\bin\bash.exe',
            'C:\Program Files\Git\bin\bash.exe'
        ) | Where-Object { Test-Path $_ }
        $bashCmd = Get-Command bash -ErrorAction SilentlyContinue
        if ($bashCmd) { $candidates += $bashCmd.Source }
        $bash = $candidates | Where-Object { $_ } | Select-Object -First 1
        if (-not $bash) {
            $hint = if ($suggestion) { " Did you mean: $suggestion?" } else { "" }
            Write-LeafMsg ("unknown command: '$Command'  (bash not found; try '.\leafos.ps1 q')$hint") -Level error
            exit 1
        }
        if ($suggestion) {
            Write-LeafMsg "unknown command: '$Command'. Did you mean: $suggestion?" -Level warn
        }
        $ctl = (Join-Path $RootDir 'bin' 'leafctl').Replace('\','/')
        if ($ctl -match '^([A-Za-z]):') { $ctl = '/' + $Matches[1].ToLower() + $ctl.Substring(2) }
        $parts = (@($Command) + $Rest) | ForEach-Object { "'" + ($_ -replace "'","'\''") + "'" }
        & $bash -l -c ($ctl + ' ' + ($parts -join ' '))
        exit $LASTEXITCODE
    }
}
