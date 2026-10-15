# Tube Forge AI

A full-stack starter for a video upload → transcription → highlight suggestions → editable clip → FFmpeg export workflow, branded as **Tube Forge AI**.

**Tagline:** Make every moment viral.

## Stack
- Next.js App Router + React + TypeScript + Tailwind
- FastAPI backend
- FFmpeg/ffprobe for media inspection and clip export
- `faster-whisper` for speech transcription when installed and configured
- SQLite/local media storage for development

> This is a starter project, not a fully production-hardened public service. It currently has no user authentication, per-user authorization, abuse protection, or durable job queue. Do not expose it to unrestricted public uploads until those controls and storage limits are implemented. YouTube URL scraping/download is not enabled; upload videos you own or are authorized to process.

## Run locally
1. Install FFmpeg and Python 3.11+.
2. Backend: `cd backend`, install `requirements.txt`, set values from `.env.example`, then run `uvicorn app.main:app --reload --port 8000`.
3. Frontend: `cd frontend`, run `npm install`, copy `.env.example` to `.env.local`, then `npm run dev`.
4. Open `http://localhost:3000`.

## Public deployment overview (Android browser is enough)

### Frontend — Vercel free tier
1. Push this project to a GitHub repository.
2. In Vercel, import the repository and set **Root Directory** to `frontend`.
3. Add environment variable `NEXT_PUBLIC_API_URL` with the public URL of your backend, e.g. `https://YOUR-BACKEND.onrender.com` (no trailing slash).
4. Deploy and copy the public `vercel.app` URL.

### Backend — Render free tier (best-effort demo only)
1. Create a Web Service from the same GitHub repository and set **Root Directory** to `backend`.
2. Choose Docker as the runtime if prompted. The included Dockerfile installs FFmpeg and uses the host-provided `PORT`.
3. Set `CORS_ORIGINS` to your exact Vercel URL.
4. Set `MAX_UPLOAD_MB=50`, `MAX_DURATION_SECONDS=600`, and `WHISPER_MODEL=tiny` for a small demo. Set `MEDIA_DIR=/tmp/tube-forge-media` and `DATABASE_URL=sqlite:////tmp/tube_forge.db` only for temporary tests.
5. Free instances may sleep, restart, have limited RAM/CPU, and use ephemeral storage. Local SQLite and uploaded files may disappear. Whisper/FFmpeg jobs may exceed free resource limits. Do not promise users permanent storage or unlimited free processing.
6. After changing `NEXT_PUBLIC_API_URL`, redeploy the frontend.

**Important about “free”:** the website can be published on free tiers, but reliable public video processing, persistent uploads, and AI transcription are not guaranteed to remain free. Provider quotas and free-tier rules can change. A public service also needs login, upload quotas, rate limiting, cleanup, and persistent storage before launch to everyone.

## Environment
See `backend/.env.example` and `frontend/.env.example`. Never put provider secrets in `NEXT_PUBLIC_*` variables.

## Production checklist
- [ ] Add authentication and per-user access checks.
- [ ] Add rate limits, upload size/duration quotas, and abuse prevention.
- [ ] Move uploads to private object storage and use durable database storage.
- [ ] Run transcription/rendering in a worker queue with job timeouts.
- [ ] Add cleanup, monitoring, backups, and privacy/terms pages.
- [ ] Test upload, transcription, export, and cross-origin requests on the deployed URLs.
