$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$root=Split-Path -Parent $PSScriptRoot
. (Join-Path $root 'app\session.ps1')
Initialize-WorkdayWindows
Add-Type -ReferencedAssemblies System.Windows.Forms -TypeDefinition @'
using System.Windows.Forms;
public class PinningTestForm : Form {
    public void RebuildHandle() { RecreateHandle(); }
}
'@
$form=New-Object PinningTestForm
$form.ShowInTaskbar=$false
Set-WorkdayTaskbarWindow $form
$executable=Join-Path $root 'app\근태매니저.exe'
try {
 foreach($iteration in 1..2) {
  if($iteration -eq 2){$form.RebuildHandle()}
  $handle=$form.Handle
  $command=[WorkdayWindowOwner]::GetTaskbarProperty($handle,2)
  $icon=[WorkdayWindowOwner]::GetTaskbarProperty($handle,3)
  $name=[WorkdayWindowOwner]::GetTaskbarProperty($handle,4)
  $appId=[WorkdayWindowOwner]::GetTaskbarProperty($handle,5)
  if($command -ne ('"'+$executable+'"')){throw "Relaunch command mismatch: $command"}
  if($command -match 'powershell'){throw 'Pinned command still targets PowerShell'}
  if($icon -ne ($executable+',0') -or $name -ne '근태매니저' -or $appId -ne 'Raphlow.AttendanceManager'){throw 'Pinning branding mismatch'}
 }
 # Exercise the real native property-store implementation and native EXE target.
 $p=Start-WorkdayHiddenProcess $executable '--self-test' (Split-Path $executable)
 $p.WaitForExit();if($p.ExitCode -ne 0){throw 'Pinned native launch target failed'};$p.Dispose()
 $fixture=Join-Path $root ('.test-data\pinning-'+[Guid]::NewGuid().ToString('N'))
 New-Item -ItemType Directory -Path $fixture -Force|Out-Null
 $link=Join-Path $fixture '근태매니저.lnk'
 $shell=New-Object -ComObject WScript.Shell
 $shortcut=$shell.CreateShortcut($link);$shortcut.TargetPath=$executable;$shortcut.IconLocation=$icon;$shortcut.Save()
 [WorkdayWindowOwner]::SetShortcutAppId($link)
 [WorkdayWindowOwner]::SetShortcutAppId($link)
 $folder=(New-Object -ComObject Shell.Application).Namespace($fixture)
 $savedId=$folder.ParseName('근태매니저.lnk').ExtendedProperty('System.AppUserModel.ID')
 if($savedId -ne $appId){throw 'Shortcut AppID was not persisted'}
 if($shell.CreateShortcut($link).TargetPath -ne $executable){throw 'Shortcut target changed'}
 [WorkdayWindowOwner]::ClearTaskbarDetails($handle)
 if([WorkdayWindowOwner]::GetTaskbarProperty($handle,2)){throw 'Relaunch properties not cleared'}
 Write-Output 'TASKBAR_PINNING_OK: native EXE command, icon, display name, explicit window AppID; handle recreation; persisted shortcut AppID; native target self-test; cleanup'
}finally{$form.Dispose()}
