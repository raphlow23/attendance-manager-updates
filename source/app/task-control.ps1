function Repair-WorkdayWatchdogTask([string]$Root) {
    $task = Get-ScheduledTask -TaskName '자동출퇴근점검' -ErrorAction SilentlyContinue
    if (-not $task) { return }
    $action = @($task.Actions)[0]
    $scriptPath = Join-Path $Root 'watchdog.ps1'
    if ($action.Execute -like '*powershell.exe' -and $action.Arguments -and $action.Arguments.IndexOf($scriptPath,[StringComparison]::OrdinalIgnoreCase) -ge 0) {
        $native = New-ScheduledTaskAction -Execute (Join-Path $Root 'WorkdayGuard.exe') -Argument '--watchdog'
        Set-ScheduledTask -TaskName '자동출퇴근점검' -Action $native -ErrorAction Stop | Out-Null
    }
}
function Invoke-WorkdayTaskAction([string]$Root, [string]$Action, $PreviousSettings = $null) {
    $ErrorActionPreference='Stop'
    $names=@('자동출근','자동퇴근','자동출퇴근로그인','자동출퇴근점검')
    $settingsFile=Join-Path $Root 'dist\자동출근설정.json'
    if($Action -eq 'register') {
        try {
            $process=Start-WorkdayHiddenProcess (Join-Path $Root 'runtime\python.exe') ('"'+(Join-Path $Root 'main.py')+'" --register-tasks') $Root -CaptureError
            try {
                $errorRead=$process.StandardError.ReadToEndAsync()
                $process.WaitForExit()
                $detail=$errorRead.GetAwaiter().GetResult()
                if($process.ExitCode -ne 0){throw ('예약 작업 등록 실패: '+$detail)}
            } finally {$process.Dispose()}
            Start-WorkdayEngine
        } catch {
            if($null -ne $PreviousSettings){Write-WorkdayText $settingsFile ([string]$PreviousSettings)}
            else {Remove-Item -LiteralPath $settingsFile -Force -ErrorAction SilentlyContinue}
            throw
        }
    }
    $tasks=@(Get-ScheduledTask -TaskName $names -ErrorAction SilentlyContinue)
    if($Action -in @('pause','resume')) {
        if(-not(Test-Path -LiteralPath $settingsFile)){throw '먼저 계정을 저장하고 작업을 등록해 주세요.'}
        $config=Get-Content -LiteralPath $settingsFile -Raw -Encoding UTF8 | ConvertFrom-Json
        if($Action -eq 'pause') {
            $config | Add-Member -NotePropertyName enabled -NotePropertyValue $false -Force
            Write-WorkdayText $settingsFile ($config|ConvertTo-Json)
            Stop-WorkdayEngine
            foreach($task in $tasks){
                if($task.State -eq 'Running'){Stop-ScheduledTask -TaskName $task.TaskName -ErrorAction SilentlyContinue}
                Disable-ScheduledTask -TaskName $task.TaskName | Out-Null
            }
        } else {
            if(@($names|Where-Object{$_ -notin $tasks.TaskName}).Count){throw '예약 작업이 없습니다. 저장 및 작업 등록을 먼저 눌러 주세요.'}
            # Keep the stop flag until every scheduled task has been enabled.
            foreach($task in $tasks){Enable-ScheduledTask -TaskName $task.TaskName|Out-Null}
            Start-WorkdayEngine
        }
        $tasks=@(Get-ScheduledTask -TaskName $names -ErrorAction SilentlyContinue)
    }
    $lines=foreach($name in $names){
        $task=@($tasks|Where-Object{$_.TaskName -eq $name})[0]
        if(-not $task){"${name}: 미등록";continue}
        $state=switch([string]$task.State){'Disabled'{'정지됨'};'Running'{'실행 중'};'Ready'{'사용 중'};default{[string]$task.State}}
        "${name}: $state"
    }
    $message=switch($Action){'pause'{'예약 작업과 자동 실행을 함께 일시 정지했습니다.'};'resume'{'예약 작업과 자동 실행을 함께 다시 시작했습니다.'};'register'{'설정 저장과 예약 작업 등록을 완료했습니다.'};default{''}}
    [PSCustomObject]@{lines=@($lines);message=$message}
}
function New-WorkdayTaskContext {
    $space=[RunspaceFactory]::CreateRunspace();$space.ThreadOptions='ReuseThread';$space.Open()
    return $space
}
function Start-WorkdayTaskJob($Context,[string]$Root,[string]$Action,$PreviousSettings=$null) {
    $pipeline=[PowerShell]::Create();$pipeline.Runspace=$Context
    [void]$pipeline.AddScript({param($AppRoot,$Mode,$Previous)
        . (Join-Path $AppRoot 'session.ps1')
        . (Join-Path $AppRoot 'task-control.ps1')
        Invoke-WorkdayTaskAction $AppRoot $Mode $Previous
    }).AddArgument($Root).AddArgument($Action).AddArgument($PreviousSettings)
    try{return @{pipeline=$pipeline;pending=$pipeline.BeginInvoke();action=$Action}}
    catch{$pipeline.Dispose();throw}
}
