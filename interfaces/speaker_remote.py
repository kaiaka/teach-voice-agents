import asyncio
import threading
import websockets
import time
import os
from dotenv import load_dotenv

load_dotenv()

ROBOT_SPEECH_URL = os.getenv("ROBOT_SPEECH_URL")
ROBOT_FLUSH_URL = os.getenv("ROBOT_FLUSH_URL")

_loop = None
_audio_ws = None
_connected = asyncio.Event()
_gen = 0

async def _connect_audio():
    global _audio_ws
    while True:
        try:
            print(f"[SpeakerRemote] Connecting to {ROBOT_SPEECH_URL} ...")
            _audio_ws = await websockets.connect(ROBOT_SPEECH_URL, ping_interval=None, max_size=None)
            print("[SpeakerRemote] Connected to robot audio.")
            _connected.set()
            await _audio_ws.wait_closed()
            print("[SpeakerRemote] Audio connection closed.")
        except Exception as e:
            print(f"[SpeakerRemote] Audio connection error ({type(e).__name__}): {e}")
            _connected.clear()
            await asyncio.sleep(1)

def _start_loop():
    global _loop
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    _loop.run_until_complete(_connect_audio())

threading.Thread(target=_start_loop, daemon=True).start()

def play_audio(data: bytes):
    global _loop, _audio_ws
    if not _loop or not _connected.is_set() or not _audio_ws:
        return
    async def _send():
        try:
            await _audio_ws.send(data)
        except Exception as e:
            print(f"[SpeakerRemote] Send error: {e}")
    asyncio.run_coroutine_threadsafe(_send(), _loop)

def stop_audio():
    global _loop

    async def _flush():
        try:
            async with websockets.connect(ROBOT_FLUSH_URL) as ws:
                await ws.send("FLUSH")
                print("[SpeakerRemote] Flush sent to control port.")
        except Exception as e:
            print(f"[SpeakerRemote] Flush error: {e}")

    if not _loop:
        return

    asyncio.run_coroutine_threadsafe(_flush(), _loop)
