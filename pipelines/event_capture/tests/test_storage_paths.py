import asyncio
from pathlib import PureWindowsPath
import tempfile
import threading
import time
import unittest

from fireviewer_capture.storage import _comparison_path
from helpers import config, pipeline, state


class WindowsPathTests(unittest.TestCase):
    def test_equivalent_drive_and_unc_namespaces_match(self):
        for root, child in [
            (r'C:\capture',r'\\?\C:\capture\frames\file.png'),
            (r'\\server\share\capture',r'\\?\UNC\server\share\capture\frames\file.png'),
        ]:
            self.assertTrue(_comparison_path(PureWindowsPath(child)).is_relative_to(PureWindowsPath(root)))

    def test_neighbor_and_other_device_paths_stay_outside(self):
        root=PureWindowsPath(r'C:\capture')
        for child in [r'\\?\C:\capture-neighbor\file.png',r'\\?\D:\capture\file.png',
                      r'\\?\GLOBALROOT\Device\HarddiskVolumeShadowCopy1\capture\file.png']:
            self.assertFalse(_comparison_path(PureWindowsPath(child)).is_relative_to(root))


class WriteDrainTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancellation_drains_started_writes_before_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            p,driver,store,metrics=pipeline(directory,config(1,duration_s=1,cap=2),[state()])
            both_started=threading.Event();release=threading.Event()
            lock=threading.Lock();started=[0];finished=[0]
            def write(*args):
                with lock:
                    started[0]+=1
                    if started[0]==2:both_started.set()
                if not release.wait(3):raise AssertionError('Writer gate was not released')
                with lock:finished[0]+=1
            p.manager._write=write
            task=asyncio.create_task(p.run())
            try:
                self.assertTrue(await asyncio.to_thread(both_started.wait,3))
                task.cancel()
                await asyncio.sleep(0)
                self.assertFalse(task.done())
            finally:
                release.set()
            with self.assertRaises(asyncio.CancelledError):await task
            self.assertEqual(finished[0],2)
            self.assertFalse(driver.handles)

    async def test_first_failure_waits_for_other_started_write(self):
        with tempfile.TemporaryDirectory() as directory:
            p,driver,store,metrics=pipeline(directory,config(1,duration_s=1,cap=2),[state()])
            other_started=threading.Event();other_finished=threading.Event()
            call_lock=threading.Lock();calls=[0]
            def write(*args):
                with call_lock:
                    calls[0]+=1;index=calls[0]
                if index==1:
                    if not other_started.wait(3):raise AssertionError('Second writer did not start')
                    raise OSError('injected write failure')
                other_started.set();time.sleep(.05);other_finished.set()
                return None
            p.manager._write=write
            with self.assertRaisesRegex(OSError,'injected write failure'):
                await p.run()
            self.assertTrue(other_finished.is_set())
            self.assertFalse(driver.handles)


if __name__=='__main__':unittest.main()
