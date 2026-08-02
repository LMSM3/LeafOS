# ------------------------------------------------------------

# LeafOS Loading / Slow UX Layer

# ------------------------------------------------------------



$LeafSlowFactor = 5



function leaf-sleep {

    param([double]$Seconds = 0.2)

    Start-Sleep -Milliseconds ([int]($Seconds * 1000 * $LeafSlowFactor))

}



function leaf-loading {

    param(

        [string]$Message = "loading",

        [int]$Ticks = 12

    )



    $frames = @(

        "./ ",

        ".\ ",

        "...",

        "   "

    )



    for ($i = 0; $i -lt $Ticks; $i++) {

        $frame = $frames[$i % $frames.Count]

        Write-Host "`r$Message $frame" -NoNewline -ForegroundColor Cyan

        leaf-sleep 0.15

    }



    Write-Host "`r$Message ... done     " -ForegroundColor Green

}



function leaf-step {

    param(

        [string]$Message,

        [scriptblock]$Action

    )



    Write-Host ""

    Write-Host "[leaf] attempting to $Message" -ForegroundColor Yellow

    leaf-loading "loading"



    try {

        & $Action

        Write-Host "[ok] $Message" -ForegroundColor Green

    }

    catch {

        Write-Host "[fail] $Message" -ForegroundColor Red

        Write-Host $_.Exception.Message -ForegroundColor DarkRed

    }



    leaf-sleep 0.3

}



function leaf-download {

    param(

        [string]$Url,

        [string]$OutFile = ".\download.ps1"

    )



    leaf-step "download.ps1" {

        Write-Host "source : $Url"

        Write-Host "target : $OutFile"



        leaf-loading "downloading" 20



        Invoke-WebRequest `

            -Uri $Url `

            -OutFile $OutFile `

            -UseBasicParsing



        Write-Host ""

        Write-Host "results" -ForegroundColor Cyan

        Get-Item $OutFile | Format-List Name, FullName, Length, LastWriteTime

    }

}



function leaf-run-download {

    param(

        [string]$Path = ".\download.ps1"

    )



    leaf-step "run $Path" {

        if (!(Test-Path $Path)) {

            throw "Missing file: $Path"

        }



        leaf-loading "verifying script" 10



        Write-Host "running: $Path" -ForegroundColor Cyan

        & $Path



        Write-Host ""

        Write-Host "results: completed" -ForegroundColor Green

    }

}



function leaf-attempt {

    param(

        [string]$Name,

        [scriptblock]$Action

    )



    leaf-step $Name $Action

}
