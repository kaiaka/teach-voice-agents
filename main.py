
import asyncio
import signal
import threading
from datetime import datetime
from realtime.client import RealtimeClient
from interfaces import speaker
import os


STOP_EVENT = threading.Event()

async def main():

    def handle_sigint(sig, frame):
        STOP_EVENT.set()
    
    signal.signal(signal.SIGINT, handle_sigint)

    # logging setup
    def log_event(event, source="", value="", extra=""):
        row = {
            "timestamp": datetime.now().isoformat(timespec="milliseconds"),
            "event": event,
            "source": source,
            "value": value.replace("\n", " ").strip(),
            "extra": extra.replace("\n", " ").strip()
        }
        try:
            print(event)
        except Exception:
            pass

    # realtime client setup
    loop = asyncio.get_running_loop()
    client = RealtimeClient(
        loop=loop,
        log_event=log_event,
        speaker=speaker,
        audio_user_path=None,
        ai_audio_logger=None
    )
    client_thread = threading.Thread(target=client.run, daemon=True)
    client_thread.start()

    try:
        while not STOP_EVENT.is_set():
            await asyncio.sleep(0.5)
    finally:
        print("[Main] Cleaning up and shutting down...")
        try:
            client.close()
        except Exception:
            pass
        print("[Main] Done.")
        os._exit(0)


if __name__ == "__main__":
    asyncio.run(main())
    