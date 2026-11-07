import json
import os
import subprocess
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

# XTTS-v2 is under the Coqui Public Model License (non-commercial use).
os.environ.setdefault("COQUI_TOS_AGREED", "1")

DATA = Path(os.getenv("DATA_DIR", "data"))
VOICES = DATA / "voices"
OUT = DATA / "out"
for d in (VOICES, OUT):
    d.mkdir(parents=True, exist_ok=True)

API_KEY = os.getenv("API_KEY", "")  # optional: set to require X-API-Key header

app = FastAPI(title="Voice Clone")
_tts = None


def tts():
    global _tts
    if _tts is None:
        import torch
        from TTS.api import TTS

        device = "cuda" if torch.cuda.is_available() else "cpu"
        _tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)
    return _tts


def auth(x_api_key: str = Header(default="")):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(401, "Invalid API key")


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/voices", dependencies=[Depends(auth)])
def voices():
    return [json.loads(p.read_text()) for p in sorted(VOICES.glob("*.json"))]


@app.post("/clone", dependencies=[Depends(auth)])
async def clone(
    name: str = Form(...),
    consent: bool = Form(...),
    file: UploadFile = File(...),
):
    if not consent:
        raise HTTPException(
            400, "You must confirm you own this voice or have the speaker's permission."
        )
    vid = uuid.uuid4().hex[:12]
    raw = VOICES / f"{vid}.upload"
    raw.write_bytes(await file.read())
    wav = VOICES / f"{vid}.wav"
    r = subprocess.run(
        ["ffmpeg", "-y", "-i", str(raw), "-ac", "1", "-ar", "22050", "-t", "60", str(wav)],
        capture_output=True,
    )
    raw.unlink(missing_ok=True)
    if r.returncode != 0:
        raise HTTPException(400, "Could not read that audio file.")
    (VOICES / f"{vid}.json").write_text(json.dumps({"id": vid, "name": name}))
    return {"id": vid, "name": name}


@app.delete("/voices/{voice_id}", dependencies=[Depends(auth)])
def delete_voice(voice_id: str):
    if not voice_id.isalnum():
        raise HTTPException(400, "Bad id")
    for ext in ("wav", "json"):
        (VOICES / f"{voice_id}.{ext}").unlink(missing_ok=True)
    return {"deleted": voice_id}


class Speak(BaseModel):
    voice_id: str
    text: str
    language: str = "en"


@app.post("/speak", dependencies=[Depends(auth)])
def speak(req: Speak):
    if not req.voice_id.isalnum():
        raise HTTPException(400, "Bad id")
    wav = VOICES / f"{req.voice_id}.wav"
    if not wav.exists():
        raise HTTPException(404, "Voice not found")
    if not req.text.strip() or len(req.text) > 2000:
        raise HTTPException(400, "Text must be 1-2000 characters")
    out = OUT / f"{uuid.uuid4().hex}.wav"
    tts().tts_to_file(
        text=req.text, speaker_wav=str(wav), language=req.language, file_path=str(out)
    )
    return FileResponse(out, media_type="audio/wav", filename="speech.wav")
