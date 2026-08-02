#!/usr/bin/env pwsh
<#
LeafOS one-shot bundle creator.

Examples:

  pwsh -File .\bin\leafctl.ps1 oneshot
  pwsh -File .\bin\leafctl.ps1 oneshot --oneshot . C:\R\LeafDemo
  pwsh -File .\bin\leaf-oneshot.ps1 --oneshot . C:\R\LeafDemo --force

The command creates a small handoff folder containing:

  README.md
  README.txt
  instructions.txt
  context.tex
  example.r
  infodata.xlsx
  run_demo.ps1
  model_check.ps1
  model_downloads.txt
  bundle_manifest.json
  stack_snapshot.txt
  leafos-oneshot.zip
#>

[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RawArgs = @()
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
try {
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
    $OutputEncoding = [Console]::OutputEncoding
}
catch {
    # Some redirected hosts do not expose a writable console encoding.
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Resolve-Path (Join-Path $ScriptDir '..')

function Write-LeafColor {
    param(
        [string]$Text = '',
        [ConsoleColor]$Color = [ConsoleColor]::Gray,
        [switch]$NoNewLine
    )
    if ($NoNewLine) {
        Write-Host $Text -ForegroundColor $Color -NoNewline
    }
    else {
        Write-Host $Text -ForegroundColor $Color
    }
}

function Write-LeafBanner {
    Write-Host ''
    Write-LeafColor '╔══════════════════════════════════════════════════════════════════════╗' Cyan
    Write-LeafColor '║                     LeafOS OneShot Bundle                          ║' Green
    Write-LeafColor '║       one command → handoff folder → zip → readable starter kit     ║' DarkCyan
    Write-LeafColor '╚══════════════════════════════════════════════════════════════════════╝' Cyan
    Write-Host ''
}

function Write-LeafStep {
    param([string]$Message)
    Write-LeafColor '  ꕤ ' Magenta -NoNewLine
    Write-LeafColor $Message White
}

function Write-LeafOk {
    param([string]$Message)
    Write-LeafColor '  ✓ ' Green -NoNewLine
    Write-LeafColor $Message Gray
}

function Write-LeafWarn {
    param([string]$Message)
    Write-LeafColor '  ! ' Yellow -NoNewLine
    Write-LeafColor $Message Yellow
}

function Show-LeafHelp {
    Write-LeafBanner
    Write-Host 'usage:'
    Write-Host '  pwsh -File .\bin\leafctl.ps1 oneshot'
    Write-Host '  pwsh -File .\bin\leafctl.ps1 oneshot --oneshot <source> <newlocation>'
    Write-Host ''
    Write-Host 'options:'
    Write-Host '  --oneshot           non-interactive mode'
    Write-Host '  --source PATH       source stack path'
    Write-Host '  --target PATH       new handoff folder'
    Write-Host '  --force             overwrite generated files if they already exist'
    Write-Host '  --no-zip            skip leafos-oneshot.zip creation'
    Write-Host '  --open              open the output folder when finished'
    Write-Host '  --dry-run           preview without writing files'
    Write-Host '  --help              show this help'
}

function ConvertTo-XmlText {
    param([AllowNull()][object]$Value)
    if ($null -eq $Value) { return '' }
    return [System.Security.SecurityElement]::Escape([string]$Value)
}

function ConvertTo-JsonText {
    param([object]$Value)
    $Value | ConvertTo-Json -Depth 12
}

function Resolve-LeafPath {
    param(
        [string]$Path,
        [string]$Base = (Get-Location).Path,
        [switch]$MustExist
    )
    if (-not $Path) { return '' }
    $expanded = [Environment]::ExpandEnvironmentVariables($Path)
    if (-not [System.IO.Path]::IsPathRooted($expanded)) {
        $expanded = Join-Path $Base $expanded
    }
    if ($MustExist) {
        return (Resolve-Path -LiteralPath $expanded).Path
    }
    return [System.IO.Path]::GetFullPath($expanded)
}

function Get-LeafArgumentValue {
    param(
        [string[]]$Items,
        [string]$Name
    )
    for ($i = 0; $i -lt $Items.Count; $i++) {
        if ($Items[$i] -eq $Name -and ($i + 1) -lt $Items.Count) {
            return $Items[$i + 1]
        }
        if ($Items[$i] -like "$Name=*") {
            return $Items[$i].Substring($Name.Length + 1)
        }
    }
    return ''
}

function Get-LeafPositionalArgs {
    param([string[]]$Items)
    $out = New-Object System.Collections.Generic.List[string]
    for ($i = 0; $i -lt $Items.Count; $i++) {
        $item = $Items[$i]
        switch -Regex ($item) {
            '^--(source|target)$' { $i++; continue }
            '^--(source|target)=' { continue }
            '^--(oneshot|force|no-zip|open|dry-run|help)$' { continue }
            default { [void]$out.Add($item) }
        }
    }
    return [string[]]$out.ToArray()
}

function New-LeafSimpleXlsx {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][object[]]$Rows
    )

    Add-Type -AssemblyName System.IO.Compression.FileSystem

    $temp = Join-Path ([System.IO.Path]::GetTempPath()) ("leafos-xlsx-" + [guid]::NewGuid().ToString('N'))
    $null = New-Item -ItemType Directory -Force -Path $temp

    try {
        $relsDir = Join-Path $temp '_rels'
        $xlDir = Join-Path $temp 'xl'
        $xlRelsDir = Join-Path $xlDir '_rels'
        $worksheetsDir = Join-Path $xlDir 'worksheets'
        $docPropsDir = Join-Path $temp 'docProps'
        New-Item -ItemType Directory -Force -Path $relsDir, $xlDir, $xlRelsDir, $worksheetsDir, $docPropsDir | Out-Null

        @'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>
'@ | Set-Content -LiteralPath (Join-Path $temp '[Content_Types].xml') -Encoding UTF8

        @'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>
'@ | Set-Content -LiteralPath (Join-Path $relsDir '.rels') -Encoding UTF8

        @'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="LeafOS Info" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>
'@ | Set-Content -LiteralPath (Join-Path $xlDir 'workbook.xml') -Encoding UTF8

        @'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>
'@ | Set-Content -LiteralPath (Join-Path $xlRelsDir 'workbook.xml.rels') -Encoding UTF8

        @'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>
  <fills count="1"><fill><patternFill patternType="none"/></fill></fills>
  <borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>
</styleSheet>
'@ | Set-Content -LiteralPath (Join-Path $xlDir 'styles.xml') -Encoding UTF8

        $created = ConvertTo-XmlText (Get-Date -Format o)
        @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>LeafOS OneShot Info</dc:title>
  <dc:creator>LeafOS</dc:creator>
  <dcterms:created xsi:type="dcterms:W3CDTF">$created</dcterms:created>
</cp:coreProperties>
"@ | Set-Content -LiteralPath (Join-Path $docPropsDir 'core.xml') -Encoding UTF8

        @'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>LeafOS</Application>
</Properties>
'@ | Set-Content -LiteralPath (Join-Path $docPropsDir 'app.xml') -Encoding UTF8

        $sheetRows = New-Object System.Collections.Generic.List[string]
        $rowIndex = 1
        foreach ($row in $Rows) {
            $a = ConvertTo-XmlText $row[0]
            $b = ConvertTo-XmlText $row[1]
            [void]$sheetRows.Add("<row r=`"$rowIndex`"><c r=`"A$rowIndex`" t=`"inlineStr`"><is><t>$a</t></is></c><c r=`"B$rowIndex`" t=`"inlineStr`"><is><t>$b</t></is></c></row>")
            $rowIndex++
        }
        $sheetData = $sheetRows -join "`n"
        @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
$sheetData
  </sheetData>
</worksheet>
"@ | Set-Content -LiteralPath (Join-Path $worksheetsDir 'sheet1.xml') -Encoding UTF8

        if (Test-Path $Path -PathType Leaf) {
            Remove-Item -LiteralPath $Path -Force
        }
        [System.IO.Compression.ZipFile]::CreateFromDirectory($temp, $Path)
    }
    finally {
        if (Test-Path $temp) {
            Remove-Item -LiteralPath $temp -Recurse -Force
        }
    }
}

function Set-LeafFile {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Content,
        [switch]$Force
    )
    if ((Test-Path $Path -PathType Leaf) -and -not $Force) {
        Write-LeafWarn "kept existing file: $Path"
        return
    }
    $Content | Set-Content -LiteralPath $Path -Encoding UTF8
    Write-LeafOk "wrote $(Split-Path -Leaf $Path)"
}

function New-LeafSnapshot {
    param([string]$Source)
    $items = Get-ChildItem -LiteralPath $Source -Force -ErrorAction SilentlyContinue |
        Select-Object -First 80 |
        ForEach-Object {
            $kind = if ($_.PSIsContainer) { 'dir ' } else { 'file' }
            '{0}  {1}' -f $kind, $_.Name
        }
    if (-not $items) { return '(no visible files)' }
    return ($items -join [Environment]::NewLine)
}

$argsList = if ($null -eq $RawArgs) { @() } else { @($RawArgs) }
if ($argsList -contains '--help' -or $argsList -contains '-h') {
    Show-LeafHelp
    exit 0
}

$oneShot = $argsList -contains '--oneshot'
$force = $argsList -contains '--force'
$noZip = $argsList -contains '--no-zip'
$open = $argsList -contains '--open'
$dryRun = $argsList -contains '--dry-run'

$sourceArg = Get-LeafArgumentValue $argsList '--source'
$targetArg = Get-LeafArgumentValue $argsList '--target'
$positionals = @(Get-LeafPositionalArgs $argsList)

if (-not $sourceArg -and $positionals.Count -ge 1) { $sourceArg = $positionals[0] }
if (-not $targetArg -and $positionals.Count -ge 2) { $targetArg = $positionals[1] }

Write-LeafBanner

if (-not $oneShot -and (-not $sourceArg -or -not $targetArg)) {
    Write-LeafColor 'Interactive mode. Press Enter to accept defaults.' DarkCyan
    if (-not $sourceArg) {
        $entered = Read-Host "Source stack path [$RootDir]"
        $sourceArg = if ($entered) { $entered } else { $RootDir }
    }
    if (-not $targetArg) {
        $entered = Read-Host 'New bundle location'
        if (-not $entered) { throw 'A new bundle location is required.' }
        $targetArg = $entered
    }
}

if (-not $sourceArg -or -not $targetArg) {
    Show-LeafHelp
    throw 'source and newlocation are required in --oneshot mode.'
}

$source = Resolve-LeafPath $sourceArg -MustExist
$target = Resolve-LeafPath $targetArg
$createdUtc = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
$targetName = Split-Path -Leaf $target
if (-not $targetName) { $targetName = 'LeafOS-OneShot' }

Write-LeafStep "source: $source"
Write-LeafStep "target: $target"
Write-LeafStep 'mode: one-shot handoff scaffold'

if ($dryRun) {
    Write-LeafWarn 'dry run only; no files written.'
    Write-Host ''
    Write-Host 'Would create: README.md, README.txt, instructions.txt, context.tex, example.r, infodata.xlsx, run_demo.ps1, model_check.ps1, model_downloads.txt, bundle_manifest.json, stack_snapshot.txt'
    if (-not $noZip) { Write-Host 'Would create: leafos-oneshot.zip' }
    exit 0
}

if (-not (Test-Path $target -PathType Container)) {
    New-Item -ItemType Directory -Force -Path $target | Out-Null
}

$snapshot = New-LeafSnapshot $source
$manifest = [ordered]@{
    name = $targetName
    created_utc = $createdUtc
    source = $source
    target = $target
    command = 'leafctl oneshot --oneshot <source> <newlocation>'
    safety = 'offline scaffold only; no model resolve/apply/download'
    files = @(
        'README.md',
        'README.txt',
        'instructions.txt',
        'context.tex',
        'example.r',
        'infodata.xlsx',
        'run_demo.ps1',
        'model_check.ps1',
        'model_downloads.txt',
        'bundle_manifest.json',
        'stack_snapshot.txt'
    )
}

$readmeMdTemplate = @'
# __TARGET_NAME__

LeafOS OneShot bundle created at `__CREATED_UTC__`.

This folder is a compact handoff kit generated from:

`__SOURCE__`

## Contents

- `README.md` — Markdown overview.
- `README.txt` — plain-text overview.
- `instructions.txt` — simple install and usage notes.
- `context.tex` — TeX context sheet.
- `example.r` — small R example.
- `infodata.xlsx` — spreadsheet metadata.
- `run_demo.ps1` — local demo helper.
- `model_check.ps1` — runtime model readiness and safe download helper.
- `model_downloads.txt` — plain-language model download decision sheet.
- `bundle_manifest.json` — machine-readable manifest.
- `stack_snapshot.txt` — source stack snapshot.
- `leafos-oneshot.zip` — compressed handoff copy.

## Quick start

```powershell
pwsh -File .\run_demo.ps1
```

## Safety

This bundle is offline. It does not resolve model metadata, apply model plans,
or download model weights.

## If default models are missing

Run:

```powershell
pwsh -File .\model_check.ps1
```

That creates or refreshes an offline `runtime-default` plan. It tells you what
to do next. It only downloads if you later run:

```powershell
pwsh -File .\model_check.ps1 -Resolve -Apply -Yes
```
'@

$readmeTextTemplate = @'
__TARGET_NAME__

LeafOS OneShot bundle created at __CREATED_UTC__.

Source:
__SOURCE__

Run:
pwsh -File .\run_demo.ps1

This bundle is offline. It does not download model weights.
'@

$instructionsTemplate = @'
LeafOS OneShot Instructions

A.) Installing

1. Open PowerShell.
2. Go to this folder:

   cd "__TARGET__"

3. Run the local demo:

   pwsh -File .\run_demo.ps1

4. Review these files:

   README.md
   README.txt
   context.tex
   example.r
   infodata.xlsx
   model_downloads.txt

B.) Usage

1. Read README.md for the friendly overview.
2. Read bundle_manifest.json for machine-readable metadata.
3. Open infodata.xlsx for the spreadsheet summary.
4. Run example.r in R if you want to inspect the bundle from R.
5. Run model_check.ps1 to inspect or prepare runtime model downloads.

If default models are missing:

   pwsh -File .\model_check.ps1

This writes an offline runtime-default plan.

To resolve exact remote files without downloading weights:

   pwsh -File .\model_check.ps1 -Resolve

To download or resume the required runtime defaults after review:

   pwsh -File .\model_check.ps1 -Resolve -Apply -Yes

Original stack source:
__SOURCE__

Safety:
- This bundle is an offline handoff.
- It does not resolve model metadata.
- It does not apply install plans.
- It does not download model weights unless model_check.ps1 is run with
  -Resolve -Apply -Yes.
'@

$contextTexTemplate = @'
\documentclass{article}
\usepackage[margin=1in]{geometry}
\title{LeafOS OneShot Context}
\author{LeafOS}
\date{__CREATED_UTC__}
\begin{document}
\maketitle

\section*{Purpose}
This document records the context for a compact LeafOS handoff bundle.

\section*{Source}
\begin{verbatim}
__SOURCE__
\end{verbatim}

\section*{Target}
\begin{verbatim}
__TARGET__
\end{verbatim}

\section*{Safety}
This bundle is offline. It does not resolve model metadata, apply model plans,
or download model weights.

\section*{Expected Files}
\begin{itemize}
  \item README.md
  \item README.txt
  \item instructions.txt
  \item context.tex
  \item example.r
  \item infodata.xlsx
  \item model_check.ps1
  \item model_downloads.txt
\end{itemize}

\end{document}
'@

$replacementPairs = @{
    '__TARGET_NAME__' = $targetName
    '__CREATED_UTC__' = $createdUtc
    '__SOURCE__' = $source
    '__TARGET__' = $target
}

function Expand-LeafTemplate {
    param([string]$Template)
    $expanded = $Template
    foreach ($key in $replacementPairs.Keys) {
        $expanded = $expanded.Replace($key, [string]$replacementPairs[$key])
    }
    return $expanded
}

$readmeMd = Expand-LeafTemplate $readmeMdTemplate
$readmeTextPlain = Expand-LeafTemplate $readmeTextTemplate
$instructions = Expand-LeafTemplate $instructionsTemplate
$contextTex = Expand-LeafTemplate $contextTexTemplate

$exampleR = @'
# LeafOS OneShot R example

cat("LeafOS OneShot bundle\n")
cat("Working directory:", getwd(), "\n\n")

files <- c(
  "README.md",
  "README.txt",
  "instructions.txt",
  "context.tex",
  "example.r",
  "infodata.xlsx",
  "bundle_manifest.json",
  "stack_snapshot.txt"
)

print(data.frame(
  file = files,
  exists = file.exists(files)
))

if (requireNamespace("readxl", quietly = TRUE)) {
  cat("\nReading infodata.xlsx with readxl:\n")
  print(readxl::read_excel("infodata.xlsx"))
} else {
  cat("\nPackage 'readxl' is not installed. Listing xlsx internals instead:\n")
  print(utils::unzip("infodata.xlsx", list = TRUE))
}
'@

$runDemo = @"
#!/usr/bin/env pwsh
Set-StrictMode -Version Latest
`$ErrorActionPreference = 'Stop'

Write-Host ''
Write-Host 'LeafOS OneShot bundle is ready.' -ForegroundColor Green
Write-Host ''
Write-Host 'Files:' -ForegroundColor Cyan
Get-ChildItem -File | Select-Object Name, Length | Format-Table -AutoSize
Write-Host ''
Write-Host 'Start here:' -ForegroundColor Cyan
Write-Host '  README.md'
Write-Host '  instructions.txt'
Write-Host '  infodata.xlsx'
Write-Host '  model_downloads.txt'
Write-Host ''
Write-Host 'If models are missing:' -ForegroundColor Cyan
Write-Host '  pwsh -File .\model_check.ps1'
Write-Host ''
Write-Host 'Safety: this local demo does not download anything.' -ForegroundColor Yellow
"@

$modelDownloads = @"
LeafOS Model Download Decision Sheet

Default runtime models:

1. gemma4-coder
   Role: primary local coder
   Quant: Q4_K_M

2. gemma4-opus-assistant
   Role: main planner / synthesizer / assistant
   Quant: Q4_K_M

If the proper default models are missing, do this:

1. Create an offline plan:

   pwsh -File .\model_check.ps1

2. Resolve exact remote files:

   pwsh -File .\model_check.ps1 -Resolve

3. Review the resolved plan in:

   plans\leaf-runtime-plan.resolved.json

4. Download or resume only after review:

   pwsh -File .\model_check.ps1 -Resolve -Apply -Yes

Important:

- Planning is offline.
- Resolve reads repository metadata but does not download weights.
- Apply is the download boundary.
- Apply requires -Yes.
- Existing partial downloads should resume through the Hugging Face cache.
- Experimental GPT-OSS 120B is not part of runtime-default.

Common choices:

- Just checking readiness:
  pwsh -File .\model_check.ps1

- Preparing exact download list:
  pwsh -File .\model_check.ps1 -Resolve

- Starting/resuming downloads:
  pwsh -File .\model_check.ps1 -Resolve -Apply -Yes
"@

$modelCheckTemplate = @'
#!/usr/bin/env pwsh
<#
model_check.ps1

Runtime model readiness helper for a LeafOS OneShot bundle.

Safe defaults:
- creates an offline runtime-default plan;
- does not resolve remote metadata unless -Resolve is used;
- does not download model weights unless -Apply -Yes is used.
#>

[CmdletBinding()]
param(
    [string]$ModelDir = '',
    [switch]$Resolve,
    [switch]$Apply,
    [switch]$Yes,
    [switch]$AllowFallback
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$BundleRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$SourceRoot = '__SOURCE__'
$InstallerRoot = Join-Path (Split-Path $SourceRoot) 'leaf_model_installer'
$PlansDir = Join-Path $BundleRoot 'plans'
$PlanPath = Join-Path $PlansDir 'leaf-runtime-plan.json'
$ResolvedPlanPath = Join-Path $PlansDir 'leaf-runtime-plan.resolved.json'

if (-not $ModelDir) {
    $ModelDir = if ($env:LEAF_MODEL_DIR) { $env:LEAF_MODEL_DIR } else { Join-Path $HOME '.leaf\models' }
}

function Write-Step {
    param([string]$Message)
    Write-Host '  ꕤ ' -ForegroundColor Magenta -NoNewline
    Write-Host $Message -ForegroundColor White
}

function Write-Ok {
    param([string]$Message)
    Write-Host '  ✓ ' -ForegroundColor Green -NoNewline
    Write-Host $Message
}

function Write-WarnLine {
    param([string]$Message)
    Write-Host '  ! ' -ForegroundColor Yellow -NoNewline
    Write-Host $Message -ForegroundColor Yellow
}

function Get-Python {
    $py = Get-Command python -ErrorAction SilentlyContinue
    if ($py) { return $py.Source }
    $py3 = Get-Command python3 -ErrorAction SilentlyContinue
    if ($py3) { return $py3.Source }
    return ''
}

function Invoke-LeafModels {
    param([Parameter(ValueFromRemainingArguments)][string[]]$Args)

    $cmd = Get-Command leaf-models -ErrorAction SilentlyContinue
    if ($cmd) {
        & $cmd.Source @Args
        return
    }

    $cmdFile = Join-Path $InstallerRoot 'leaf-models.cmd'
    if (Test-Path $cmdFile -PathType Leaf) {
        & $cmdFile @Args
        return
    }

    $python = Get-Python
    if (-not $python) {
        throw 'Python was not found. Install Python or run leaf_model_installer\install.ps1 from the source stack.'
    }

    $installCli = Join-Path $InstallerRoot 'leaf_models\install_cli.py'
    if (-not (Test-Path $installCli -PathType Leaf)) {
        throw "Leaf model installer source was not found: $InstallerRoot"
    }

    $oldPythonPath = $env:PYTHONPATH
    try {
        if ($oldPythonPath) {
            $env:PYTHONPATH = "$InstallerRoot;$oldPythonPath"
        }
        else {
            $env:PYTHONPATH = "$InstallerRoot"
        }
        & $python -B -m leaf_models.install_cli @Args
    }
    finally {
        $env:PYTHONPATH = $oldPythonPath
    }
}

Write-Host ''
Write-Host 'LeafOS runtime model readiness' -ForegroundColor Green
Write-Host ''
Write-Step "bundle: $BundleRoot"
Write-Step "models: $ModelDir"
Write-Step 'profile: runtime-default'

New-Item -ItemType Directory -Force -Path $PlansDir | Out-Null

$planArgs = @('plan', '--profile', 'runtime-default', '--dest', $ModelDir, '--out', $PlanPath)
if ($AllowFallback) { $planArgs += '--allow-fallback' }

Write-Host ''
Write-Step 'creating offline runtime-default plan'
Invoke-LeafModels @planArgs
Write-Ok "offline plan: $PlanPath"

if (-not $Resolve) {
    Write-Host ''
    Write-WarnLine 'No remote metadata was read and no model weights were downloaded.'
    Write-Host ''
    Write-Host 'If the default models are missing, next run:' -ForegroundColor Cyan
    Write-Host '  pwsh -File .\model_check.ps1 -Resolve'
    Write-Host ''
    Write-Host 'After reviewing the resolved plan, download/resume with:' -ForegroundColor Cyan
    Write-Host '  pwsh -File .\model_check.ps1 -Resolve -Apply -Yes'
    exit 0
}

Write-Host ''
Write-Step 'resolving exact remote files; this reads metadata only'
Invoke-LeafModels resolve $PlanPath --out $ResolvedPlanPath
Write-Ok "resolved plan: $ResolvedPlanPath"

if (-not $Apply) {
    Write-Host ''
    Write-WarnLine 'Resolved only. Model weights were not downloaded.'
    Write-Host ''
    Write-Host 'Review the resolved plan, then run:' -ForegroundColor Cyan
    Write-Host '  pwsh -File .\model_check.ps1 -Resolve -Apply -Yes'
    exit 0
}

if (-not $Yes) {
    throw 'Apply is the download boundary. Re-run with -Apply -Yes to start or resume downloads.'
}

Write-Host ''
Write-Step 'applying resolved plan; this downloads or resumes model weights'
Invoke-LeafModels apply $ResolvedPlanPath --yes
Write-Ok 'download/apply step completed'

Write-Host ''
Write-Step 'verifying resolved plan'
Invoke-LeafModels verify $ResolvedPlanPath
Write-Ok 'verification command finished'
'@

$modelCheck = $modelCheckTemplate.Replace('__SOURCE__', $source.Replace("'", "''"))

Set-LeafFile -Path (Join-Path $target 'README.md') -Content $readmeMd -Force:$force
Set-LeafFile -Path (Join-Path $target 'README.txt') -Content $readmeTextPlain -Force:$force
Set-LeafFile -Path (Join-Path $target 'instructions.txt') -Content $instructions -Force:$force
Set-LeafFile -Path (Join-Path $target 'context.tex') -Content $contextTex -Force:$force
Set-LeafFile -Path (Join-Path $target 'example.r') -Content $exampleR -Force:$force
Set-LeafFile -Path (Join-Path $target 'run_demo.ps1') -Content $runDemo -Force:$force
Set-LeafFile -Path (Join-Path $target 'model_check.ps1') -Content $modelCheck -Force:$force
Set-LeafFile -Path (Join-Path $target 'model_downloads.txt') -Content $modelDownloads -Force:$force
Set-LeafFile -Path (Join-Path $target 'bundle_manifest.json') -Content (ConvertTo-JsonText $manifest) -Force:$force
Set-LeafFile -Path (Join-Path $target 'stack_snapshot.txt') -Content $snapshot -Force:$force

$xlsxPath = Join-Path $target 'infodata.xlsx'
if ((Test-Path $xlsxPath -PathType Leaf) -and -not $force) {
    Write-LeafWarn "kept existing file: $xlsxPath"
}
else {
    $rows = @(
        @('Field', 'Value'),
        @('Created UTC', $createdUtc),
        @('Source', $source),
        @('Target', $target),
        @('Mode', 'oneshot'),
        @('Safety', 'offline scaffold only'),
        @('Primary files', 'README.md, README.txt, instructions.txt, context.tex, example.r, infodata.xlsx'),
        @('Model helper', 'model_check.ps1'),
        @('Model decision sheet', 'model_downloads.txt')
    )
    New-LeafSimpleXlsx -Path $xlsxPath -Rows $rows
    Write-LeafOk 'wrote infodata.xlsx'
}

if (-not $noZip) {
    $zipTemp = Join-Path ([System.IO.Path]::GetTempPath()) ("leafos-oneshot-" + [guid]::NewGuid().ToString('N') + '.zip')
    $zipPath = Join-Path $target 'leafos-oneshot.zip'
    if ((Test-Path $zipPath -PathType Leaf) -and -not $force) {
        Write-LeafWarn "kept existing file: $zipPath"
    }
    else {
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        if (Test-Path $zipTemp -PathType Leaf) { Remove-Item -LiteralPath $zipTemp -Force }
        if (Test-Path $zipPath -PathType Leaf) { Remove-Item -LiteralPath $zipPath -Force }
        [System.IO.Compression.ZipFile]::CreateFromDirectory($target, $zipTemp)
        Move-Item -LiteralPath $zipTemp -Destination $zipPath -Force
        Write-LeafOk 'wrote leafos-oneshot.zip'
    }
}

Write-Host ''
Write-LeafColor 'OneShot complete.' Green
Write-LeafColor "New location: $target" Cyan
if (-not $noZip) { Write-LeafColor "Zip:          $(Join-Path $target 'leafos-oneshot.zip')" Cyan }
Write-Host ''
Write-Host 'Try:'
Write-Host "  cd `"$target`""
Write-Host '  pwsh -File .\run_demo.ps1'

if ($open) {
    Invoke-Item -LiteralPath $target
}
