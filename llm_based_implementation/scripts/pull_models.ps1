# Pull the benchmark models, with fallback to canonical tags when the
# requested tag does not exist in the Ollama registry. Writes the list of
# successfully-resolved tags to artifacts/resolved_models.json.

$ErrorActionPreference = "Continue"
$ollama = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"

# requested tag -> ordered candidate tags to try
$wanted = @(
    @("qwen2.5:14b-instruct", @("qwen2.5:14b-instruct", "qwen2.5:14b")),
    @("phi4",                 @("phi4")),
    @("llama3.1:8b-instruct", @("llama3.1:8b-instruct", "llama3.1:8b")),
    @("llama3.2:3b-instruct", @("llama3.2:3b-instruct", "llama3.2:3b"))
)

$resolved = @()
foreach ($entry in $wanted) {
    $requested = $entry[0]
    $candidates = $entry[1]
    $done = $false
    foreach ($tag in $candidates) {
        Write-Output "=== Pulling $tag (requested: $requested) ==="
        & $ollama pull $tag
        if ($LASTEXITCODE -eq 0) {
            Write-Output "OK: resolved $requested -> $tag"
            $resolved += [ordered]@{ requested = $requested; resolved = $tag }
            $done = $true
            break
        } else {
            Write-Output "FAILED tag $tag (exit $LASTEXITCODE), trying next candidate..."
        }
    }
    if (-not $done) {
        Write-Output "ERROR: could not pull any candidate for $requested"
        $resolved += [ordered]@{ requested = $requested; resolved = $null }
    }
}

$artifacts = Join-Path (Split-Path $PSScriptRoot -Parent) "artifacts"
New-Item -ItemType Directory -Force -Path $artifacts | Out-Null
$out = Join-Path $artifacts "resolved_models.json"
$resolved | ConvertTo-Json -Depth 4 | Out-File -FilePath $out -Encoding utf8
Write-Output "Wrote $out"
Write-Output "=== installed models ==="
& $ollama list
