try { $j = [Console]::In.ReadToEnd() | ConvertFrom-Json } catch { exit 0 }
$c = "$($j.tool_input.command)"
if (-not $c -or $c -notmatch '\bgit\b' -or $c -notmatch '\bcommit\b') { exit 0 }
$repo = $null
if ($c -match 'git\s+-C\s+"([^"]+)"') { $repo = $Matches[1] } elseif ($c -match 'git\s+-C\s+(\S+)') { $repo = $Matches[1] }
if (-not $repo) { $repo = "$($j.cwd)" }
if (-not $repo -or -not (Test-Path -LiteralPath $repo)) { exit 0 }
function Get-AddedLines([string[]]$diffArgs) {
    $lines = New-Object System.Collections.Generic.List[object]
    $f = ''
    foreach ($line in (& git -C $repo diff --cached -U0 --diff-filter=AM @diffArgs 2>$null)) {
        if ($line -match '^\+\+\+ b/(.*)$') { $f = $Matches[1]; continue }
        if ($line -match '^\+' -and $line -notmatch '^\+\+\+') { $lines.Add([pscustomobject]@{ File = $f; Text = $line.Substring(1) }) }
    }
    return ,$lines
}
$addedLines = Get-AddedLines @()
$mergeHead = & git -C $repo rev-parse -q --verify MERGE_HEAD 2>$null
if ($LASTEXITCODE -eq 0 -and $mergeHead) {
    $notInMergeHead = New-Object 'System.Collections.Generic.HashSet[string]'
    foreach ($a in (Get-AddedLines @('MERGE_HEAD'))) { [void]$notInMergeHead.Add("$($a.File)`n$($a.Text)") }
    $addedLines = @($addedLines | Where-Object { $notInMergeHead.Contains("$($_.File)`n$($_.Text)") })
}
$generated = '(Results.Expected|(^|.)obj.|\.g\.cs$|\.Generated\.cs$)'
$problems = New-Object System.Collections.Generic.List[string]
foreach ($a in $addedLines) {
    $isCs = ($a.File -match '\.cs$') -and ($a.File -notmatch $generated)
    if ($isCs -and $a.Text -match '^\s*//' -and $a.Text -notmatch '^\s*///' -and $a.Text -notmatch '^\s*//\s*TODO\(RDMST-\d+\):' -and $a.Text -notmatch 'https?://') {
        $problems.Add("comment in C# outside the three allowed kinds: $($a.File)`: $($a.Text.Trim())")
    }
}
$dl = Join-Path $env:USERPROFILE '.claude\customer-names.txt'
if (Test-Path -LiteralPath $dl) {
    $names = @(Get-Content -LiteralPath $dl | Where-Object { $_.Trim() })
    $messages = New-Object System.Collections.Generic.List[string]
    foreach ($m in [regex]::Matches($c, '(?:-m|--message)\s+(?:"([^"]*)"|''([^'']*)''|(\S+))')) { $messages.Add("$($m.Groups[1].Value)$($m.Groups[2].Value)$($m.Groups[3].Value)") }
    $staged = @(& git -C $repo diff --cached --name-only 2>$null)
    foreach ($n in $names) {
        $esc = [regex]::Escape($n.Trim())
        foreach ($msg in $messages) { if ($msg -match "(?i)$esc") { $problems.Add("customer name '$n' in the commit message") } }
        foreach ($s in $staged) { if ($s -match "(?i)$esc") { $problems.Add("customer name '$n' in the staged path $s") } }
        $hit = $addedLines | Where-Object { $_.Text -match "(?i)$esc" } | Select-Object -First 1
        if ($hit) { $problems.Add("customer name '$n' in $($hit.File)") }
    }
}
if ($problems.Count -gt 0) {
    [Console]::Error.WriteLine('BLOCKED by the commit self-check (CLAUDE.md comments rule, rules/customer-data.md):')
    $problems | Select-Object -Unique | Select-Object -First 12 | ForEach-Object { [Console]::Error.WriteLine("  $_") }
    [Console]::Error.WriteLine('Rename instead of commenting (the allowed kinds: XML docs on public members, // TODO(RDMST-xxxx):, a workaround citing a full URL); say "the customer app" instead of its name; then commit again.')
    exit 2
}
exit 0
