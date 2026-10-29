import ctypes,json,os,sys,tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import main as app

class JsonReplacement(unittest.TestCase):
    def test_failed_replace_preserves_previous_complete_file_and_cleans_temporary(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'worker-health.json';app.save_json(path,{'old':True})
            with patch.object(app.os,'replace',side_effect=PermissionError('held by reader')),patch.object(app.time,'sleep'):
                with self.assertRaises(PermissionError):app.save_json(path,{'new':True})
            self.assertEqual(json.loads(path.read_text()),{'old':True})
            self.assertEqual([p.name for p in Path(folder).iterdir()],['worker-health.json'])
    def test_concurrent_writers_use_independent_temporary_files(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'worker-health.json';errors=[]
            def write(number):
                try:app.save_json(path,dict(number=number,payload='x'*2000))
                except Exception as error:errors.append(error)
            threads=[threading.Thread(target=write,args=(n,)) for n in range(8)]
            for thread in threads:thread.start()
            for thread in threads:thread.join()
            self.assertFalse(errors);self.assertEqual(len(json.loads(path.read_text())['payload']),2000)
            self.assertEqual(len(list(Path(folder).iterdir())),1)
    @unittest.skipUnless(os.name=='nt','Windows sharing mode required')
    def test_temporary_windows_reader_lock_is_retried(self):
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.CreateFileW.argtypes=[ctypes.c_wchar_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p]
        kernel.CreateFileW.restype=ctypes.c_void_p;kernel.CloseHandle.argtypes=[ctypes.c_void_p]
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'worker-health.json';app.save_json(path,{'old':True})
            handle=kernel.CreateFileW(str(path),0x80000000,3,None,3,0,None)
            self.assertNotEqual(handle,ctypes.c_void_p(-1).value)
            release=threading.Thread(target=lambda:(time.sleep(.08),kernel.CloseHandle(handle)))
            release.start()
            try:app.save_json(path,{'new':True})
            finally:release.join()
            self.assertEqual(json.loads(path.read_text()),{'new':True})
