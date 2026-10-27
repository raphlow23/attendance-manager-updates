function Test-UpdateSignature($Manifest, [string]$PublicKeyFile) {
    if ($Manifest.sha256 -notmatch '^[a-fA-F0-9]{64}$' -or ([Uri]$Manifest.archive_url).Scheme -ne 'https' -or $Manifest.runtime -ne '3.12.10') { throw '업데이트 형식 또는 런타임이 일치하지 않습니다.' }
    $version = [int]$Manifest.version
    $payload = "$version`n$($Manifest.archive_url)`n$($Manifest.sha256)`n$($Manifest.runtime)"
    $rsa = New-Object Security.Cryptography.RSACryptoServiceProvider
    try {
        $rsa.FromXmlString([IO.File]::ReadAllText($PublicKeyFile))
        return $rsa.VerifyData([Text.Encoding]::UTF8.GetBytes($payload), [Security.Cryptography.CryptoConfig]::MapNameToOID('SHA256'), [Convert]::FromBase64String($Manifest.signature))
    } finally { $rsa.PersistKeyInCsp = $false; $rsa.Dispose() }
}
function Get-WorkdayUpdateOffer([string]$Root) {
    $migration = Join-Path $Root 'dist\native-watchdog-v14.done'
    if (-not (Test-Path -LiteralPath $migration)) {
        try {
            . (Join-Path $Root 'task-control.ps1')
            Repair-WorkdayWatchdogTask $Root
            New-Item -ItemType Directory -Path (Join-Path $Root 'dist') -Force | Out-Null
            [IO.File]::WriteAllText($migration, (Get-Date).ToString('o'))
        } catch {
            try { [IO.File]::AppendAllText((Join-Path $Root 'dist\ui-errors.log'), ((Get-Date).ToString('o') + ' watchdog migration: ' + $_.Exception.Message + "`r`n")) } catch {}
        }
    }
    $config = Get-Content -LiteralPath (Join-Path $Root 'update-config.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if (-not $config.enabled -or ([Uri]$config.manifest_url).Scheme -ne 'https') { throw '자동 업데이트 주소를 확인할 수 없습니다.' }
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $manifest = Invoke-RestMethod -Uri $config.manifest_url -TimeoutSec 8 -Headers @{ 'Cache-Control' = 'no-cache' }
    $current = [int](Get-Content -LiteralPath (Join-Path $Root 'release-version.txt') -Raw)
    if ([int]$manifest.version -le $current) { return [PSCustomObject]@{ available=$false; status="자동 업데이트: 최신 버전 ($current)"; manifest=$null } }
    if (-not (Test-UpdateSignature $manifest (Join-Path $Root 'update-public.xml'))) { throw '업데이트 전자서명이 일치하지 않습니다.' }
    return [PSCustomObject]@{ available=$true; status="새 버전 $($manifest.version): 설정 창을 닫으면 자동 적용합니다."; manifest=$manifest }
}
function Start-WorkdayUpdateJob([string]$Root, $Manifest = $null) {
    $pipeline = [PowerShell]::Create()
    [void]$pipeline.AddScript({
        param($ScriptFile, $ApplicationRoot, $Offer)
        $ErrorActionPreference = 'Stop'
        . $ScriptFile
        if ($null -eq $Offer) { Get-WorkdayUpdateOffer $ApplicationRoot }
        else { Invoke-WorkdayUpdate $ApplicationRoot $Offer }
    }).AddArgument((Join-Path $Root 'update.ps1')).AddArgument($Root).AddArgument($Manifest)
    try { return [PSCustomObject]@{ pipeline=$pipeline; pending=$pipeline.BeginInvoke() } }
    catch { $pipeline.Dispose(); throw }
}
function Invoke-WorkdayUpdate([string]$Root, $Manifest = $null) {
    $configFile = Join-Path $Root 'update-config.json'
    if (-not (Test-Path -LiteralPath $configFile)) { return '자동 업데이트: 배포 주소 연결 전' }
    $stage = $null
    $backups = @()
    $actionLock = $null
    $paused = $false
    $resumeGuard = $false
    try {
        $config = Get-Content -LiteralPath $configFile -Raw -Encoding UTF8 | ConvertFrom-Json
        if (-not $config.enabled -or -not $config.manifest_url) { return '자동 업데이트: 배포 주소 연결 전' }
        if (([Uri]$config.manifest_url).Scheme -ne 'https') { throw 'HTTPS 업데이트 주소가 필요합니다.' }
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        if ($null -eq $Manifest) { $Manifest = Invoke-RestMethod -Uri $config.manifest_url -TimeoutSec 8 -Headers @{ 'Cache-Control' = 'no-cache' } }
        $current = [int](Get-Content -LiteralPath (Join-Path $Root 'release-version.txt') -Raw)
        if ([int]$manifest.version -le $current) { return "자동 업데이트: 최신 버전 ($current)" }
        if (-not (Test-UpdateSignature $manifest (Join-Path $Root 'update-public.xml'))) { throw '업데이트 전자서명이 일치하지 않습니다.' }
        $stage = Join-Path (Join-Path $Root 'dist') ('update-' + [Guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $stage -Force | Out-Null
        $archivePath = Join-Path $stage 'update.zip'
        Invoke-WebRequest -UseBasicParsing -Uri $manifest.archive_url -OutFile $archivePath -TimeoutSec 60
        if ((Get-Item -LiteralPath $archivePath).Length -gt 20MB) { throw '코드 업데이트 크기 제한을 초과했습니다.' }
        if ((Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash -ne $manifest.sha256) { throw '업데이트 파일 검사에 실패했습니다.' }
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $zip = [IO.Compression.ZipFile]::OpenRead($archivePath)
        try {
            $seen = @{}
            foreach ($entry in $zip.Entries) {
                $name = $entry.FullName
                if ($name -notmatch '^[\p{L}\p{N}_-]+\.(py|ps1|exe|txt)$' -or $entry.Length -gt 10MB -or $seen.ContainsKey($name)) { throw '지원하지 않는 업데이트 파일입니다.' }
                $seen[$name] = $true
                $destination = Join-Path $Root $name
                $backup = Join-Path $stage ($name + '.backup')
                if (Test-Path -LiteralPath $destination) { Copy-Item -LiteralPath $destination -Destination $backup }
                $backups += @{ destination = $destination; backup = $backup; existed = (Test-Path -LiteralPath $destination) }
                [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, (Join-Path $stage $name), $true)
            }
            if (-not $seen.ContainsKey('release-version.txt') -or [int](Get-Content -LiteralPath (Join-Path $stage 'release-version.txt') -Raw) -ne [int]$manifest.version) { throw '업데이트 버전 파일이 일치하지 않습니다.' }
        } finally { $zip.Dispose() }
        # No runtime replacement: preserve credentials, state, logs and active jobs.
        $actionPath = Join-Path $Root 'dist\action.lock'
        $actionLock = New-Object IO.FileStream($actionPath, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::ReadWrite)
        if ($actionLock.Length -eq 0) { $actionLock.SetLength(1) }
        try { $actionLock.Lock(0,1) } catch { throw '자동화 처리 중이므로 업데이트는 다음 실행에 적용합니다.' }
        $guardianStatus = Join-Path $Root 'dist\guardian-status.json'
        if (Test-Path -LiteralPath $guardianStatus) {
            $priorGuard = Get-Content -LiteralPath $guardianStatus -Raw -Encoding UTF8 | ConvertFrom-Json
            $resumeGuard = ($priorGuard.state -in @('running','recovering')) -and [bool](Get-Process -Id $priorGuard.pid -ErrorAction SilentlyContinue)
        }
        [IO.File]::WriteAllText((Join-Path $Root 'dist\update.pause'), 'update in progress')
        $paused = $true
        $guardianStatus = Join-Path $Root 'dist\guardian-status.json'
        for ($wait=0; $wait -lt 20; $wait++) {
            if (-not (Test-Path -LiteralPath $guardianStatus)) { break }
            $guard = Get-Content -LiteralPath $guardianStatus -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($guard.state -eq 'intentional_stop' -or -not (Get-Process -Id $guard.pid -ErrorAction SilentlyContinue)) { break }
            Start-Sleep -Seconds 1
        }
        Start-Sleep -Milliseconds 3300
        foreach ($item in $backups) {
            $name = Split-Path -Leaf $item.destination
            if ($name -eq 'release-version.txt') { continue }
            Copy-Item -LiteralPath (Join-Path $stage $name) -Destination $item.destination -Force
        }
        Copy-Item -LiteralPath (Join-Path $stage 'release-version.txt') -Destination (Join-Path $Root 'release-version.txt') -Force
        return "업데이트 적용 완료: 버전 $($manifest.version). 새 화면은 다음 실행부터 적용됩니다."
    } catch {
        foreach ($item in $backups) {
            if (Test-Path -LiteralPath $item.backup) { Copy-Item -LiteralPath $item.backup -Destination $item.destination -Force -ErrorAction SilentlyContinue }
            elseif (-not $item.existed) { Remove-Item -LiteralPath $item.destination -Force -ErrorAction SilentlyContinue }
        }
        return "업데이트 확인/적용 보류: $($_.Exception.Message)"
    } finally {
        if ($actionLock) { try { $actionLock.Unlock(0,1) } catch {}; $actionLock.Dispose() }
        if ($paused) {
            Remove-Item -LiteralPath (Join-Path $Root 'dist\update.pause') -Force -ErrorAction SilentlyContinue
            if ($resumeGuard -and -not (Test-Path -LiteralPath (Join-Path $Root 'dist\automation.stop'))) { Start-Process -FilePath (Join-Path $Root 'WorkdayGuard.exe') -WindowStyle Hidden }
        }
    }
}
