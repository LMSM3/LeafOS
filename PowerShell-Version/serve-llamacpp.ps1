#!/usr/bin/env pwsh
<#
Start a persistent llama.cpp HTTP provider for LeafOS.

This is intentionally different from chat-local.ps1:
- chat-local.ps1 runs llama-cli for one foreground conversation.
- serve-llamacpp.ps1 runs llama-server as a long-lived provider endpoint.

For Vulkan acceleration, point LEAF_LLAMACPP_DIR or --llama-dir at a
llama.cpp Windows Vulkan build, for example a directory extracted from:
  llama-<tag>-bin-win-vulkan-x64.zip
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Installer = Join-Path $Root 'ProjectLeaf\leaf_model_installer'
$DefaultCache = Join-Path $Installer 'models'
$HomeCache = Join-Path $HOME '.leaf\models'

$Model = 'fable'
$ModelPath = ''
$ModelDir = ''
$LlamaDir = ''
$HostAddress = '127.0.0.1'
$Port = 8080
$Ctx = 4096
$GpuLayers = 999
$Threads = 0
$Parallel = 1
$Batch = 2048
$UBatch = 512
$Reasoning = 'off'
$Alias = 'leaf-local'
$Backend = 'vulkan'
$CheckOnly = $false
$ExtraArgs = @()

function Write-Usage {
    @'
LeafOS llama.cpp provider server

Usage:
  .\serve-llamacpp.ps1 [--backend vulkan|cpu|auto] [--model fable]

Examples:
  .\serve-llamacpp.ps1 --backend vulkan --model fable --ctx 4096
  .\serve-llamacpp.ps1 --llama-dir C:\llama-vulkan --model-path C:\models\coder.gguf
  .\serve-llamacpp.ps1 --check-only --llama-dir C:\llama-vulkan

Options:
  --llama-dir PATH      Directory containing llama-server.exe
  --model-dir PATH      Override model cache root
  --model-path PATH     Exact .gguf model path
  --model NAME          opus|fable|fable-q2|fable-q3|fable-q6|fable-q8|qwen|qwopus
  --host ADDRESS        Listen address; use 0.0.0.0 for LAN
  --port N              HTTP port, default 8080
  --ctx N               Context size
  --gpu-layers N        Layers to offload; 999 means as many as fit
  --threads N           CPU threads; 0 lets llama.cpp choose
  --parallel N          Server slots
  --batch N             Logical batch size
  --ubatch N            Physical micro-batch size
  --reasoning on|off|auto
  --alias NAME          API model alias
  --backend vulkan|cpu|auto
  --check-only          Validate backend visibility, then exit
  --                    Pass remaining arguments directly to llama-server

Provider environment for another shell:
  $env:LEAF_PROVIDER_MODE = 'llamacpp'
  $env:LEAF_LLAMACPP_URL = 'http://127.0.0.1:8080'
'@ | Write-Host
}

function Get-Value {
    param(
        [string[]]$Values,
        [int]$Index,
        $InlineValue,
        [string]$Name
    )
    if ($null -ne $InlineValue) {
        return [pscustomobject]@{ Value = $InlineValue; Index = $Index }
    }
    $next = $Index + 1
    if ($next -ge $Values.Count) {
        throw "Missing value after $Name"
    }
    return [pscustomobject]@{ Value = $Values[$next]; Index = $next }
}

$RawArgs = @($args)
$i = 0
while ($i -lt $RawArgs.Count) {
    $arg = [string]$RawArgs[$i]
    if ($arg -eq '--') {
        if ($i + 1 -lt $RawArgs.Count) {
            $script:ExtraArgs = @($RawArgs[($i + 1)..($RawArgs.Count - 1)])
        }
        break
    }

    $name = $arg
    $inline = $null
    if ($arg -match '^(--?[^=]+)=(.*)$') {
        $name = $Matches[1]
        $inline = $Matches[2]
    }

    $nameLower = $name.ToLowerInvariant()
    if ($nameLower -in @('--llama-dir', '-llamadir')) {
        $got = Get-Value -Values $RawArgs -Index $i -InlineValue $inline -Name $name
        $LlamaDir = [string]$got.Value
        $i = [int]$got.Index
    }
    elseif ($nameLower -in @('--model', '-model', '-m')) {
        $got = Get-Value -Values $RawArgs -Index $i -InlineValue $inline -Name $name
        $Model = [string]$got.Value
        $i = [int]$got.Index
    }
    elseif ($nameLower -in @('--model-dir', '-modeldir')) {
        $got = Get-Value -Values $RawArgs -Index $i -InlineValue $inline -Name $name
        $ModelDir = [string]$got.Value
        $i = [int]$got.Index
    }
    elseif ($nameLower -in @('--model-path', '-modelpath')) {
        $got = Get-Value -Values $RawArgs -Index $i -InlineValue $inline -Name $name
        $ModelPath = [string]$got.Value
        $i = [int]$got.Index
    }
    elseif ($nameLower -in @('--host', '-host')) {
        $got = Get-Value -Values $RawArgs -Index $i -InlineValue $inline -Name $name
        $HostAddress = [string]$got.Value
        $i = [int]$got.Index
    }
    elseif ($nameLower -in @('--port', '-port')) {
        $got = Get-Value -Values $RawArgs -Index $i -InlineValue $inline -Name $name
        $Port = [int]$got.Value
        $i = [int]$got.Index
    }
    elseif ($nameLower -in @('--ctx', '-ctx', '-c')) {
        $got = Get-Value -Values $RawArgs -Index $i -InlineValue $inline -Name $name
        $Ctx = [int]$got.Value
        $i = [int]$got.Index
    }
    elseif ($nameLower -in @('--gpu-layers', '--n-gpu-layers', '-ngl')) {
        $got = Get-Value -Values $RawArgs -Index $i -InlineValue $inline -Name $name
        $GpuLayers = [int]$got.Value
        $i = [int]$got.Index
    }
    elseif ($nameLower -in @('--threads', '-threads', '-t')) {
        $got = Get-Value -Values $RawArgs -Index $i -InlineValue $inline -Name $name
        $Threads = [int]$got.Value
        $i = [int]$got.Index
    }
    elseif ($nameLower -in @('--parallel', '-np')) {
        $got = Get-Value -Values $RawArgs -Index $i -InlineValue $inline -Name $name
        $Parallel = [int]$got.Value
        $i = [int]$got.Index
    }
    elseif ($nameLower -in @('--batch', '-b')) {
        $got = Get-Value -Values $RawArgs -Index $i -InlineValue $inline -Name $name
        $Batch = [int]$got.Value
        $i = [int]$got.Index
    }
    elseif ($nameLower -in @('--ubatch', '-ub')) {
        $got = Get-Value -Values $RawArgs -Index $i -InlineValue $inline -Name $name
        $UBatch = [int]$got.Value
        $i = [int]$got.Index
    }
    elseif ($nameLower -in @('--reasoning', '-reasoning')) {
        $got = Get-Value -Values $RawArgs -Index $i -InlineValue $inline -Name $name
        $Reasoning = [string]$got.Value
        $i = [int]$got.Index
    }
    elseif ($nameLower -in @('--alias', '-a')) {
        $got = Get-Value -Values $RawArgs -Index $i -InlineValue $inline -Name $name
        $Alias = [string]$got.Value
        $i = [int]$got.Index
    }
    elseif ($nameLower -in @('--backend', '-backend')) {
        $got = Get-Value -Values $RawArgs -Index $i -InlineValue $inline -Name $name
        $Backend = ([string]$got.Value).ToLowerInvariant()
        $i = [int]$got.Index
    }
    elseif ($nameLower -in @('--check-only', '-checkonly')) {
        $CheckOnly = $true
    }
    elseif ($nameLower -in @('--help', '-help', '-h')) {
        Write-Usage
        exit 0
    }
    else {
        throw "Unknown serve-llamacpp option: $arg"
    }
    $i++
}

if ($Backend -notin @('vulkan', 'cpu', 'auto')) {
    throw "--backend must be vulkan, cpu, or auto"
}

function Test-AnyLocalGguf {
    param([string]$Path)
    if (-not (Test-Path $Path -PathType Container)) { return $false }
    return [bool](Get-ChildItem -LiteralPath $Path -Recurse -File -Filter '*.gguf' -ErrorAction SilentlyContinue | Select-Object -First 1)
}

function Resolve-ModelRoot {
    if ($ModelDir) { return $ModelDir }
    if ($env:LEAF_MODEL_DIR) { return $env:LEAF_MODEL_DIR }
    if (Test-AnyLocalGguf -Path $DefaultCache) { return $DefaultCache }
    return $HomeCache
}

function Join-ModelPath {
    param([string]$RootPath, [string]$Folder, [string]$File)
    return (Join-Path (Join-Path $RootPath $Folder) $File)
}

function Resolve-LlamaDir {
    if ($LlamaDir) { return $LlamaDir }
    if ($env:LEAF_LLAMACPP_DIR) { return $env:LEAF_LLAMACPP_DIR }

    $candidates = @(
        (Join-Path $Root 'tmp\llama-cpp-win-vulkan-b9828'),
        (Join-Path $Root 'tmp\llama-cpp-win-vulkan'),
        (Join-Path $Root 'tmp\llama-cpp-win-cpu-b9828')
    )
    foreach ($candidate in $candidates) {
        if (Test-Path (Join-Path $candidate 'llama-server.exe') -PathType Leaf) {
            return $candidate
        }
    }
    return $candidates[0]
}

$ModelRoot = Resolve-ModelRoot
if (-not $ModelPath) {
    switch ($Model.ToLowerInvariant()) {
        { $_ -in @('opus', 'assistant', 'main', 'scheduler', 'sage') } {
            $ModelPath = Join-ModelPath $ModelRoot 'Gemma4-Opus-Assistant' 'gemma4-opus48-Q4_K_M.gguf'
        }
        { $_ -in @('fable', 'coder', 'forge', 'fable-q4', 'coder-q4', 'gemma4-coder') } {
            $ModelPath = Join-ModelPath $ModelRoot 'Gemma4-Coder' 'gemma4-coding-Q4_K_M.gguf'
        }
        { $_ -in @('fable-q2', 'coder-q2') } {
            $ModelPath = Join-ModelPath $ModelRoot 'Gemma4-Coder' 'gemma4-coding-Q2_K.gguf'
        }
        { $_ -in @('fable-q3', 'coder-q3') } {
            $ModelPath = Join-ModelPath $ModelRoot 'Gemma4-Coder' 'gemma4-coding-Q3_K_M.gguf'
        }
        { $_ -in @('fable-q6', 'coder-q6') } {
            $ModelPath = Join-ModelPath $ModelRoot 'Gemma4-Coder' 'gemma4-coding-Q6_K.gguf'
        }
        { $_ -in @('fable-q8', 'coder-q8') } {
            $ModelPath = Join-ModelPath $ModelRoot 'Gemma4-Coder' 'gemma4-coding-Q8_0.gguf'
        }
        { $_ -in @('qwen', 'reasoning', 'oracle', 'scheduler-fallback') } {
            $ModelPath = Join-ModelPath $ModelRoot 'Qwen3.5-Claude-Reasoning' 'Qwen3.5-14B-A3B-Claude-Opus-Reasoning-Distilled-4.6-MXFP4_MOE.gguf'
        }
        { $_ -in @('qwopus', 'swift', 'secondary', 'legacy-coder') } {
            $ModelPath = Join-ModelPath $ModelRoot 'Qwopus3.5-9B-Coder-MTP' 'Qwopus3.5-9B-Coder-MTP-Q4_K_M.gguf'
        }
        default {
            throw "Unknown model alias: $Model"
        }
    }
}

$ResolvedLlamaDir = Resolve-LlamaDir
$LlamaServer = Join-Path $ResolvedLlamaDir 'llama-server.exe'
if (-not (Test-Path $LlamaServer -PathType Leaf)) {
    throw "llama-server.exe not found: $LlamaServer"
}
if (-not (Test-Path $ModelPath -PathType Leaf)) {
    throw "model file not found: $ModelPath"
}

$deviceOutput = & $LlamaServer --list-devices 2>&1 | Out-String
$hasDevice = ($deviceOutput -match '\S') -and ($deviceOutput -notmatch '^\s*Available devices:\s*$')
$hasVulkanDll = [bool](Get-ChildItem -LiteralPath $ResolvedLlamaDir -File -Filter '*vulkan*.dll' -ErrorAction SilentlyContinue | Select-Object -First 1)

if ($Backend -eq 'vulkan' -and -not $hasDevice) {
    Write-Host ''
    Write-Host 'llama.cpp Vulkan device check failed.' -ForegroundColor Yellow
    Write-Host "llama dir: $ResolvedLlamaDir"
    Write-Host ''
    Write-Host 'llama-server --list-devices returned:'
    Write-Host $deviceOutput
    Write-Host 'This usually means the selected llama.cpp build is CPU-only.'
    Write-Host 'Use a Windows x64 Vulkan build, then pass --llama-dir or set LEAF_LLAMACPP_DIR.'
    exit 3
}

if ($Backend -eq 'auto' -and -not $hasDevice) {
    $GpuLayers = 0
}

Write-Host ''
Write-Host 'LeafOS llama.cpp provider' -ForegroundColor Cyan
Write-Host "llama:  $LlamaServer"
Write-Host "model:  $ModelPath"
Write-Host "url:    http://$HostAddress`:$Port"
Write-Host "alias:  $Alias"
Write-Host "backend requested: $Backend"
Write-Host "device visible:    $hasDevice"
Write-Host "vulkan dll found:  $hasVulkanDll"
Write-Host ''
Write-Host 'Provider env for another shell:' -ForegroundColor DarkCyan
Write-Host "`$env:LEAF_PROVIDER_MODE = 'llamacpp'"
Write-Host "`$env:LEAF_LLAMACPP_URL = 'http://127.0.0.1:$Port'"
Write-Host ''

if ($CheckOnly) {
    exit 0
}

$serverArgs = @(
    '-m', $ModelPath,
    '--host', $HostAddress,
    '--port', [string]$Port,
    '-c', [string]$Ctx,
    '-b', [string]$Batch,
    '-ub', [string]$UBatch,
    '-np', [string]$Parallel,
    '-a', $Alias,
    '--metrics',
    '--jinja',
    '-rea', $Reasoning
)

if ($GpuLayers -gt 0) {
    $serverArgs += @('-ngl', [string]$GpuLayers)
}
else {
    $serverArgs += @('--device', 'none')
}

if ($Threads -ne 0) {
    $serverArgs += @('--threads', [string]$Threads)
}
if ($Reasoning -eq 'off') {
    $serverArgs += @('--reasoning-budget', '0')
}
if ($ExtraArgs.Count -gt 0) {
    $serverArgs += $ExtraArgs
}

Push-Location $ResolvedLlamaDir
try {
    & $LlamaServer @serverArgs
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
