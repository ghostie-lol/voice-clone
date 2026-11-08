# Voice Clone

Self-hosted voice cloning (like ElevenLabs). Clone a voice from 10-60 seconds of audio, type text, get speech back as a WAV.

- `backend/` - FastAPI server (Chatterbox by default), usage metering and lifetime keys
- `lib/` - Flutter app (Android, iOS, Windows)
- `.github/workflows/build.yml` - builds the APK, EXE and IPA and publishes them to GitHub Releases

## 1. Run the backend

Needs Python 3.11 and ffmpeg. An NVIDIA GPU is strongly recommended.

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

Docker (GPU): `docker build -t voice-clone backend && docker run --gpus all -p 8000:8000 -v vc-data:/data -e ADMIN_TOKEN=change-me voice-clone`

For use outside your home network, put it behind HTTPS (Caddy or nginx).

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `ENGINE` | `chatterbox` | `chatterbox` (MIT license) or `xtts` (non-commercial only; install `coqui-tts` in a separate env) |
| `API_KEY` | none | Optional shared key sent as `X-API-Key` |
| `ADMIN_TOKEN` | none | Needed for `/admin/keys` and `/admin/grant` |
| `FREE_UNITS_PER_MONTH` | 300 | Free allowance per device (1 unit = 1 second of generation) |
| `HEAVY_RAM_GB` | 6 | A job peaking above this counts as heavy |
| `HEAVY_CPU_SECONDS` | 60 | A job using more CPU time than this counts as heavy |
| `HEAVY_MULTIPLIER` | 3 | Heavy jobs use up the allowance this many times faster |

## 2. Lifetime keys

Each key is single-use and unlocks unlimited access for the device that redeems it.

```bash
python licensing.py mint 10
# or over HTTP
curl -X POST https://your-server/admin/keys -H "X-Admin-Token: change-me" -H "Content-Type: application/json" -d '{"count": 10}'
```

Keys are stored hashed; the plaintext is shown once. Back up `data/app.db`.

## 3. Build and release (GitHub only, no app stores)

Push a tag (`git tag v1.0.0 && git push --tags`) or run **Build and release** from the Actions tab. A tag publishes everything to the repo's **Releases** page:

| File | Install |
|---|---|
| `VoiceClone-android.apk` | Open it on the phone and allow "install unknown apps" |
| `VoiceClone-windows.zip` | Unzip, run `voice_clone.exe` (SmartScreen may warn: More info > Run anyway) |
| `VoiceClone-ios-unsigned.ipa` | Install with AltStore or Sideloadly using a free Apple ID (re-sign every 7 days) |

**Repository variables** (Settings > Secrets and variables > Actions > Variables):
- `APP_ORG`: required reverse-domain application identifier, e.g. `com.yourname.voiceclone`. Do not leave it as `com.example`; all three platform builds stop with a clear error until this is set.
- `SERVER_URL`: your server URL, baked into the apps as the default

The workflow pins Flutter to `3.47.9` and upgrades the `record` and `share_plus` dependency trees during each build. Commit the generated `pubspec.lock` after running `flutter pub upgrade record share_plus` locally so future builds use a fixed dependency resolution.

**Android signing (recommended).** Without it, every build gets a different debug signature and users must uninstall before updating. Make one keystore, once, and add it as secrets:

```bash
keytool -genkey -v -keystore upload.jks -keyalg RSA -keysize 2048 -validity 10000 -alias upload
base64 -w0 upload.jks   # paste into the secret below
```

Secrets: `ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`. Keep a backup of `upload.jks`; if you lose it you can't ship updates.

## Notes

- Free allowance is tracked per device ID the app creates, so a reinstall resets it and loses a redeemed key. Re-grant with `/admin/grant`.
- Only clone voices you own or have permission to use.
- Chatterbox adds an inaudible watermark to generated audio. Check its current license before charging for anything.
