function New-WorkdayFeatureHosts([string]$Root) {
    $hosts = @{}
    foreach ($name in @('control.ps1','corrections.ps1','overtime.ps1','trips.ps1','status.ps1','보안안내.ps1')) {
        $space = [RunspaceFactory]::CreateRunspace()
        $space.ApartmentState = 'STA'; $space.ThreadOptions = 'ReuseThread'; $space.Open()
        $pipeline = [PowerShell]::Create(); $pipeline.Runspace = $space
        [void]$pipeline.AddScript({ param($AppRoot,$Feature)
            Add-Type -AssemblyName System.Windows.Forms
            Add-Type -AssemblyName System.Drawing
            . (Join-Path $AppRoot 'session.ps1')
            Initialize-WorkdayWindows
            # Build and dispose an invisible form once, before the user clicks.
            # SelfTest never registers tasks or submits anything to the site.
            & (Join-Path $AppRoot $Feature) -SelfTest
        }).AddArgument($Root).AddArgument($name)
        $hosts[$name] = @{ space=$space; pipeline=$pipeline; pending=$pipeline.BeginInvoke(); phase='warming'; requested=$false; owner=0; root=$Root }
    }
    return $hosts
}
function Open-WorkdayFeatureHost($Hosts, [string]$Name, [long]$OwnerHandle) {
    $hostState = $Hosts[$Name]
    if (-not $hostState) { throw '메뉴 화면을 찾을 수 없습니다.' }
    if ($hostState.phase -eq 'active') { return }
    $hostState.owner=$OwnerHandle; $hostState.requested=$true
}
function Update-WorkdayFeatureHosts($Hosts) {
    foreach ($name in @($Hosts.Keys)) {
        $hostState=$Hosts[$name]
        if ($hostState.pending -and $hostState.pending.IsCompleted) {
            try {
                [void]$hostState.pipeline.EndInvoke($hostState.pending)
                if ($hostState.pipeline.Streams.Error.Count) { throw $hostState.pipeline.Streams.Error[0].Exception }
            } catch { Write-Output ('화면 실행 확인: ' + $_.Exception.Message) }
            $hostState.pipeline.Commands.Clear(); $hostState.pipeline.Streams.Error.Clear()
            $hostState.pending=$null; $hostState.phase='ready'
        }
        if ($hostState.phase -eq 'ready' -and $hostState.requested) {
            $hostState.requested=$false
            [void]$hostState.pipeline.AddCommand((Join-Path $hostState.root $name)).AddParameter('OwnerHandle',$hostState.owner)
            $hostState.phase='active'; $hostState.pending=$hostState.pipeline.BeginInvoke()
        }
    }
}
function Test-WorkdayFeatureBusy($Hosts) {
    return @($Hosts.Values | Where-Object { $_.requested -or $_.phase -eq 'active' }).Count -gt 0
}
function Close-WorkdayFeatureHosts($Hosts) {
    foreach ($hostState in $Hosts.Values) {
        if ($hostState.pending -and -not $hostState.pending.IsCompleted) { $hostState.pipeline.Stop() }
        $hostState.pipeline.Dispose(); $hostState.space.Dispose()
    }
}
