try { $j = [Console]::In.ReadToEnd() | ConvertFrom-Json } catch { exit 0 }
$c = "$($j.tool_input.command)"
if (-not $c) { exit 0 }
$bypass = ($c -match '--no-gpg-sign') -or ($c -match 'commit\.gpgsign' -and $c -match 'false') -or ($c -match '\bgit\b' -and $c -match '--no-verify')
if ($bypass) {
    [Console]::Error.WriteLine('BLOCKED by git rule: signing/hook bypass (--no-gpg-sign, commit.gpgsign=false, --no-verify) is forbidden. If Eduardo gave a one-time go-ahead, Eduardo runs that command manually in a terminal.')
    exit 2
}
exit 0
