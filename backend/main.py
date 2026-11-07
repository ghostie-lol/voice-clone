import json
import os
import subprocess
import threading
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

import licensing

# ENGINE=chatterbox (default, MIT license, OK for commercial use)
# ENGINE=xtts       (Coqui XTTS-v2, NON-COMMERCIAL license: personal use only)
ENGINE = os.getenv("ENGINE", "chatterbox")
if ENGINE == "xtts":
    os.environ.setdefault("COQUI_TOS_AGREED", "1")

DATA = Path(os.getenv("DATA_DIR", "data"))
VOICES = DATA / "voices"
OUT = DATA / "out"
for d in (VOICES, OUT):
    d.mkdir(parents=True, exist_ok=True)

API_KEY = os.getenv("API_KEY", "")  # optional: require X-API-Key on every call
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")  # required to mint lifetime keys over HTTP

CHATTERBOX_LANGS = {
    "ar", "da", "de", "el", "en", "es", "fi", "fr", "he", "hi", "it", "ja",
    "ko", "ms", "nl", "no", "pl", "pt", "ru", "sv", "sw", "tr", "zh",
}

app = FastAPI(title="Voice Clone")
_model = None
_gen_lock = threading.Lock()  # one generation at a time (also keeps metering accurate)


def model():
    global _model
    if _model is None:
        import torch

        device = "cuda" if torch.cuda.is_available() else "cpu"
        if ENGINE == "xtts":
            from TTS.api import TTS

            _model = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)
        else:
            from chatterbox.mtl_tts import ChatterboxMultilingualTTS

            _model = ChatterboxMultilingualTTS.from_pretrained(device=device)
    return _model


def synth(text: str, ref: Path, lang: str, out: Path):
    m = model()
    if ENGINE == "xtts":
        m.tts_to_file(
            text=text,
            speaker_wav=str(ref),
            language="zh-cn" if lang == "zh" else lang,
            file_path=str(out),
        )
    else:
        if lang not in CHATTERBOX_LANGS:
            raise HTTPException(400, f"Language '{lang}' is not supported")
        import torchaudio as ta

        wav = m.generate(text, language_id=lang, audio_prompt_path=str(ref))
        ta.save(str(out), wav, m.sr)


def auth(x_api_key: str = Header(default="")):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(401, "Invalid API key")


def device_id(x_device_id: str = Header(default="")) -> str:
    if not licensing.DEVICE_RE.match(x_device_id):
        raise HTTPException(400, "Missing or invalid X-Device-Id")
    licensing.ensure_device(x_device_id)
    return x_device_id


@app.get("/health")
def health():
    return {"ok": True, "engine": ENGINE}


@app.get("/status", dependencies=[Depends(auth)])
def status(dev: str = Depends(device_id)):
    return licensing.status(dev)


class Redeem(BaseModel):
    code: str


@app.post("/redeem", dependencies=[Depends(auth)])
def redeem(req: Redeem, dev: str = Depends(device_id)):
    if not licensing.redeem(req.code, dev):
        raise HTTPException(400, "Invalid or already used key")
    return licensing.status(dev)


class Mint(BaseModel):
    count: int = 1


@app.post("/admin/keys")
def admin_mint(req: Mint, x_admin_token: str = Header(default="")):
    if not ADMIN_TOKEN or x_admin_token != ADMIN_TOKEN:
        raise HTTPException(401, "Unauthorized")
    return {"keys": licensing.mint(max(1, min(req.count, 500)))}


class Grant(BaseModel):
    device_id: str


@app.post("/admin/grant")
def admin_grant(req: Grant, x_admin_token: str = Header(default="")):
    if not ADMIN_TOKEN or x_admin_token != ADMIN_TOKEN:
        raise HTTPException(401, "Unauthorized")
    if not licensing.DEVICE_RE.match(req.device_id):
        raise HTTPException(400, "Bad device id")
    licensing.grant(req.device_id)
    return {"granted": req.device_id}


@app.get("/voices", dependencies=[Depends(auth)])
def voices():
    return [json.loads(p.read_text()) for p in sorted(VOICES.glob("*.json"))]


@app.post("/clone", dependencies=[Depends(auth), Depends(device_id)])
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
        ["ffmpeg", "-y", "-i", str(raw), "-ac", "1", "-ar", "24000", "-t", "60", str(wav)],
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
def speak(req: Speak, dev: str = Depends(device_id)):
    if not req.voice_id.isalnum():
        raise HTTPException(400, "Bad id")
    wav = VOICES / f"{req.voice_id}.wav"
    if not wav.exists():
        raise HTTPException(404, "Voice not found")
    if not req.text.strip() or len(req.text) > 2000:
        raise HTTPException(400, "Text must be 1-2000 characters")
    if licensing.status(dev)["exhausted"]:
        raise HTTPException(
            402, "Free monthly allowance used up. Enter a lifetime key or upgrade."
        )
    out = OUT / f"{uuid.uuid4().hex}.wav"
    with _gen_lock:
        with licensing.Meter() as meter:
            synth(req.text, wav, req.language, out)
    meter.record(dev)
    return FileResponse(out, media_type="audio/wav", filename="speech.wav")
