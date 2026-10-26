"""Bounded verification of Kit's asynchronously written RGB/RGBA PNG files."""
import asyncio
import hashlib
import struct
import time
import zlib
from pathlib import Path


def verify_png(path, resolution, max_file_bytes=32*1024**2):
    path = Path(path)
    if not 0 < path.stat().st_size <= max_file_bytes:
        raise ValueError('PNG file size is outside the capture budget')
    with path.open('rb') as stream:
        data = stream.read(max_file_bytes+1)
    if len(data)>max_file_bytes or data[:8]!=b'\x89PNG\r\n\x1a\n':
        raise ValueError('Invalid PNG signature or size')
    offset=8; header=None; decoder=None; raw=bytearray(); ended=False
    expected_size=0
    while offset<len(data):
        if offset+12>len(data):raise ValueError('Incomplete PNG chunk')
        length=struct.unpack_from('>I',data,offset)[0]
        end=offset+12+length
        if end>len(data):raise ValueError('Incomplete PNG payload')
        kind=data[offset+4:offset+8]; payload=data[offset+8:end-4]
        if zlib.crc32(kind+payload)!=struct.unpack_from('>I',data,end-4)[0]:
            raise ValueError('PNG chunk CRC differs')
        if kind==b'IHDR':
            if header is not None or offset!=8 or length!=13:raise ValueError('Invalid PNG header')
            header=struct.unpack('>IIBBBBB',payload)
            width,height,depth,color,compression,filter_method,interlace=header
            if ((width,height)!=tuple(resolution) or depth!=8 or color not in (2,6)
                    or compression or filter_method or interlace):
                raise ValueError('PNG dimensions or pixel encoding differ')
            expected_size=height*(1+width*(4 if color==6 else 3))
            if expected_size>40*1024**2:raise ValueError('Decoded PNG exceeds budget')
        elif kind==b'IDAT':
            if header is None:raise ValueError('PNG data precedes header')
            if decoder is None:decoder=zlib.decompressobj()
            raw.extend(decoder.decompress(payload,expected_size-len(raw)+1))
            if len(raw)>expected_size or decoder.unconsumed_tail:
                raise ValueError('Decoded PNG exceeds its dimensions')
        elif kind==b'IEND':
            if length or end!=len(data):raise ValueError('PNG end marker differs')
            ended=True
        offset=end
    if not ended or decoder is None or not decoder.eof or decoder.unused_data or len(raw)!=expected_size:
        raise ValueError('PNG write or compressed image is incomplete')
    stride=expected_size//header[1]
    if any(raw[i]>4 for i in range(0,len(raw),stride)):
        raise ValueError('PNG scanline filter invalid')
    return {'file':path.name,'sha256':hashlib.sha256(data).hexdigest(),
            'bytes':len(data),'resolution_px':list(resolution),'png_stream_verified':True}


async def wait_for_png(path, resolution, *, timeout_s=30):
    """A renderer callback can precede completion of its asynchronous file write."""
    deadline=time.monotonic()+timeout_s
    last=None
    while time.monotonic()<deadline:
        try:return verify_png(path,resolution)
        except (OSError,ValueError,zlib.error) as error:last=error
        await asyncio.sleep(.05)
    raise TimeoutError('Native PNG did not finish and verify within its write deadline') from last
