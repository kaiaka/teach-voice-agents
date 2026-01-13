
import asyncio
import signal
import threading
from datetime import datetime
from realtime.client import RealtimeClient
from interfaces import speaker
import os
from util.logger import log_event

STOP_EVENT = threading.Event()
SAY_EVENT = asyncio.Event()

async def keyboard_listener():
    loop = asyncio.get_running_loop()

    while not STOP_EVENT.is_set():
        cmd = await loop.run_in_executor(None, input, "")
        cmd = cmd.strip().lower()

        if cmd == "q":
            STOP_EVENT.set()

        elif cmd == "s":
            SAY_EVENT.set()

async def main():

    def handle_sigint(sig, frame):
        STOP_EVENT.set()
    
    signal.signal(signal.SIGINT, handle_sigint)

    # realtime client setup
    loop = asyncio.get_running_loop()
    client = RealtimeClient(
        loop=loop,
        speaker=speaker,
        audio_user_path=None,
        ai_audio_logger=None
    )
    client_thread = threading.Thread(target=client.run, daemon=True)
    client_thread.start()

    try:
        asyncio.create_task(keyboard_listener())
        
        while not STOP_EVENT.is_set():

            if SAY_EVENT.is_set():
                SAY_EVENT.clear()
                client.say("Please get the supervisor. He's waiting outside the room.")
                
            await asyncio.sleep(0.5)
    finally:
        log_event("main", "", "Cleaning up and shutting down...")
        try:
            client.close()
        except Exception:
            pass
        log_event("main", "", "Done")
        os._exit(0)


if __name__ == "__main__":
    asyncio.run(main())
    