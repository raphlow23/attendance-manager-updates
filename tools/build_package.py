"""Package only application sources, installer assets and offline dependencies."""
import hashlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / '출근정리_설치패키지_2026-10-26.zip'
ROOT_FILES = [
    '사용안내.txt', '설치하기.bat', '출퇴근관리.bat', 'gui-install.ps1',
    'install.cmd', 'install.ps1', 'requirements.txt', 'VERSION.txt',
    'python-3.12.10-embed-amd64.zip', '설치.exe', '출근정리.exe', '출퇴근관리.exe', '개발변경_설정_시험안내.md',
]


def build():
    files = [ROOT / name for name in ROOT_FILES]
    files += list((ROOT / 'wheels').glob('*.whl'))
    files += [ROOT / 'app' / name for name in ('main.py', 'resident.py', 'attendance_recovery.py', 'overtime_requests.py', 'control.ps1', 'launcher.ps1', 'overtime.ps1', 'theme.ps1', 'session.ps1', 'status.ps1', '출퇴근관리.bat', '출퇴근관리.exe', 'WorkdayGuard.exe', 'watchdog.ps1', 'notify.ps1', '보안안내.ps1', 'update.ps1', 'update-settings.ps1', 'update-config.json', 'update-public.xml', 'release-version.txt')]
    files += [p for p in (ROOT / 'app' / 'driver').rglob('*') if p.is_file()]
    files.append(ROOT / 'app' / '출근정리.exe')
    files += [ROOT / '근태매니저.exe', ROOT / 'app' / '근태매니저.exe']
    files.append(ROOT / 'app' / 'attendance.ico')
    files += [ROOT / 'app' / name for name in ('ui-host.ps1', 'task-control.ps1', 'attendance_changes.py', 'corrections.ps1')]
    files.append(ROOT / 'app' / 'monthly_reconcile.py')
    files.append(ROOT / 'app' / 'site_access.py')
    files += [ROOT / 'app' / name for name in ('business_trips.py','trip_site.py','trips.ps1','trip_export.py')]
    files.append(ROOT / 'app' / 'overtime-drafts.ps1')
    files += [ROOT / 'app' / name for name in ('install-integration.ps1','uninstall.ps1','제거.exe')]
    files.sort(key=lambda p: p.relative_to(ROOT).as_posix())
    manifest = ROOT / 'MANIFEST-SHA256.txt'
    manifest.write_text(''.join(
        f'{hashlib.sha256(p.read_bytes()).hexdigest().upper()}  {p.relative_to(ROOT).as_posix()}\n'
        for p in files
    ), encoding='utf-8')
    with ZipFile(OUTPUT, 'w', ZIP_DEFLATED) as archive:
        for path in files + [manifest]:
            archive.write(path, path.relative_to(ROOT).as_posix())
    with ZipFile(OUTPUT) as archive:
        assert archive.testzip() is None
        names = archive.namelist()
        assert 'app/attendance_recovery.py' in names
        assert 'app/overtime_requests.py' in names and 'app/launcher.ps1' in names
        assert not any('/dist/' in n or '__pycache__' in n or (n.endswith('.json') and n != 'app/update-config.json') or 'private' in n for n in names)
        for line in archive.read('MANIFEST-SHA256.txt').decode('utf-8').splitlines():
            digest, path = line.split('  ', 1)
            assert hashlib.sha256(archive.read(path)).hexdigest().upper() == digest
    print(f'PACKAGE_OK: {OUTPUT.name} ({OUTPUT.stat().st_size} bytes, {len(names)} files)')


if __name__ == '__main__':
    build()
