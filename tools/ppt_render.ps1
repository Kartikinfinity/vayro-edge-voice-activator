<#
  Render a .pptx to PNGs (one per slide) and optionally export a PDF, using the installed PowerPoint (COM).
  Usage: powershell -ExecutionPolicy Bypass -File tools\ppt_render.ps1 -Pptx <deck.pptx> -OutDir <dir> [-Pdf <out.pdf>] [-Width 1600]
#>
param(
    [Parameter(Mandatory = $true)][string]$Pptx,
    [Parameter(Mandatory = $true)][string]$OutDir,
    [string]$Pdf = "",
    [int]$Width = 1600
)
$Pptx = (Resolve-Path $Pptx).Path
New-Item -ItemType Directory -Force $OutDir | Out-Null
$OutDir = (Resolve-Path $OutDir).Path
$app = New-Object -ComObject PowerPoint.Application
try {
    # ReadOnly, Untitled, WithWindow = false
    $pres = $app.Presentations.Open($Pptx, -1, 0, 0)
    $h = [int]($Width * $pres.PageSetup.SlideHeight / $pres.PageSetup.SlideWidth)
    for ($i = 1; $i -le $pres.Slides.Count; $i++) {
        $pres.Slides.Item($i).Export((Join-Path $OutDir ("slide-{0:D2}.png" -f $i)), "PNG", $Width, $h)
    }
    if ($Pdf) { $pres.SaveAs($Pdf, 32) }  # 32 = ppSaveAsPDF
    "slides: $($pres.Slides.Count) -> $OutDir"
    $pres.Close()
} finally {
    $app.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($app) | Out-Null
}
