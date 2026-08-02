# ------------------------------------------------------------

# LeafOS Download Layer: animation + error handling

# ------------------------------------------------------------



function leaf-loading {

    param(

        [string]$Message = "loading",

        [int]$Ticks = 8,

        [int]$DelayMs = 90

    )



    $frames = @("./ ", ".\ ", "...", "   ")



    for ($i = 0; $i -lt $Ticks; $i++) {

        $frame = $frames[$i % $frames.Count]

        Write-Host "`r$Message $frame" -NoNewline -ForegroundColor Cyan

        Start-Sleep -Milliseconds $DelayMs

    }



    Write-Host "`r$Message ... done     " -ForegroundColor Green

}



function leaf-download {

    param(

        [Parameter(Mandatory)]

        [string]$Url,



        [string]$OutFile = ".\download.ps1"

    )



    Write-Host ""

    Write-Host "[leaf] attempting to download.ps1" -ForegroundColor Yellow

    Write-Host "source: $Url"

    Write-Host "target: $OutFile"



    try {

        leaf-loading "downloading"



        Invoke-WebRequest `

            -Uri $Url `

            -OutFile $OutFile `

            -UseBasicParsing `

            -ErrorAction Stop



        Write-Host ""

        Write-Host "[ok] download complete" -ForegroundColor Green

        Write-Host ""

        Write-Host "results" -ForegroundColor Cyan

        Get-Item $OutFile | Format-List Name, FullName, Length, LastWriteTime

    }

    catch {

        Write-Host ""

        Write-Host "[fail] download failed" -ForegroundColor Red

        Write-Host $_.Exception.Message -ForegroundColor DarkRed



        if ($_.Exception.Response) {

            Write-Host ""

            Write-Host "server response:" -ForegroundColor Yellow

            Write-Host $_.Exception.Response.StatusCode

        }

    }

}



function leaf-run-download {

    param(

        [string]$Path = ".\download.ps1"

    )



    Write-Host ""

    Write-Host "[leaf] attempting to run $Path" -ForegroundColor Yellow



    try {

        if (!(Test-Path $Path)) {

            throw "Missing file: $Path"

        }



        leaf-loading "verifying"



        Write-Host ""

        Write-Host "running: $Path" -ForegroundColor Cyan



        & $Path



        Write-Host ""

        Write-Host "[ok] run complete" -ForegroundColor Green

    }

    catch {

        Write-Host ""

        Write-Host "[fail] run failed" -ForegroundColor Red

        Write-Host $_.Exception.Message -ForegroundColor DarkRed

    }

}



function leaf-attempt {

    param(

        [Parameter(Mandatory)]

        [string]$Name,



        [Parameter(Mandatory)]

        [scriptblock]$Action

    )



    Write-Host ""

    Write-Host "[leaf] attempting to $Name" -ForegroundColor Yellow



    try {

        leaf-loading "loading"



        & $Action



        Write-Host ""

        Write-Host "[ok] $Name" -ForegroundColor Green

    }

    catch {

        Write-Host ""

        Write-Host "[fail] $Name" -ForegroundColor Red

        Write-Host $_.Exception.Message -ForegroundColor DarkRed

    }

}
