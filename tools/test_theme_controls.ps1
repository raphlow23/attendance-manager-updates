$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Windows.Forms,System.Drawing
. (Join-Path (Split-Path -Parent $PSScriptRoot) 'app/theme.ps1')
Add-Type -ReferencedAssemblies System.Windows.Forms @'
using System;
using System.Runtime.InteropServices;
using System.Windows.Forms;
public class QuietThemeForm:Form { protected override bool ShowWithoutActivation{get{return true;}} }
public static class ThemeInputProbe {
 [DllImport("user32.dll",CharSet=CharSet.Unicode)] public static extern IntPtr FindWindowEx(IntPtr p,IntPtr a,string n,string t);
 [DllImport("user32.dll")] public static extern IntPtr SendMessage(IntPtr h,int m,IntPtr w,IntPtr l);
}
'@
$f=New-Object QuietThemeForm;$f.ShowInTaskbar=$false;$f.StartPosition='Manual';$f.Location=New-Object Drawing.Point(-20000,-20000)
$f.Size=New-Object Drawing.Size(600,400)
$n=New-Object Windows.Forms.NumericUpDown;$n.Location=New-Object Drawing.Point(25,25);$n.Value=10;$f.Controls.Add($n)
$d=New-Object Windows.Forms.DateTimePicker;$d.Location=New-Object Drawing.Point(25,75);$d.ShowUpDown=$true;$d.Format='Custom';$d.CustomFormat='HH:mm';$d.Value=[DateTime]'2026-10-29T08:30:00';$f.Controls.Add($d)
$c=New-Object Windows.Forms.ComboBox;$c.Location=New-Object Drawing.Point(25,125);$c.DropDownStyle='DropDownList';[void]$c.Items.Add('1시간');[void]$c.Items.Add('2시간');$c.SelectedIndex=0;$f.Controls.Add($c)
$b=New-Object Windows.Forms.Button;$b.Location=New-Object Drawing.Point(25,180);$b.Text='메뉴';$f.Controls.Add($b)
$g=New-Object Windows.Forms.DataGridView;$g.Location=New-Object Drawing.Point(250,25);$g.Width=280;[void]$g.Columns.Add('weekday','요일');[void]$g.Columns.Add('hours','인정시간');$f.Controls.Add($g)
Set-UiTheme $f
foreach($column in $g.Columns){$column.Width=220}
try{
 $f.Show();[Windows.Forms.Application]::DoEvents()
 foreach($input in @($n,$d,$c)){if([WorkdaySoftTheme]::InputSkinCount($input) -lt 1){throw ('Native arrow decoration missing: '+$input.GetType().Name)}}
 $up=@($n.Controls|Where-Object{$_ -isnot [Windows.Forms.TextBox]})[0]
 $point=[int](($up.ClientSize.Height/4)*65536+$up.ClientSize.Width/2)
 [void][ThemeInputProbe]::SendMessage($up.Handle,0x201,[IntPtr]1,[IntPtr]$point)
 [void][ThemeInputProbe]::SendMessage($up.Handle,0x202,[IntPtr]0,[IntPtr]$point)
 if($n.Value -ne 11){throw 'Native numeric arrow no longer increments'}
 $handle=[ThemeInputProbe]::FindWindowEx($d.Handle,[IntPtr]::Zero,'msctls_updown32',$null)
 $before=$d.Value
 [void][ThemeInputProbe]::SendMessage($handle,0x201,[IntPtr]1,[IntPtr]131077)
 [void][ThemeInputProbe]::SendMessage($handle,0x202,[IntPtr]0,[IntPtr]131077)
 if($d.Value -eq $before){throw 'Native time arrow no longer changes time'}
 [void][ThemeInputProbe]::SendMessage($c.Handle,0x100,[IntPtr]40,[IntPtr]0)
 [void][ThemeInputProbe]::SendMessage($c.Handle,0x101,[IntPtr]40,[IntPtr]0)
 if($c.SelectedIndex -ne 1){throw 'ComboBox Down key no longer changes selection'}
 [WorkdaySoftTheme]::SetSelected($b,$true);if(-not [WorkdaySoftTheme]::IsPressed($b)){throw 'Selected menu is not inset'}
 [WorkdaySoftTheme]::SetSelected($b,$false);if([WorkdaySoftTheme]::IsPressed($b)){throw 'Menu inset selection does not clear'}
 if($g.ColumnHeadersDefaultCellStyle.Alignment -ne 'MiddleCenter' -or $g.ColumnHeadersDefaultCellStyle.WrapMode -ne 'False'){throw 'Header alignment or wrapping mismatch'}
 foreach($column in $g.Columns){if($column.Width -lt [Windows.Forms.TextRenderer]::MeasureText($column.HeaderText,$g.Font).Width+22){throw 'Short header can wrap or clip'}}
 $scroll=@($g.Controls|Where-Object{$_ -is [Windows.Forms.HScrollBar] -and $_.Visible})[0]
 if(-not $scroll){throw 'Horizontal scroll fixture not visible'}
 if([WorkdaySoftTheme]::GridSkinCount($g) -lt 1){throw 'Native scrollbar skin not bound'}
 $old=$g.HorizontalScrollingOffset
 [void][ThemeInputProbe]::SendMessage($g.Handle,0x114,[IntPtr]1,$scroll.Handle)
 [Windows.Forms.Application]::DoEvents()
 if($g.HorizontalScrollingOffset -le $old){throw 'Styled scrollbar no longer moves grid'}
 if($g.BorderStyle -ne 'None' -or $g.ColumnHeadersBorderStyle -ne 'None'){throw 'Grid border remains'}
 Write-Output 'THEME_CONTROLS_OK: borderless grid and native horizontal scroll; real numeric/time arrow clicks, ComboBox keyboard, selected inset, centered nonwrapping headers; no site or account actions'
}finally{$f.Close();$f.Dispose()}
