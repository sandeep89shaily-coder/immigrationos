# Run the native .NET XFA experiment with an official blank downloaded
# yourself from IRCC in a normal Windows browser. No client data.
# Example:
#   .\scripts\run_imm5476_native_trial.ps1 -OfficialBlank C:\IRCC\imm5476e.pdf
param(
    [Parameter(Mandatory = $true)]
    [string]$OfficialBlank,
    [string]$OutputDirectory = ""
)

$ErrorActionPreference = "Stop"
$expected = "aca5c476b93d1c496b1afbc2cfe843499e852e31dcf0c192153bd01f8d6c56c4"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$project = Join-Path $projectRoot "experiments\AsposeXfaTrial\AsposeXfaTrial.csproj"
$checker = Join-Path $projectRoot "scripts\verify_xfa_trial_readback.py"
if (-not (Test-Path -LiteralPath $OfficialBlank -PathType Leaf)) {
    throw "IRCC_OFFICIAL_BLANK_MISSING: Download IMM 5476 (11-2025) from the official canada.ca instruction page."
}
$source = (Resolve-Path -LiteralPath $OfficialBlank).Path
$sha = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
if ($sha -ne $expected) {
    throw "OFFICIAL_FIXTURE_SHA256_MISMATCH: the supplied blank is not the pinned IMM 5476 11-2025 PDF."
}
if ((Get-Item -LiteralPath $source).Length -gt 12582912) {
    throw "OFFICIAL_FIXTURE_TOO_LARGE"
}
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $env:TEMP ("imm5476-xfa-trial-" + [Guid]::NewGuid().ToString("N"))
}
New-Item -Path $OutputDirectory -ItemType Directory -Force | Out-Null
$folder = (Resolve-Path -LiteralPath $OutputDirectory).Path
if ($source.StartsWith($folder + [IO.Path]::DirectorySeparatorChar,
         [StringComparison]::OrdinalIgnoreCase)) {
    throw "Original official PDF must not be inside the generated output folder"
}
$filled = Join-Path $folder "IMM5476-ASPOSE-NATIVE-FICTIONAL-UNVALIDATED.pdf"
$report = Join-Path $folder "aspose-native-report.json"
$readback = Join-Path $folder "independent-readback.json"
if (Test-Path -LiteralPath $filled) {
    throw "Refusing to overwrite existing trial output"
}
Write-Host "Exact official IMM5476 source checksum confirmed."
Write-Host "Building Aspose .NET trial; original PDF will not be overwritten."
dotnet restore $project
if ($LASTEXITCODE -ne 0) { throw "ASPOSE_RESTORE_FAILED" }
dotnet build $project --no-restore -c Release
if ($LASTEXITCODE -ne 0) { throw "ASPOSE_BUILD_FAILED" }
dotnet run --no-build --project $project --configuration Release -- $source $filled $report
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Native engine did not produce an independently validated output. See $report"
    exit 2
}
if (-not (Test-Path -LiteralPath $filled -PathType Leaf)) {
    throw "ASPOSE_OUTPUT_MISSING"
}
python $checker --original $source --output $filled --report $readback --expected-input-sha256 $expected --official-imm5476
if ($LASTEXITCODE -ne 0) {
    Write-Warning "XFA or AcroForm readback failed; see $readback"
    exit 2
}
Write-Host "Four-field technical readback PASSED; Adobe Reader, licences and IRCC submission remain UNVERIFIED."
Write-Host "Technical results: $readback"
