Param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir '..') | Select-Object -ExpandProperty Path

$DataDir = Join-Path $ProjectRoot 'data\processed'
$NvdPath = Join-Path $DataDir 'nvd.json'
$KevPath = Join-Path $DataDir 'kev.json'
$EpssPath = Join-Path $DataDir 'epss.json'
$OutputPath = Join-Path $ScriptDir 'contrast_cves.json'

function Write-Section {
    param([string]$Title)
    Write-Host ''
    Write-Host $Title
    Write-Host ('-' * $Title.Length)
}

function Convert-ToDouble {
    param([object]$Value)

    if ($null -eq $Value) {
        return $null
    }

    $number = 0.0
    if ([double]::TryParse([string]$Value, [ref]$number)) {
        return $number
    }

    return $null
}

function Get-CveId {
    param([object]$Record)

    if ($null -eq $Record) {
        return $null
    }

    foreach ($Key in @('cve_id', 'cveID', 'id')) {
        $Value = $Record.$Key
        if ($Value -and ([string]$Value).Trim()) {
            return ([string]$Value).Trim().ToUpperInvariant()
        }
    }

    if ($Record.cve -and $Record.cve.id) {
        return ([string]$Record.cve.id).Trim().ToUpperInvariant()
    }

    return $null
}

Write-Host 'Loading processed data files...'
if (-not (Test-Path $NvdPath)) { Throw "Missing $NvdPath" }
if (-not (Test-Path $KevPath)) { Throw "Missing $KevPath" }
if (-not (Test-Path $EpssPath)) { Throw "Missing $EpssPath" }

$nvd = Get-Content -Raw -Path $NvdPath | ConvertFrom-Json
$kev = Get-Content -Raw -Path $KevPath | ConvertFrom-Json
$epss = Get-Content -Raw -Path $EpssPath | ConvertFrom-Json

$kevSet = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
foreach ($item in $kev) {
    $cveId = Get-CveId -Record $item
    if ($cveId) { [void]$kevSet.Add($cveId) }
}

$epssMap = @{ }
foreach ($item in $epss) {
    $cveId = Get-CveId -Record $item
    $epssValue = Convert-ToDouble -Value $item.epss_probability
    if ($cveId -and $null -ne $epssValue) { $epssMap[$cveId] = $epssValue }
}

$records = foreach ($item in $nvd) {
    $cveId = Get-CveId -Record $item
    if (-not $cveId) { continue }
    $cvss = Convert-ToDouble -Value $item.cvss_score
    if ($null -eq $cvss) { continue }
    if (-not $epssMap.ContainsKey($cveId)) { continue }
    [pscustomobject]@{
        cve_id = $cveId
        cvss_score = [double]$cvss
        epss_probability = [double]$epssMap[$cveId]
        kev_flag = [bool]$kevSet.Contains($cveId)
    }
}

Write-Host "Cross-referenced CVEs present in NVD and EPSS: $($records.Count)"

$categoryA = $records |
    Where-Object { $_.cvss_score -ge 9.0 -and -not $_.kev_flag -and $_.epss_probability -lt 0.05 } |
    Sort-Object @{Expression='cvss_score';Descending=$true}, @{Expression='epss_probability';Descending=$false}, cve_id |
    Select-Object -First 4

$categoryB = $records |
    Where-Object { $_.cvss_score -ge 6.0 -and $_.cvss_score -le 8.5 -and $_.kev_flag -and $_.epss_probability -gt 0.70 } |
    Sort-Object @{Expression='epss_probability';Descending=$true}, @{Expression='cvss_score';Descending=$true}, cve_id |
    Select-Object -First 4

$categoryC = $records |
    Where-Object { $_.cvss_score -ge 8.0 -and -not $_.kev_flag -and $_.epss_probability -ge 0.10 -and $_.epss_probability -le 0.50 } |
    Sort-Object @{Expression='cvss_score';Descending=$true}, @{Expression='epss_probability';Descending=$true}, cve_id |
    Select-Object -First 2

Write-Section 'Category A - High CVSS, Not in KEV, Low EPSS'
foreach ($item in $categoryA) { Write-Host ('{0} | {1:N1} | {2:P2} | {3}' -f $item.cve_id, $item.cvss_score, $item.epss_probability, ([int]$item.kev_flag)) }

Write-Section 'Category B - Moderate CVSS, In KEV, High EPSS'
foreach ($item in $categoryB) { Write-Host ('{0} | {1:N1} | {2:P2} | {3}' -f $item.cve_id, $item.cvss_score, $item.epss_probability, ([int]$item.kev_flag)) }

Write-Section 'Category C - High CVSS, Not in KEV, Moderate EPSS'
foreach ($item in $categoryC) { Write-Host ('{0} | {1:N1} | {2:P2} | {3}' -f $item.cve_id, $item.cvss_score, $item.epss_probability, ([int]$item.kev_flag)) }

$payload = [ordered]@{
    category_a = @($categoryA)
    category_b = @($categoryB)
    category_c = @($categoryC)
}

$payload | ConvertTo-Json -Depth 6 | Set-Content -Path $OutputPath -Encoding UTF8

Write-Host ''
Write-Host "Saved contrast CVEs to $OutputPath"
Write-Host "Counts: A=$($categoryA.Count) B=$($categoryB.Count) C=$($categoryC.Count)"

if ($categoryA.Count -lt 4 -or $categoryB.Count -lt 4 -or $categoryC.Count -lt 2) {
    Write-Warning 'One or more categories returned fewer CVEs than requested.'
}
