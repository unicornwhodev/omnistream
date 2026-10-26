import asyncio
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from native_capture import verify_png,wait_for_png


def small_png():
    def chunk(kind,payload):
        return struct.pack('>I',len(payload))+kind+payload+struct.pack('>I',zlib.crc32(kind+payload))
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',2,1,8,6,0,0,0))
            +chunk(b'IDAT',zlib.compress(b'\0'+bytes([20,30,40,255])*2))+chunk(b'IEND',b''))


class NativeCaptureTests(unittest.TestCase):
    def test_complete_pixels_crc_and_dimensions_are_required(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'frame.png'; original=small_png();p.write_bytes(original)
            self.assertTrue(verify_png(p,(2,1))['png_stream_verified'])
            with self.assertRaises(ValueError):verify_png(p,(3,1))
            for damaged in (original[:-2],original[:45]+b'X'+original[46:],original+b'extra'):
                p.write_bytes(damaged)
                with self.assertRaises((ValueError,zlib.error)):verify_png(p,(2,1))

    def test_callback_before_file_completion_waits_for_actual_bytes(self):
        async def scenario(p):
            data=small_png();p.write_bytes(data[:40])
            async def finish():
                await asyncio.sleep(.07);p.write_bytes(data)
            task=asyncio.create_task(finish())
            result=await wait_for_png(p,(2,1),timeout_s=1)
            await task
            self.assertEqual(result['bytes'],len(data))
        with tempfile.TemporaryDirectory() as root:asyncio.run(scenario(Path(root)/'frame.png'))

    def test_incomplete_file_has_a_finite_deadline(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'frame.png';p.write_bytes(small_png()[:-12])
            with self.assertRaises(TimeoutError):asyncio.run(wait_for_png(p,(2,1),timeout_s=.06))
