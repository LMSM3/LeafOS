#!/usr/bin/env pwsh
<#
Start a simple local llama.cpp chat against the real LeafOS model cache.

This script parses arguments manually so both PowerShell style
  .\chat-local.ps1 -Model opus -Prompt "hello"
and shell style
  .\chat-local.ps1 --model opus --prompt "hello"
work from the top-level LeafOS launchers.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Installer = Join-Path $Root 'ProjectLeaf\leaf_model_installer'
$DefaultCache = Join-Path $Installer 'models'
$HomeCache = Join-Path $HOME '.leaf\models'
$LlamaDir = Join-Path $Root 'tmp\llama-cpp-win-cpu-b9828'
$Llama = Join-Path $LlamaDir 'llama-cli.exe'

$Model = 'opus'
$ModelPath = ''
$ModelDir = ''
$Prompt = ''
$SystemPrompt = 'You are LeafOS local runtime. Be concise, practical, and honest about uncertainty.'
$Ctx = 4096
$Threads = 0
$Tokens = 256
$Temp = '0.7'
$Reasoning = 'off'
$NoWsl = $false

function Write-Usage {
    @'
LeafOS local chat

Usage:
  .\chat-local.ps1 [--model opus|fable|qwen|qwopus] [--prompt TEXT]

Examples:
  .\chat-local.ps1 --model opus
  .\chat-local.ps1 --model fable --prompt "Write a tiny PowerShell hello-world."
  .\chat-local.ps1 --model qwen --prompt "Make a 3-step plan."

Options:
  --model-dir PATH       Override the model cache root
  --model-path PATH      Use an exact .gguf file
  --system TEXT          System prompt
  --ctx N                Context size
  --threads N            CPU threads; 0 lets llama.cpp choose
  --tokens N             Maximum generated tokens
  --temp N               Temperature
  --reasoning on|off|auto
  --no-wsl               Skip WSL and use the Windows llama.cpp binary
'@ | Write-Host
}

$RawArgs = [string[]]@($args)
for ($i = 0; $i -lt $RawArgs.Count; $i++) {
    $arg = [string]$RawArgs[$i]
    $name = $arg
    $value = $null
    $hasInlineValue = $false
    if ($arg -match '^(--?[^=]+)=(.*)$') {
        $name = $Matches[1]
        $value = $Matches[2]
        $hasInlineValue = $true
    }

    $normalized = $name.ToLowerInvariant()
    $valueOptions = @(
        '--model', '-model', '-m',
        '--model-dir', '-model-dir', '-modeldir',
        '--model-path', '-model-path', '-modelpath',
        '--prompt', '-prompt', '-p',
        '--system', '--system-prompt', '-system', '-system-prompt', '-systemprompt',
        '--ctx', '-ctx', '-c',
        '--threads', '-threads', '-t',
        '--tokens', '-tokens', '-n',
        '--temp', '--temperature', '-temp', '-temperature',
        '--reasoning', '-reasoning'
    )
    if ($normalized -in $valueOptions -and -not $hasInlineValue) {
        if (($i + 1) -ge $RawArgs.Count) {
            throw "Missing value after $name"
        }
        $value = [string]$RawArgs[$i + 1]
        $i++
    }

    if ($normalized -in @('--model', '-model', '-m')) { $Model = $value }
    elseif ($normalized -in @('--model-dir', '-model-dir', '-modeldir')) { $ModelDir = $value }
    elseif ($normalized -in @('--model-path', '-model-path', '-modelpath')) { $ModelPath = $value }
    elseif ($normalized -in @('--prompt', '-prompt', '-p')) { $Prompt = $value }
    elseif ($normalized -in @('--system', '--system-prompt', '-system', '-system-prompt', '-systemprompt')) { $SystemPrompt = $value }
    elseif ($normalized -in @('--ctx', '-ctx', '-c')) { $Ctx = $value }
    elseif ($normalized -in @('--threads', '-threads', '-t')) { $Threads = $value }
    elseif ($normalized -in @('--tokens', '-tokens', '-n')) { $Tokens = $value }
    elseif ($normalized -in @('--temp', '--temperature', '-temp', '-temperature')) { $Temp = $value }
    elseif ($normalized -in @('--reasoning', '-reasoning')) { $Reasoning = $value }
    elseif ($normalized -in @('--no-wsl', '-nowsl', '-no-wsl')) { $NoWsl = $true }
    elseif ($normalized -in @('--help', '-help', '-h')) { Write-Usage; exit 0 }
    else { throw "Unknown chat-local option: $arg" }
}

if ($Ctx -lt 1) { throw '--ctx must be greater than zero' }
if ($Threads -lt 0) { throw '--threads must be zero or greater' }
if ($Tokens -lt 1) { throw '--tokens must be greater than zero' }
$ParsedTemp = 0.0
if (-not [double]::TryParse($Temp, [Globalization.NumberStyles]::Float, [Globalization.CultureInfo]::InvariantCulture, [ref]$ParsedTemp)) {
    throw '--temp must be a number'
}
if ($Reasoning.ToLowerInvariant() -notin @('on', 'off', 'auto')) {
    throw '--reasoning must be on, off, or auto'
}

function Test-AnyLocalGguf {
    param([string]$Path)
    if (-not (Test-Path $Path -PathType Container)) { return $false }
    return [bool](Get-ChildItem -LiteralPath $Path -Recurse -File -Filter '*.gguf' -ErrorAction SilentlyContinue | Select-Object -First 1)
}

function Resolve-ModelRoot {
    if ($ModelDir) { return (Resolve-Path -LiteralPath $ModelDir -ErrorAction Stop).Path }
    if ($env:LEAF_MODEL_DIR) { return (Resolve-Path -LiteralPath $env:LEAF_MODEL_DIR -ErrorAction Stop).Path }
    if (Test-AnyLocalGguf -Path $DefaultCache) { return $DefaultCache }
    return $HomeCache
}

function Join-ModelPath {
    param([string]$RootPath, [string]$Folder, [string]$File)
    return (Join-Path (Join-Path $RootPath $Folder) $File)
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
$ModelPath = [IO.Path]::GetFullPath($ModelPath)
if ($Model.ToLowerInvariant() -in @('fable-q2', 'coder-q2')) {
    throw "The Q2 Fable model is incompatible with this llama.cpp runtime and produces malformed output. Use --model fable-q3 or --model fable (Q4_K_M)."
}
}

$ForwardArgs = @(
    '--model', $Model,
    '--model-dir', $ModelRoot,
    '--system', $SystemPrompt,
    '--ctx', [string]$Ctx,
    '--tokens', [string]$Tokens,
    '--temp', [string]$Temp,
    '--reasoning', [string]$Reasoning
)
if ($Threads -ne 0) { $ForwardArgs += @('--threads', [string]$Threads) }
if ($Prompt) { $ForwardArgs += @('--prompt', $Prompt) }
if ($ModelPath) { $ForwardArgs += @('--model-path', $ModelPath) }

if (-not $NoWsl) {
    $wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    $bashScript = Join-Path $Root 'Bash-Version\chat-local.sh'
    if ($wsl -and (Test-Path $bashScript -PathType Leaf)) {
        try {
            $wslFriendlyRoot = $Root -replace '\\', '/'
            $wslRoot = (& wsl.exe wslpath -a $wslFriendlyRoot).Trim()
            $wslScript = "$wslRoot/Bash-Version/chat-local.sh"
            & wsl.exe --cd $wslRoot --exec /bin/bash --noprofile --norc $wslScript @ForwardArgs
            $code = $LASTEXITCODE
            if ($code -eq 0) { exit 0 }
            if ($code -eq 130) { exit 130 }
            Write-Warning "WSL local chat exited with code $code; trying the Windows llama.cpp binary."
        }
        catch {
            Write-Warning "WSL local chat was unavailable: $($_.Exception.Message). Trying Windows fallback."
        }
    }
}

if (-not (Test-Path $Llama -PathType Leaf)) {
    throw "llama.cpp chat binary not found: $Llama"
}
if (-not (Test-Path $ModelPath -PathType Leaf)) {
    throw "model file not found: $ModelPath"
}

Write-Host 'LeafOS local chat' -ForegroundColor Cyan
Write-Host "model: $ModelPath"
if ($Prompt) {
    Write-Host 'mode:  single turn'
}
else {
    Write-Host 'mode:  interactive conversation. Press Ctrl+C to leave.'
}
Write-Host ''

$llamaArgs = @(
    '-m', $ModelPath,
    '-c', [string]$Ctx,
    '-n', [string]$Tokens,
    '--temp', [string]$Temp,
    '-cnv',
    '--simple-io',
    '--no-display-prompt',
    '--no-show-timings',
    '--no-warmup',
    '-rea', [string]$Reasoning,
    '-sys', $SystemPrompt
)
if ($Reasoning -eq 'off') { $llamaArgs += @('--reasoning-budget', '0') }
if ($Threads -ne 0) { $llamaArgs += @('--threads', [string]$Threads) }
if ($Prompt) { $llamaArgs += @('-st', '-p', $Prompt) }

Push-Location $LlamaDir
try {
    & $Llama @llamaArgs
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
