import time, wave, audioop, pyaudio
from pathlib import Path
from typing import Callable, Optional

TARGET_RATE   = 24_000
CHUNK_MS      = 10
SAMPLE_WIDTH  = 2
FORMAT        = pyaudio.paInt16
CHANNELS_REQ  = 1

def stream_audio(
        callback: Callable[[bytes], None],
        device_index: Optional[int] = None,
        save_to: Optional[str or Path] = None
) -> None:
    pa = pyaudio.PyAudio()

    print("[Mic] available devices:")
    for i in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(i)
        if info["maxInputChannels"] > 0:
            print(f"  {i}: {info['name']} ({int(info['defaultSampleRate'])} Hz, {info['maxInputChannels']} ch)")

    if device_index is None:
        device_index = pa.get_default_input_device_info()["index"]

    info       = pa.get_device_info_by_index(device_index)
    src_rate   = int(info["defaultSampleRate"])
    src_ch     = max(1, info["maxInputChannels"])
    frames     = int(src_rate * CHUNK_MS / 1000)

    try:
        stream = pa.open(format=FORMAT, channels=CHANNELS_REQ,
                         rate=src_rate, input=True,
                         input_device_index=device_index,
                         frames_per_buffer=frames)
    except IOError:
        stream = pa.open(format=FORMAT, channels=src_ch,
                         rate=src_rate, input=True,
                         input_device_index=device_index,
                         frames_per_buffer=frames)

    print(f"[Mic] selected {device_index}: {info['name']}  rate={src_rate} Hz, channels={stream._channels}")

    wav: Optional[wave.Wave_write] = None
    if save_to is not None:
        path = Path(save_to)
        if path.is_dir() or save_to in ("", "."):
            ts   = time.strftime("%Y%m%d_%H%M%S")
            path = Path(path, f"mic_{ts}.wav")
        path.parent.mkdir(parents=True, exist_ok=True)
        wav = wave.open(str(path), "wb")
        wav.setnchannels(1)
        wav.setsampwidth(SAMPLE_WIDTH)
        wav.setframerate(TARGET_RATE)
        print(f"[Rec] writing input to {path}")

    try:
        while True:
            raw = stream.read(frames, exception_on_overflow=False)
            if stream._channels > 1:
                raw = audioop.tomono(raw, SAMPLE_WIDTH, 0.5, 0.5)
            if src_rate != TARGET_RATE:
                raw, _ = audioop.ratecv(raw, SAMPLE_WIDTH, 1,
                                        src_rate, TARGET_RATE, None)
            callback(raw)
            if wav:
                wav.writeframes(raw)
    finally:
        stream.stop_stream()
        stream.close()
        pa.terminate()
        if wav:
            wav.close()
            print("[Rec] file closed")

def list_devices() -> None:
    pa = pyaudio.PyAudio()
    for i in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(i)
        print(f"{i}: {info['name']}  (inputs={info['maxInputChannels']}, rate={info['defaultSampleRate']})")
    pa.terminate()
