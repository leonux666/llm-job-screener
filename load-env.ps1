# Loads .env into the current PowerShell session.
#   . .\load-env.ps1
# The leading dot matters: it runs the script in your shell rather than a child
# process, which is the only way the variables survive past the script.
Get-Content .env | ForEach-Object {
  if ($_ -match '^\s*([^#=]+)=(.*)$') {
    [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim())
  }
}
if ($env:ANTHROPIC_API_KEY) {
  Write-Host "loaded ANTHROPIC_API_KEY ($($env:ANTHROPIC_API_KEY.Substring(0,12))...)"
} else {
  Write-Host "ANTHROPIC_API_KEY not found in .env" -ForegroundColor Red
}
