param(
    [Parameter(Mandatory = $true)]
    [string]$JobsPath,
    [Parameter(Mandatory = $true)]
    [string]$OutputDirectory
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech

$jobs = Get-Content -LiteralPath $JobsPath -Raw | ConvertFrom-Json
$jobProperties = @($jobs.PSObject.Properties)
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null

$synthesizer = New-Object System.Speech.Synthesis.SpeechSynthesizer
$availableVoices = @($synthesizer.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name })
$preferredVoices = @('Microsoft Zira Desktop', 'Microsoft Zira', 'Microsoft David Desktop', 'Microsoft David')
$voice = $preferredVoices | Where-Object { $availableVoices -contains $_ } | Select-Object -First 1
if (-not $voice) {
    $voice = $availableVoices | Select-Object -First 1
}
if (-not $voice) {
    throw 'No local English speech voice is installed.'
}

$synthesizer.SelectVoice($voice)
$synthesizer.Rate = -1
$synthesizer.Volume = 100
$format = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(
    24000,
    [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,
    [System.Speech.AudioFormat.AudioChannel]::Mono
)

try {
    foreach ($property in $jobProperties) {
        $textId = $property.Name
        $destination = Join-Path $OutputDirectory ($textId + '.wav')
        $synthesizer.SetOutputToWaveFile($destination, $format)
        $synthesizer.Speak([string]$property.Value.text)
        $synthesizer.SetOutputToNull()
    }
}
finally {
    $synthesizer.Dispose()
}

Write-Output ("Generated {0} WAV segments with {1}." -f $jobProperties.Count, $voice)
