# Voice Clone

Self-hosted voice cloning (like ElevenLabs). Clone a voice from 10-60 seconds of audio, type text, get speech back as a WAV.

- `backend/` - FastAPI server (Chatterbox by default), usage metering and lifetime keys
- `lib/` - Flutter app (Android, iOS, Windows)
- `.github/workflows/build.yml` - builds and releases all three apps

## 1. Run the backend

Needs Python 3.11 and ffmpeg. An NVIDIA GPU is strongly recommended.

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

Docker (GPU): `docker build -t voice-clone backend && docker run --gpus all -p 8000:8000 -v vc-data:/data -e ADMIN_TOKEN=change-me voice-clone`

For public use, put it behind HTTPS (Caddy or nginx).

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `ENGINE` | `chatterbox` | `chatterbox` (MIT, commercial OK) or `xtts` (non-commercial only; install `coqui-tts` in a separate env) |
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

Keys are stored hashed; the plaintext is shown once. Back up `data/app.db`. The redeem box is hidden in the iOS app because Apple may reject license-key unlocks; sell unlimited access there through in-app purchase instead.

## 3. Build and release

Push a tag (`git tag v1.0.0 && git push --tags`) or run **Build and release** from the Actions tab.

**Repository variables** (Settings > Secrets and variables > Actions > Variables):
- `APP_ORG`: your reverse-domain, e.g. `com.yourname` (Play rejects `com.example`)
- `SERVER_URL`: your HTTPS server URL, baked into the apps as the default

**Windows -> GitHub Releases:** automatic on tag, no secrets needed.

**Android -> Google Play (internal track, draft)** secrets:
`ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`, `PLAY_SERVICE_ACCOUNT_JSON`.
Create the app in Play Console and upload the first build manually once; later builds upload automatically.

**iOS -> App Store Connect (TestFlight)** secrets:
`APPSTORE_KEY_ID`, `APPSTORE_ISSUER_ID`, `APPSTORE_KEY_P8`, `APPLE_TEAM_ID`.
Create the app record in App Store Connect first, using bundle ID `<APP_ORG>.voiceClone` (check the exact ID in the build log). Without these secrets the workflow builds an unsigned IPA for sideloading.

Without the Android secrets you still get an APK to sideload.

## Before you submit to the stores

- Add a privacy policy URL and an in-app way to delete voices and data.
- Both stores have rules for AI voice cloning and generated audio: keep the consent checkbox, disclose AI-generated content, and add a report/abuse contact.
- Selling unlimited access inside the apps must use Apple in-app purchase and Google Play Billing (not built yet).
- Chatterbox adds an inaudible watermark to generated audio. Check its current license and model terms before commercial use.

## Notes

- Free allowance is tracked per device ID created by the app, so a reinstall resets it and loses a redeemed key. Back up or re-grant with `/admin/grant`.
- Only clone voices you own or have permission to use.
