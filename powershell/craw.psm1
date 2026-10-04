# Craw.psm1 — Craw's face in PowerShell.

$script:CrawPipe = "\\.\pipe\craw"
$script:CrawFallback = "•"

function Start-CrawDaemon {
    $root = "C:\Users\user\Downloads\Craw"
    Start-Process -FilePath "py" `
        -ArgumentList "-m","craw" `
        -WorkingDirectory $root `
        -WindowStyle Hidden
    Start-Sleep -Milliseconds 2000
}

function Get-CrawResponse {
    [CmdletBinding()]
    param([hashtable]$Request)

    if (-not $Request) { $Request = @{ ask = "face" } }
    $json = $Request | ConvertTo-Json -Compress

    foreach ($attempt in 1..2) {
        try {
            $client = New-Object System.IO.Pipes.NamedPipeClientStream(
                ".", "craw", [System.IO.Pipes.PipeDirection]::InOut
            )
            $client.Connect(500)
            try {
                $writer = New-Object System.IO.StreamWriter($client)
                $reader = New-Object System.IO.StreamReader($client)
                $writer.WriteLine($json)
                $writer.Flush()
                $line = $reader.ReadLine()
                if (-not $line) { throw "empty response" }
                return ($line | ConvertFrom-Json)
            } finally {
                $client.Dispose()
            }
        } catch {
            if ($attempt -eq 1) {
                Start-CrawDaemon
            } else {
                return $null
            }
        }
    }
    return $null
}

function Get-CrawPrompt {
    [CmdletBinding()]
    param()
    $r = Get-CrawResponse -Request @{ ask = "face" }
    if (-not $r) {
        return "$script:CrawFallback "
    }
    $glyph = $r.face.glyph
    $color = $r.face.color
    $map = @{
        "green"   = "Green"
        "yellow"  = "Yellow"
        "red"     = "Red"
        "cyan"    = "Cyan"
        "magenta" = "Magenta"
        "dim"     = "DarkGray"
    }
    $psColor = if ($map.ContainsKey($color)) { $map[$color] } else { "White" }

    if ($r.message -and $r.message.text) {
        Write-Host ""
        Write-Host "  $($r.message.text)" -ForegroundColor $psColor
    }

    return "$glyph "
}

function prompt {
    $glyph = Get-CrawPrompt
    $path = (Get-Location).Path
    Write-Host $glyph -NoNewline -ForegroundColor Green
    Write-Host "$path" -NoNewline
    return "> "
}

function craw {
    [CmdletBinding()]
    param([Parameter(ValueFromRemainingArguments=$true)]$Args)
    $text = ($Args -join ' ').Trim()
    $req = if ($text) { @{ ask = "say"; text = $text } } else { @{ ask = "face" } }
    $r = Get-CrawResponse -Request $req

    if (-not $r) {
        Write-Host "craw: not running" -ForegroundColor Red
        return
    }

    if ($text) {
        Write-Host $r.message.text -ForegroundColor Cyan
    } else {
        Write-Host "craw is $($r.face.mood), $($r.face.age_min)m old." -ForegroundColor $r.face.color
        if ($r.message.text) { Write-Host "  $($r.message.text)" }
    }
}

function craw-mute {
    [CmdletBinding()]
    param()
    $r = Get-CrawResponse -Request @{ ask = "mute" }
    if ($r) { Write-Host "craw is quiet." -ForegroundColor DarkGray }
    else { Write-Host "craw: not running" -ForegroundColor Red }
}

function craw-unmute {
    [CmdletBinding()]
    param()
    $r = Get-CrawResponse -Request @{ ask = "unmute" }
    if ($r) { Write-Host "craw can speak." -ForegroundColor Green }
    else { Write-Host "craw: not running" -ForegroundColor Red }
}

function craw-mute-mic {
    [CmdletBinding()]
    param()
    $r = Get-CrawResponse -Request @{ ask = "mute_mic" }
    if ($r) { Write-Host "craw can't hear you." -ForegroundColor DarkGray }
    else { Write-Host "craw: not running" -ForegroundColor Red }
}

function craw-unmute-mic {
    [CmdletBinding()]
    param()
    $r = Get-CrawResponse -Request @{ ask = "unmute_mic" }
    if ($r) { Write-Host "craw is listening." -ForegroundColor Green }
    else { Write-Host "craw: not running" -ForegroundColor Red }
}

function craw-name {
    [CmdletBinding()]
    param([Parameter(ValueFromRemainingArguments=$true)]$Name)
    $text = ($Name -join ' ').Trim()
    if (-not $text) {
        Write-Host "usage: craw-name <your name>" -ForegroundColor Yellow
        return
    }
    $r = Get-CrawResponse -Request @{ ask = "name"; text = $text }
    if ($r) { Write-Host $r.message.text -ForegroundColor Cyan }
    else { Write-Host "craw: not running" -ForegroundColor Red }
}

function craw-log {
    [CmdletBinding()]
    param([int]$Lines = 20)
    $r = Get-CrawResponse -Request @{ ask = "shell_log"; n = $Lines }
    if ($r) {
        Write-Host $r.message.text -ForegroundColor DarkGray
    } else {
        Write-Host "craw: not running" -ForegroundColor Red
    }
}

function craw-ping {
    [CmdletBinding()]
    param()
    $r = Get-CrawResponse -Request @{ ask = "ping" }
    if ($r) { Write-Host $r.message.text -ForegroundColor Green }
    else { Write-Host "craw: not running" -ForegroundColor Red }
}

function craw-workspace {
    [CmdletBinding()]
    param()
    $r = Get-CrawResponse -Request @{ ask = "workspace" }
    if ($r) { Write-Host $r.message.text -ForegroundColor DarkGray }
    else { Write-Host "craw: not running" -ForegroundColor Red }
}

function craw-readings {
    [CmdletBinding()]
    param([int]$Lines = 10)
    $r = Get-CrawResponse -Request @{ ask = "readings"; n = $Lines }
    if ($r) { Write-Host $r.message.text -ForegroundColor DarkGray }
    else { Write-Host "craw: not running" -ForegroundColor Red }
}

Export-ModuleMember -Function prompt, craw, craw-mute, craw-unmute, craw-mute-mic, craw-unmute-mic, craw-name, craw-log, craw-ping, craw-workspace, craw-readings, Get-CrawResponse, Get-CrawPrompt