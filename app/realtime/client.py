import os
import json
import base64
import threading
import asyncio
import time
import websocket
from dotenv import load_dotenv
from interfaces.mic_terminal import stream_audio, list_devices
from util.logger import log_event

load_dotenv()

# .env variables
API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_SPEECH_MODEL = os.getenv("OPENAI_SPEECH_MODEL")
OPENAI_LANGUAGE = os.getenv("OPENAI_LANGUAGE")
OPENAI_TRANSCRIPTION_MODEL = os.getenv("OPENAI_TRANSCRIPTION_MODEL")
MIC_INDEX = os.getenv("MIC_INDEX", "").lower()
MIC_INDEX = None if MIC_INDEX == "" else int(MIC_INDEX)
PROMPT_SPEECH_TXT = os.getenv("PROMPT_LOCAL_TXT")


# load prompt from .txt
PROMPT_SPEECH_FILE = os.path.join(os.path.dirname(__file__), "../config", "prompts", PROMPT_SPEECH_TXT)
with open(PROMPT_SPEECH_FILE, "r", encoding="utf-8") as f:
    PROMPT_SPEECH = f.read()

# API variables
URL = f"wss://api.openai.com/v1/realtime?model={OPENAI_SPEECH_MODEL}"
HEADERS = [
    f"Authorization: Bearer {API_KEY}",
    "OpenAI-Beta: realtime=v1"
]

def dbg(tag, extra=""):
    print("[DBG]", tag, extra)


class RealtimeClient:
    def __init__(self, loop=None, speaker=None, audio_user_path=None, ai_audio_logger=None):
        self.loop = loop
        self.speaker = speaker
        self.speech_visualizer = None
        self.ws = None

        self._ai_buf = {}
        self._dialog_buffer = []
        self._last_expression = {}
        self._last_arms = {}

        self._drop_audio_until_new_response = False
        self._last_vad_stop_ts = 0
        self._current_response_id = None

        self.audio_user_path = audio_user_path
        self.ai_audio_logger = ai_audio_logger

        self._first_audio_seen_for_rid = set()

        print(" ------------------------------------------ ")
        print(f'[RTC] Model: {OPENAI_SPEECH_MODEL}')
        print(f'[RTC] Language: {OPENAI_LANGUAGE}')
        print(f'[RTC] Transcription Model: {OPENAI_TRANSCRIPTION_MODEL}')
        print(f'[RTC] Mic Index: {MIC_INDEX}')
        print(" ------------------------------------------ ")

    def _schedule_in_loop(self, coro_or_fn, *args, **kwargs):
        def _runner():
            result = coro_or_fn(*args, **kwargs)
            if asyncio.iscoroutine(result):
                asyncio.create_task(result)
        self.loop.call_soon_threadsafe(_runner)

    def _on_open(self, ws, *_):
        dbg("open")

        # send OpenAI setup
        ws.send(json.dumps({
            "type": "session.update",
            "session": {
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "modalities": ["audio", "text"],
                "input_audio_transcription": {
                    "model": OPENAI_TRANSCRIPTION_MODEL,
                    "language": OPENAI_LANGUAGE
                },
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "silence_duration_ms": 800,
                    "prefix_padding_ms": 300,
                    "create_response": True,
                    "interrupt_response": True
                }
            }
        }))

    def _on_message(self, ws, raw, *_):
        ev = json.loads(raw)
        typ = ev.get("type", "")

        # OpenAI: session created
        if typ == "session.created":
            ws.send(json.dumps({
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "system",
                    "content": [
                        {"type": "input_text", "text": PROMPT_SPEECH}
                    ]
                }
            }))
            
            # start microphone stream, sending chunks to OpenAI Websocket
            threading.Thread(
                target=lambda: stream_audio(
                    lambda chunk: ws.send(json.dumps({
                        "type": "input_audio_buffer.append",
                        "audio": base64.b64encode(chunk).decode()
                    })),
                    MIC_INDEX,
                    save_to=self.audio_user_path
                ),
                daemon=True
            ).start()

        # OpenAI: USER input started
        if typ == "input_audio_buffer.speech_started":
            now = time.monotonic()

            # filter brief speech start events: at least 250ms since last stop
            # vad = "voice activity detection"
            if now - self._last_vad_stop_ts > 0.25:
                self._last_vad_stop_ts = now

                # stop SYSTEM audio output (important for interruptions)
                self._schedule_in_loop(self.speaker.stop_audio)
                # ensure incoming system audio to be dropped
                self._drop_audio_until_new_response = True

                # logging and visualization
                if self.ai_audio_logger:
                    self.ai_audio_logger.flush_segment()
                if self.speech_visualizer:
                    self.speech_visualizer.stop_speaking()
            log_event("api",source="realtime_api",value="speech_started")
        
        # OpenAI: USER input stopped
        if typ == "input_audio_buffer.speech_stopped":
            log_event("api",source="realtime_api",value="speech_stopped")

        # OpenAI: USER transcription completed
        if typ == "conversation.item.input_audio_transcription.completed":
            text = ev["transcript"].strip()
            self._dialog_buffer.append(f"User: {text}")
            log_event("user_text", source="user", value=text)
            log_event("api",source="realtime_api",value="input_audio_transcription.completed")

        # OpenAI: SYSTEM response started
        if typ in ("response.created", "response.started"):
            rid = ev.get("response", {}).get("id")
            if rid and rid != self._current_response_id:
                self._current_response_id = rid
                self._drop_audio_until_new_response = False
                log_event("api",source="realtime_api",value=typ,extra=json.dumps({"rid": rid}))
                if self.speech_visualizer:
                    self.speech_visualizer.start_speaking()

        # OpenAI: incoming audio chunks for SYSTEM response audio
        if typ == "response.audio.delta":
            data = base64.b64decode(ev["delta"])
            rid = ev.get("response_id", self._current_response_id)
            
            if rid and rid not in self._first_audio_seen_for_rid:
                self._first_audio_seen_for_rid.add(rid)
                log_event("api", source="realtime_api", value="response.audio.first_delta", extra=json.dumps({"rid": rid}))
                if self.ai_audio_logger:
                    self.ai_audio_logger.mark_start(rid)

            # play audio on speaker 
            if not self._drop_audio_until_new_response:
                if self.ai_audio_logger:
                    self.ai_audio_logger.append(data)
                self._schedule_in_loop(self.speaker.play_audio, data)

        # OpenAI: incoming transcript deltas for SYSTEM response
        if typ == "response.audio_transcript.delta":
            rid = ev["response_id"]
            self._ai_buf.setdefault(rid, []).append(ev["delta"])

        # OpenAI: SYSTEM response done: means NOT PLAYBACK but generation done
        if typ == "response.done":
            rid = ev["response"]["id"]
            log_event("api", source="realtime_api", value="response.done", extra=json.dumps({"rid": rid}))
            if self.ai_audio_logger:
                self.ai_audio_logger.mark_end(rid)
            text = "".join(self._ai_buf.pop(rid, []))
            if text.strip():
                #print("AI:", text.strip())
                self._dialog_buffer.append(f"AI: {text.strip()}")
                log_event("ai_response", source="realtime_api", value=text.strip())


        if typ == "response.cancelled":
            print("AI: <response cancelled>")
            # ideally: send conversation.item.truncate (https://platform.openai.com/docs/guides/realtime-conversations?lang=python)


        # Error Handling
        if typ == "error":
            dbg("ERROR", json.dumps(ev))
            log_event("api",source="realtime_api",value="error",extra=json.dumps(ev))
            if self.speech_visualizer:
                self.speech_visualizer.stop_speaking()

    def _on_error(self, ws, error):
        print("WebSocket error")
        log_event("api",source="websocket",value="ws_error",extra=str(error))

    def _on_close(self, _ws, code, reason):
        print("WebSocket closed", code, reason)
        log_event("api", source="websocket", value="ws_close", extra=json.dumps({"code": code, "reason": reason}))
        if self.speech_visualizer:
            self.speech_visualizer.stop_speaking()

    def say(self, text: str):
        prompt = "Say exactly the following: " + text

        event = {
            "type": "response.create",
            "response": {
                # empty input array removes all prior context
                "input": [],
                "instructions": prompt,
            },
        }

        self.ws.send(json.dumps(event))


    def run(self):
        # Initiate OpenAI WebSocket
        self.ws = websocket.WebSocketApp(
            URL,
            header=HEADERS,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        self.ws.run_forever(ping_interval=20, ping_timeout=10)


    