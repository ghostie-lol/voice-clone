# Voice Clone

Free, self-hosted voice cloning (like ElevenLabs) using open-source **XTTS-v2**.
Clone a voice from 10-60 seconds of audio, then turn text into speech in 16 languages and save the WAV.

- `backend/` - FastAPI server running XTTS-v2
- `lib/` - Flutter app (Android, iOS, Windows)
- `.github/workflows/build.yml` - builds the APK, EXE and unsigned IPA

## 1. Run the backend

Needs Python 3.10-3.11 and ffmpeg. An NVIDIA GPU makes it fast; CPU works but is slow.

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

Or with Docker (GPU): `docker build -t voice-clone backend && docker run --gpus all -p 8000:8000 -v vc-data:/data voice-clone`

The first request downloads the model (about 2 GB). Optional: set `API_KEY=yourkey` to require an `X-API-Key` header.

## 2. Get the apps

Open the **Actions** tab, run **Build apps**, and download the artifacts:

| Artifact | Install |
|---|---|
| `VoiceClone-android-apk` | Copy the APK to your phone and install |
| `VoiceClone-windows-exe` | Unzip, run `voice_clone.exe` |
| `VoiceClone-ios-unsigned-ipa` | Unsigned: sideload with AltStore or Sideloadly (free Apple ID, re-sign every 7 days), or sign with a paid Apple Developer account |

In the app, open **Settings** and enter your server URL, e.g. `http://192.168.1.20:8000` (your PC's LAN IP; phone and PC on the same Wi-Fi). Android emulator: `http://10.0.2.2:8000`.

## Notes

- XTTS-v2 is licensed for **non-commercial use** (Coqui Public Model License).
- Only clone voices you own or have permission to use. The app and API require a consent confirmation.
- The server has no HTTPS. Keep it on your LAN, or put it behind a reverse proxy or VPN if exposed.
