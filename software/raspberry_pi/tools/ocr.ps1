param(
    [Parameter(Mandatory=$true)][string]$ImagePath,
    [switch]$Boxes
)
# 用 Windows 自带 OCR 引擎识别图片中的文字（支持中文，离线，零依赖）
# 用法: powershell -ExecutionPolicy Bypass -File ocr.ps1 -ImagePath x.png [-Boxes]

Add-Type -AssemblyName System.Runtime.WindowsRuntime

$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType=WindowsRuntime]

$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() |
    Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]

Function Await($WinRtTask, $ResultType) {
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}

$path = (Resolve-Path $ImagePath).Path
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($path)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])

# 优先用中文识别引擎，否则用用户语言
$zhLang = [Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages |
    Where-Object { $_.LanguageTag -like 'zh*' } | Select-Object -First 1
if ($zhLang) {
    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($zhLang)
} else {
    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
}
if (-not $engine) { Write-Error "无法创建 OCR 引擎"; exit 1 }

$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])

foreach ($line in $result.Lines) {
    if ($Boxes) {
        $ws = @($line.Words | ForEach-Object { $_.BoundingRect })
        $minX = ($ws | Measure-Object X -Minimum).Minimum
        $minY = ($ws | Measure-Object Y -Minimum).Minimum
        $maxX = ($ws | Measure-Object X -Maximum).Maximum
        $maxY = ($ws | Measure-Object Y -Maximum).Maximum
        Write-Output ("[{0},{1} {2},{3}] {4}" -f [int]$minX, [int]$minY, [int]$maxX, [int]$maxY, $line.Text)
    } else {
        Write-Output $line.Text
    }
}
