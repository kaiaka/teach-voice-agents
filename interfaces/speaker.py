import asyncio
import pyaudio
import time
import threading

_SAMPLE_RATE = 24000
_CHUNK = 240

_pa = pyaudio.PyAudio()
_stream = None

_lock = None
_write_lock = None
_loop = None
_gen = 0

_visualizer = None

_last_audio_time = 0.0
_speaking_active = False

async def _ensure_loop_locks():
    global _lock, _write_lock, _loop
    loop = asyncio.get_running_loop()
    if _loop is not loop:
        _lock = asyncio.Lock()
        _write_lock = asyncio.Lock()
        _loop = loop

def _open_stream():
    return _pa.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=_SAMPLE_RATE,
        output=True,
        frames_per_buffer=_CHUNK
    )

async def _ensure_stream():
    global _stream
    if _stream is None:
        _stream = _open_stream()

async def play_audio(data: bytes) -> None:
    global _stream, _gen, _last_audio_time, _speaking_active
    await _ensure_loop_locks()
    local_gen = _gen

    async with _lock:
        await _ensure_stream()

    if local_gen != _gen:
        return

    async with _write_lock:
        if local_gen != _gen:
            return
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, _stream.write, data)
            _last_audio_time = time.time()
            if not _speaking_active:
                _speaking_active = True
                if _visualizer:
                    _visualizer.start_speaking()
        except Exception:
            return

# monitor SYSTEM output silence
async def _monitor_silence():
    global _last_audio_time, _speaking_active
    while True:
        await asyncio.sleep(0.2)
        if _speaking_active and (time.time() - _last_audio_time > 0.6):
            _speaking_active = False
            if _visualizer:
                _visualizer.stop_speaking()

async def stop_audio() -> None:
    global _stream, _gen
    await _ensure_loop_locks()

    async with _lock:
        _gen += 1
        async with _write_lock:
            if _stream is not None:
                try:
                    if _stream.is_active():
                        _stream.stop_stream()
                except Exception:
                    pass
                try:
                    _stream.close()
                except Exception:
                    pass
                _stream = None
            _stream = _open_stream()
    print("[Audio] Flushed.")

async def close() -> None:
    global _stream
    await _ensure_loop_locks()
    async with _lock:
        async with _write_lock:
            if _stream is not None:
                try:
                    if _stream.is_active():
                        _stream.stop_stream()
                except Exception:
                    pass
                try:
                    _stream.close()
                except Exception:
                    pass
                _stream = None
            try:
                _pa.terminate()
            except Exception:
                pass

def attach_speech_visualizer(server):
    global _visualizer
    _visualizer = server
    loop = asyncio.get_event_loop()
    loop.create_task(_monitor_silence())
    print(f"[Audio] Speech visualizer attached ({type(server).__name__}) and silence monitor running.")
