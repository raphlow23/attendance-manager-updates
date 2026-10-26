$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$root = Split-Path -Parent $PSScriptRoot
$images = @()
foreach ($size in @(16,24,32,48,64,128,256)) {
    $bitmap = New-Object Drawing.Bitmap($size,$size)
    $g = [Drawing.Graphics]::FromImage($bitmap)
    $g.SmoothingMode = 'AntiAlias'
    $g.ScaleTransform(($size/256.0),($size/256.0))
    $bg = New-Object Drawing.SolidBrush([Drawing.ColorTranslator]::FromHtml('#343C46'))
    $cyan = New-Object Drawing.SolidBrush([Drawing.ColorTranslator]::FromHtml('#4BAFC9'))
    $white = New-Object Drawing.SolidBrush([Drawing.Color]::White)
    $hand = New-Object Drawing.Pen([Drawing.ColorTranslator]::FromHtml('#343C46'),14)
    $check = New-Object Drawing.Pen([Drawing.ColorTranslator]::FromHtml('#E98244'),20)
    $hand.StartCap='Round'; $hand.EndCap='Round'; $check.StartCap='Round'; $check.EndCap='Round'; $check.LineJoin='Round'
    try {
        $g.FillEllipse($bg,4,4,248,248)
        $g.FillEllipse($cyan,16,16,224,224)
        $g.FillEllipse($white,43,39,170,170)
        $g.DrawLine($hand,128,70,128,126)
        $g.DrawLine($hand,128,126,163,145)
        $g.FillEllipse($bg,140,151,100,86)
        $g.DrawLines($check,[Drawing.PointF[]]@((New-Object Drawing.PointF(158,194)),(New-Object Drawing.PointF(179,214)),(New-Object Drawing.PointF(220,171))))
        $stream=New-Object IO.MemoryStream
        $bitmap.Save($stream,[Drawing.Imaging.ImageFormat]::Png)
        $images += ,@($size,$stream.ToArray())
        if($size -eq 256){$bitmap.Save((Join-Path $root 'previews\attendance-icon.png'),[Drawing.Imaging.ImageFormat]::Png)}
        $stream.Dispose()
    } finally { $g.Dispose(); $bitmap.Dispose(); $bg.Dispose(); $cyan.Dispose(); $white.Dispose(); $hand.Dispose(); $check.Dispose() }
}
$file=[IO.File]::Create((Join-Path $root 'app\attendance.ico'))
$writer=New-Object IO.BinaryWriter($file)
try {
    $writer.Write([UInt16]0); $writer.Write([UInt16]1); $writer.Write([UInt16]$images.Count)
    $offset=6+16*$images.Count
    foreach($entry in $images){
        $dimension=if($entry[0] -eq 256){0}else{$entry[0]}
        $writer.Write([byte]$dimension); $writer.Write([byte]$dimension); $writer.Write([byte]0); $writer.Write([byte]0)
        $writer.Write([UInt16]1); $writer.Write([UInt16]32); $writer.Write([UInt32]$entry[1].Length); $writer.Write([UInt32]$offset)
        $offset += $entry[1].Length
    }
    foreach($entry in $images){$writer.Write([byte[]]$entry[1])}
} finally {$writer.Dispose(); $file.Dispose()}
Write-Output 'ICON_OK: seven sizes, 16 through 256 pixels'
