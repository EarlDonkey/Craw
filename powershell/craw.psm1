# Craw.psm1 — Craw's face in PowerShell.
#
# Import this in your $PROFILE:
#   Import-Module C:\Users\user\Downloads\Craw\powershell\Craw.psm1
#
# Then Craw lives in your prompt.

$script:CrawPipe = "\\.\pipe\craw"
$script:CrawFallback = "•"

function Get-CrawResponse {
    [CmdletBinding()]
    param()
    try {
        $client = New-Object System.IO.Pipes.NamedPipeClientStream(
            ".", "craw", [System.IO.Pipes.PipeDirection]::InOut
        )
        $client.Connect(200)
        try {
            $writer = New-Object System.IO.StreamWriter($client)
            $reader = New-Object System.IO.StreamReader($client)
            $writer.WriteLine('{"ask":"face"}')
            $writer.Flush()
            $line = $reader.ReadLine()
            return ($line | ConvertFrom-Json)
        } finally {
            $client.Dispose()
        }
    } catch {
        return $null
    }
}

function Get-CrawPrompt {
    [CmdletBinding()]
    param()
    $r = Get-CrawResponse
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

# Override the prompt. This is the magic.
function prompt {
    $glyph = Get-CrawPrompt
    $path = (Get-Location).Path
    # Craw's face, then the path, then the caret
    Write-Host $glyph -NoNewline -ForegroundColor Green
    Write-Host "$path" -NoNewline
    return "> "
}

# A `craw` command so you can talk to it from the shell.
function craw {
    [CmdletBinding()]
    param([Parameter(ValueFromRemainingArguments=$true)]$Args)
    $text = ($Args -join ' ').Trim()
    $obj = if ($text) { @{ ask = "say"; text = $text } } else { @{ ask = "face" } }
    $req = $obj | ConvertTo-Json -Compress

    try {
        $client = New-Object System.IO.Pipes.NamedPipeClientStream(".", "craw", [System.IO.Pipes.PipeDirection]::InOut)
        $client.Connect(300)
        try {
            $writer = New-Object System.IO.StreamWriter($client)
            $reader = New-Object System.IO.StreamReader($client)
            $writer.WriteLine($req)
            $writer.Flush()
            $line = $reader.ReadLine()
            $r = $line | ConvertFrom-Json
        } finally { $client.Dispose() }
    } catch {
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
    $r = Get-CrawResponse -Request @{ ask = "mute_mic" }
    if ($r) { Write-Host "craw can't hear you." -ForegroundColor DarkGray }
    else { Write-Host "craw: not running" -ForegroundColor Red }
}

function craw-unmute-mic {
    $r = Get-CrawResponse -Request @{ ask = "unmute_mic" }
    if ($r) { Write-Host "craw is listening." -ForegroundColor Green }
    else { Write-Host "craw: not running" -ForegroundColor Red }
}

Export-ModuleMember -Function prompt, craw, craw-mute, craw-unmute, Get-CrawResponse, Get-CrawPrompt, craw-mute-mic, craw-unmute-mic