# Light grey raised surfaces and muted blue from the supplied reference.
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
            if (-not [WorkdaySoftTheme]::OwnVisible($child) -or $child.Width -le 0 -or $child.Height -le 0) { continue }
            $left = $X + $child.Left; $top = $Y + $child.Top
            $rect = New-Object Drawing.RectangleF($left, $top, $child.Width, $child.Height)
            $backColor = $child.BackColor
            if($child -is [Windows.Forms.Button]){$backColor=$Parent.BackColor}
            if ($child -is [Windows.Forms.DataGridView]) { $backColor = $child.BackgroundColor }
            $background = New-Object Drawing.SolidBrush($backColor)
            $ink = New-Object Drawing.SolidBrush($child.ForeColor)
            try {
                $Graphics.FillRectangle($background, $rect)
                if ($child -is [Windows.Forms.DataGridView]) {
                    $headerBrush = New-Object Drawing.SolidBrush($child.ColumnHeadersDefaultCellStyle.BackColor)
                    $whiteBrush = New-Object Drawing.SolidBrush($child.ColumnHeadersDefaultCellStyle.ForeColor)
                    $cellInk = New-Object Drawing.SolidBrush($child.DefaultCellStyle.ForeColor)
                    $columns=@($child.Columns|Where-Object{$_.Visible});$weights = ($columns | Measure-Object -Property FillWeight -Sum).Sum
                    $cx = [single]$left
                    try {
                        foreach ($column in $columns) {
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
                } elseif($child -is [Windows.Forms.Button]) {
                    [WorkdaySoftTheme]::SurfacePaint($Graphics,$rect,14,$Parent.BackColor,$true)
                    [WorkdaySoftTheme]::PreviewButton($Graphics,$rect,$child)
                } elseif ($child -isnot [Windows.Forms.Panel]) {
                    $text = $child.Text
                    if ($child -is [Windows.Forms.DateTimePicker]) { $text = $child.Value.ToString($child.CustomFormat) }
                    if ($child -is [Windows.Forms.CheckBox]) { $text = $(if ($child.Checked) { '☑ ' } else { '☐ ' }) + $text }
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
if (-not ('WorkdaySoftTheme' -as [type])) {
 Add-Type -ReferencedAssemblies System.Windows.Forms,System.Drawing -TypeDefinition @"
using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Reflection;
using System.Windows.Forms;
public static class WorkdaySoftTheme {
 public static readonly Color Surface=Color.FromArgb(231,235,237), Ink=Color.FromArgb(57,76,91);
 static Color Mix(Color a,Color b,float t){return Color.FromArgb((int)(a.R+(b.R-a.R)*t),(int)(a.G+(b.G-a.G)*t),(int)(a.B+(b.B-a.B)*t));}
 static GraphicsPath Round(RectangleF r,float radius){GraphicsPath p=new GraphicsPath();float d=Math.Min(radius*2,Math.Min(r.Width,r.Height));if(d<=0){p.AddRectangle(r);return p;}p.AddArc(r.X,r.Y,d,d,180,90);p.AddArc(r.Right-d,r.Y,d,d,270,90);p.AddArc(r.Right-d,r.Bottom-d,d,d,0,90);p.AddArc(r.X,r.Bottom-d,d,d,90,90);p.CloseFigure();return p;}
 static readonly MethodInfo State=typeof(Control).GetMethod("GetState",BindingFlags.NonPublic|BindingFlags.Instance);
 public static bool OwnVisible(Control c){return State==null?true:(bool)State.Invoke(c,new object[]{2});}
 public static void SurfacePaint(Graphics g,RectangleF r,float radius,Color color,bool raised){
  if(r.Width<2||r.Height<2)return;g.SmoothingMode=SmoothingMode.AntiAlias;
  if(raised)for(int i=5;i>=1;i--){RectangleF light=r;light.Offset(-i*.7f,-i*.7f);RectangleF dark=r;dark.Offset(i*.8f,i*.8f);using(var p=Round(dark,radius))using(var b=new SolidBrush(Color.FromArgb(8,112,126,136)))g.FillPath(b,p);using(var p=Round(light,radius))using(var b=new SolidBrush(Color.FromArgb(22,255,255,255)))g.FillPath(b,p);}
  using(var p=Round(r,radius))using(var b=new LinearGradientBrush(r,Mix(color,Color.White,.18f),Mix(color,Surface,.08f),90f))using(var pen=new Pen(Color.FromArgb(160,255,255,255),1)){g.FillPath(b,p);g.DrawPath(pen,p);}
 }
 public static void ButtonPaint(Graphics g,Rectangle r,Button b,bool pressed,bool hover){
  RectangleF face=new RectangleF(r.X+1,r.Y+1,r.Width-3,r.Height-3);Color fill=b.Enabled?b.BackColor:Surface;
  if(pressed)fill=Mix(fill,Ink,.10f);else if(hover)fill=Mix(fill,Color.White,.10f);
  SurfacePaint(g,face,Math.Min(14,r.Height/3),fill,false);
  Color text=!b.Enabled?Color.FromArgb(126,139,148):(fill.GetBrightness()>.64f?Ink:Color.White);
  Rectangle content=Rectangle.Inflate(r,-5,-2);if(pressed)content.Offset(1,1);
  TextRenderer.DrawText(g,b.Text,b.Font,content,text,TextFormatFlags.HorizontalCenter|TextFormatFlags.VerticalCenter|TextFormatFlags.WordBreak);
  if(b.Focused)using(var p=Round(RectangleF.Inflate(face,-3,-3),10))using(var pen=new Pen(Color.FromArgb(100,80,112,136),1)){pen.DashStyle=DashStyle.Dot;g.DrawPath(pen,p);}
 }
 public static void PreviewButton(Graphics g,RectangleF r,Button b){
  Color fill=b.Enabled?b.BackColor:Surface;
  SurfacePaint(g,new RectangleF(r.X+1,r.Y+1,r.Width-3,r.Height-3),Math.Min(14,r.Height/3),fill,false);
  Color text=!b.Enabled?Color.FromArgb(126,139,148):(fill.GetBrightness()>.64f?Ink:Color.White);
  using(var brush=new SolidBrush(text))using(var format=new StringFormat()){format.Alignment=StringAlignment.Center;format.LineAlignment=StringAlignment.Center;g.DrawString(b.Text,b.Font,brush,RectangleF.Inflate(r,-5,-2),format);}
 }
 public static void ApplyButton(Button b){
  bool down=false,hover=false;b.FlatStyle=FlatStyle.Flat;b.FlatAppearance.BorderSize=0;
  b.Paint+=(s,e)=>ButtonPaint(e.Graphics,b.ClientRectangle,b,down,hover);
  b.MouseEnter+=(s,e)=>{hover=true;b.Invalidate();};b.MouseLeave+=(s,e)=>{hover=false;down=false;b.Invalidate();};b.MouseDown+=(s,e)=>{down=true;b.Invalidate();};b.MouseUp+=(s,e)=>{down=false;b.Invalidate();};
  b.EnabledChanged+=(s,e)=>b.Invalidate();b.GotFocus+=(s,e)=>b.Invalidate();b.LostFocus+=(s,e)=>b.Invalidate();
  EventHandler size=(s,e)=>{var old=b.Region;using(var p=Round(new RectangleF(0,0,b.Width,b.Height),Math.Min(14,b.Height/3)))b.Region=new Region(p);if(old!=null)old.Dispose();};size(b,EventArgs.Empty);b.SizeChanged+=size;
 }
 public static void Container(Control parent){
  if(parent is Panel){EventHandler size=(s,e)=>{var old=parent.Region;using(var p=Round(new RectangleF(0,0,parent.Width,parent.Height),20))parent.Region=new Region(p);if(old!=null)old.Dispose();};size(parent,EventArgs.Empty);parent.SizeChanged+=size;}
  var buffered=typeof(Control).GetProperty("DoubleBuffered",BindingFlags.NonPublic|BindingFlags.Instance);if(buffered!=null)buffered.SetValue(parent,true,null);
  parent.Paint+=(s,e)=>{if(parent is Form && parent.Controls.Count<8)SurfacePaint(e.Graphics,new RectangleF(14,14,parent.ClientSize.Width-28,parent.ClientSize.Height-28),22,Surface,true);foreach(Control c in parent.Controls){if(!OwnVisible(c))continue;if(!(c is Panel||c is GroupBox||c is DataGridView||c is Button))continue;RectangleF r=new RectangleF(c.Left,c.Top,c.Width,c.Height);r.Inflate(c is Button?1:4,c is Button?1:4);SurfacePaint(e.Graphics,r,c is Button?Math.Min(15,c.Height/3):18,Surface,true);}};
 }
}
"@
}
function Set-UiTheme($Window) {
 if (-not (Get-Command Initialize-WorkdayWindows -ErrorAction SilentlyContinue)) { . (Join-Path $PSScriptRoot 'session.ps1') }
 Initialize-WorkdayWindows;Set-WorkdayTaskbarWindow $Window
 $iconPath=Join-Path $PSScriptRoot 'attendance.ico';if(Test-Path -LiteralPath $iconPath){$Window.Icon=New-Object Drawing.Icon($iconPath)}
 $script:UiBackground=[Drawing.ColorTranslator]::FromHtml('#E7EBED');$script:UiInk=[Drawing.ColorTranslator]::FromHtml('#394C5B')
 $script:UiCyan=[Drawing.ColorTranslator]::FromHtml('#55758D');$script:UiMint=[Drawing.ColorTranslator]::FromHtml('#647F91');$script:UiOrange=[Drawing.ColorTranslator]::FromHtml('#647F91')
 $Window.BackColor=$script:UiBackground;$Window.ForeColor=$script:UiInk
 function Apply-SoftControls($parent){
  [WorkdaySoftTheme]::Container($parent)
  foreach($control in $parent.Controls){
   if($control -is [Windows.Forms.Button]){
    $primary=$control.Text -match '조회|저장|내보내기|신청|정리|작성|시작|설치'
    $control.BackColor=if($primary){$script:UiCyan}else{$script:UiBackground};$control.ForeColor=if($primary){[Drawing.Color]::White}else{$script:UiInk}
    $control.Font=New-Object Drawing.Font('Malgun Gothic',$(if($control.Width -lt 80){9}else{10}),[Drawing.FontStyle]::Bold);$control.Cursor=[Windows.Forms.Cursors]::Hand
    [WorkdaySoftTheme]::ApplyButton($control)
   }elseif($control -is [Windows.Forms.DataGridView]){
    $control.BackgroundColor=[Drawing.ColorTranslator]::FromHtml('#F3F5F6');$control.BorderStyle='None';$control.EnableHeadersVisualStyles=$false
    $control.ColumnHeadersDefaultCellStyle.BackColor=[Drawing.ColorTranslator]::FromHtml('#D7E0E6');$control.ColumnHeadersDefaultCellStyle.ForeColor=$script:UiInk
    $control.ColumnHeadersDefaultCellStyle.SelectionBackColor=[Drawing.ColorTranslator]::FromHtml('#C3D3DF');$control.ColumnHeadersDefaultCellStyle.SelectionForeColor=$script:UiInk
    $control.ColumnHeadersHeight=42;$control.DefaultCellStyle.BackColor=[Drawing.ColorTranslator]::FromHtml('#F6F8F9');$control.DefaultCellStyle.ForeColor=$script:UiInk
    $control.DefaultCellStyle.SelectionBackColor=[Drawing.ColorTranslator]::FromHtml('#C8DAE4');$control.DefaultCellStyle.SelectionForeColor=$script:UiInk
    $control.AlternatingRowsDefaultCellStyle.BackColor=[Drawing.ColorTranslator]::FromHtml('#EAF0F3');$control.GridColor=[Drawing.ColorTranslator]::FromHtml('#DAE2E7')
   }elseif($control -is [Windows.Forms.TextBoxBase] -or $control -is [Windows.Forms.ComboBox] -or $control -is [Windows.Forms.NumericUpDown] -or $control -is [Windows.Forms.DateTimePicker]){
    $control.BackColor=[Drawing.ColorTranslator]::FromHtml('#F5F7F8');$control.ForeColor=$script:UiInk
    if($control -is [Windows.Forms.TextBoxBase]){$control.BorderStyle='FixedSingle'}
    if($control -is [Windows.Forms.ComboBox]){$control.FlatStyle='Flat'}
   }elseif($control -is [Windows.Forms.Label]){
    if($control.BackColor.GetBrightness() -lt .5 -or $control.BackColor -eq [Drawing.Color]::White){$control.BackColor=[Drawing.Color]::Transparent;$control.ForeColor=$script:UiInk}
    if($parent -is [Windows.Forms.Panel]){$control.ForeColor=$script:UiInk};$control.BackColor=[Drawing.Color]::Transparent
   }elseif($control -is [Windows.Forms.Panel] -or $control -is [Windows.Forms.GroupBox]){
    $control.BackColor=$script:UiBackground;$control.ForeColor=$script:UiInk;Apply-SoftControls $control
   }elseif($control -is [Windows.Forms.CheckBox]){$control.BackColor=[Drawing.Color]::Transparent;$control.ForeColor=$script:UiInk}
  }
 }
 Apply-SoftControls $Window
}
