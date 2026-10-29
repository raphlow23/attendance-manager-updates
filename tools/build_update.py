"""Create the small code update archive, excluding runtime, data and signing keys."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
version = int((ROOT / 'app' / 'release-version.txt').read_text().strip())
output = ROOT / 'releases' / f'attendance-manager-v{version}.zip'
output.parent.mkdir(exist_ok=True)
files = sorted(p for p in (ROOT / 'app').iterdir()
               if p.is_file() and p.suffix in ('.py', '.ps1', '.exe', '.txt'))
with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
    for path in files:
        archive.write(path, path.name)
with ZipFile(output) as archive:
    assert archive.testzip() is None
    assert 'release-version.txt' in archive.namelist()
    assert not any('/' in n or '\\' in n or 'private' in n or n.endswith('.json') for n in archive.namelist())
print(f'CODE_UPDATE_OK: {output.name}, {output.stat().st_size} bytes')
