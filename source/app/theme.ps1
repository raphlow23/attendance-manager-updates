# Palette based on the dashboard reference supplied by the user.
function Write-UiPreview($Window, [string]$Path) {
    if (-not $Path) { return }
    $Window.CreateControl()
    foreach ($control in $Window.Controls) { $control.CreateControl() }
    $bitmap = New-Object Drawing.Bitmap($Window.Width, $Window.Height)
    $graphics = [Drawing.Graphics]::FromImage($bitmap)
    function Draw-PreviewChildren($Parent, $Graphics, [int]$X, [int]$Y) {
        # Hidden forms omit descendants in DrawToBitmap. Composite each child
        # directly, without showing a window or taking over the user's screen.
        for ($index = $Parent.Controls.Count - 1; $index -ge 0; $index--) {
            $child = $Parent.Controls[$index]
            if ($child.Width -le 0 -or $child.Height -le 0) { continue }
            $left = $X + $child.Left; $top = $Y + $child.Top
            $rect = New-Object Drawing.RectangleF($left, $top, $child.Width, $child.Height)
            $backColor = $child.BackColor
            if ($child -is [Windows.Forms.DataGridView]) { $backColor = $child.BackgroundColor }
            $background = New-Object Drawing.SolidBrush($backColor)
            $ink = New-Object Drawing.SolidBrush($child.ForeColor)
            try {
                $Graphics.FillRectangle($background, $rect)
                if ($child -is [Windows.Forms.DataGridView]) {
                    $headerBrush = New-Object Drawing.SolidBrush($child.ColumnHeadersDefaultCellStyle.BackColor)
                    $whiteBrush = New-Object Drawing.SolidBrush([Drawing.Color]::White)
                    $cellInk = New-Object Drawing.SolidBrush($child.DefaultCellStyle.ForeColor)
                    $weights = ($child.Columns | Measure-Object -Property FillWeight -Sum).Sum
                    $cx = [single]$left
                    try {
                        foreach ($column in $child.Columns) {
                            $cw = [single]($child.Width * $column.FillWeight / $weights)
                            $Graphics.FillRectangle($headerBrush, $cx, $top, $cw, 40)
                            $Graphics.DrawString($column.HeaderText, $child.Font, $whiteBrush, (New-Object Drawing.RectangleF(($cx + 8), ($top + 10), ($cw - 12), 30)))
                            $cy = $top + 40
                            foreach ($row in $child.Rows) {
                                $value = $row.Cells[$column.Index].Value
                                $text = [string]$value
                                if ($column -is [Windows.Forms.DataGridViewCheckBoxColumn]) { if ($value) { $text = '☑' } else { $text = '☐' } }
                                $Graphics.DrawString($text, $child.Font, $cellInk, (New-Object Drawing.RectangleF(($cx + 8), ($cy + 6), ($cw - 12), 30)))
                                $cy += 32
                            }
                            $cx += $cw
                        }
                    } finally { $headerBrush.Dispose(); $whiteBrush.Dispose(); $cellInk.Dispose() }
                } elseif ($child -isnot [Windows.Forms.Panel]) {
                    $text = $child.Text
                    if ($child -is [Windows.Forms.DateTimePicker]) { $text = $child.Value.ToString('yyyy년 MM월') }
                    $format = New-Object Drawing.StringFormat
                    try {
                        $format.LineAlignment = [Drawing.StringAlignment]::Center
                        if ($child -is [Windows.Forms.Button]) { $format.Alignment = [Drawing.StringAlignment]::Center }
                        $textRect = New-Object Drawing.RectangleF(($left + $child.Padding.Left + 4), $top, ($child.Width - $child.Padding.Left - 8), $child.Height)
                        $Graphics.DrawString($text, $child.Font, $ink, $textRect, $format)
                    } finally { $format.Dispose() }
                }
                if ($child -is [Windows.Forms.Panel]) { Draw-PreviewChildren $child $Graphics $left $top }
            } finally { $background.Dispose(); $ink.Dispose() }
        }
    }
    try {
        $Window.DrawToBitmap($bitmap, (New-Object Drawing.Rectangle(0, 0, $Window.Width, $Window.Height)))
        $border = [int](($Window.Width - $Window.ClientSize.Width) / 2)
        Draw-PreviewChildren $Window $graphics $border ($Window.Height - $Window.ClientSize.Height - $border)
        $bitmap.Save($Path, [Drawing.Imaging.ImageFormat]::Png)
    } finally { $graphics.Dispose(); $bitmap.Dispose() }
}
function Set-UiTheme($Window) {
    $iconPath = Join-Path $PSScriptRoot 'attendance.ico'
    if (Test-Path -LiteralPath $iconPath) { $Window.Icon = New-Object Drawing.Icon($iconPath) }
    elseif (Test-Path -LiteralPath (Join-Path $PSScriptRoot '근태매니저.exe')) { $Window.Icon = [Drawing.Icon]::ExtractAssociatedIcon((Join-Path $PSScriptRoot '근태매니저.exe')) }
    $script:UiBackground = [Drawing.ColorTranslator]::FromHtml('#ECEEF3')
    $script:UiInk = [Drawing.ColorTranslator]::FromHtml('#343C46')
    $script:UiCyan = [Drawing.ColorTranslator]::FromHtml('#4BAFC9')
    $script:UiMint = [Drawing.ColorTranslator]::FromHtml('#55B6A6')
    $script:UiOrange = [Drawing.ColorTranslator]::FromHtml('#E98244')
    $Window.BackColor = $script:UiBackground
    $Window.ForeColor = $script:UiInk
    foreach ($control in $Window.Controls) {
        if ($control -is [Windows.Forms.Button]) {
            $control.FlatStyle = 'Flat'
            $control.FlatAppearance.BorderSize = 0
            $control.BackColor = $script:UiCyan
            $control.ForeColor = [Drawing.Color]::White
            $control.Font = New-Object Drawing.Font('Malgun Gothic', 10, [Drawing.FontStyle]::Bold)
            $control.Cursor = [Windows.Forms.Cursors]::Hand
        } elseif ($control -is [Windows.Forms.DataGridView]) {
            $control.BackgroundColor = [Drawing.Color]::White
            $control.BorderStyle = 'None'
            $control.EnableHeadersVisualStyles = $false
            $control.ColumnHeadersDefaultCellStyle.BackColor = $script:UiInk
            $control.ColumnHeadersDefaultCellStyle.ForeColor = [Drawing.Color]::White
            $control.ColumnHeadersHeight = 40
            $control.DefaultCellStyle.BackColor = [Drawing.Color]::White
            $control.DefaultCellStyle.ForeColor = $script:UiInk
            $control.DefaultCellStyle.SelectionBackColor = [Drawing.ColorTranslator]::FromHtml('#D7F0F0')
            $control.DefaultCellStyle.SelectionForeColor = $script:UiInk
            $control.AlternatingRowsDefaultCellStyle.BackColor = [Drawing.ColorTranslator]::FromHtml('#F6F9FB')
            $control.GridColor = $script:UiBackground
        } elseif ($control -is [Windows.Forms.TextBox] -or $control -is [Windows.Forms.ComboBox] -or $control -is [Windows.Forms.NumericUpDown]) {
            $control.BackColor = [Drawing.Color]::White
            $control.ForeColor = $script:UiInk
        }
    }
}
