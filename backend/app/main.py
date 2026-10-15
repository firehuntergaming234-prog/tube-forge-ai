from __future__ import annotations
import json, os, shutil, subprocess, uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
from sqlalchemy import create_engine, String, Text, Float, Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "sqlite:///./tube_forge.db"
    media_dir: str = "./private_media"
    max_upload_mb: int = 1024
    max_duration_seconds: int = 14400
    cors_origins: str = "http://localhost:3000"
    whisper_model: str = "small"
    highlight_provider_url: str = ""
    class Config:
        env_file = ".env"

cfg = Settings()
MEDIA = Path(cfg.media_dir).resolve()
MEDIA.mkdir(parents=True, exist_ok=True)
engine = create_engine(cfg.database_url, connect_args={"check_same_thread": False} if cfg.database_url.startswith("sqlite") else {})
Session = sessionmaker(bind=engine, expire_on_commit=False)

class Base(DeclarativeBase): pass
class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    filename: Mapped[str] = mapped_column(String)
    source_path: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="uploaded")
    duration: Mapped[float] = mapped_column(Float, default=0)
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    fps: Mapped[str] = mapped_column(String, default="unknown")
    transcript_json: Mapped[str] = mapped_column(Text, default="[]")
    clips_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[str] = mapped_column(String, default=lambda: datetime.now(timezone.utc).isoformat())
Base.metadata.create_all(engine)

app = FastAPI(title="Tube Forge AI API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=[x.strip() for x in cfg.cors_origins.split(",")], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

def run(cmd: list[str]) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError((p.stderr or p.stdout or "Command failed")[-2000:])
    return p.stdout

def inspect_media(path: str) -> dict:
    raw = run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path])
    data = json.loads(raw)
    v = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if not v: raise ValueError("The uploaded file has no video stream.")
    duration = float(data.get("format", {}).get("duration", 0))
    fps = v.get("avg_frame_rate", "0/1")
    return {"duration": duration, "width": int(v.get("width", 0)), "height": int(v.get("height", 0)), "fps": fps}

@app.get("/api/health")
def health(): return {"ok": True, "service": "tube-forge-api"}

@app.post("/api/upload")
async def upload(background: BackgroundTasks, file: UploadFile = File(...)):
    allowed = {".mp4", ".mov", ".webm", ".m4v"}
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in allowed: raise HTTPException(415, "Unsupported format. Upload MP4, MOV, WebM, or M4V.")
    job_id = str(uuid.uuid4())
    folder = MEDIA / job_id
    folder.mkdir(parents=True, exist_ok=False)
    target = folder / ("source" + suffix)
    limit = cfg.max_upload_mb * 1024 * 1024
    size = 0
    try:
        with target.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > limit: raise HTTPException(413, f"File exceeds the {cfg.max_upload_mb} MB limit.")
                out.write(chunk)
        meta = inspect_media(str(target))
        if meta["duration"] <= 0: raise ValueError("Could not determine video duration.")
        if meta["duration"] > cfg.max_duration_seconds: raise HTTPException(413, "Video exceeds the configured duration limit.")
        with Session() as db:
            item = Job(id=job_id, filename=Path(file.filename or "video").name, source_path=str(target), status="uploaded",
                       duration=meta["duration"], width=meta["width"], height=meta["height"], fps=meta["fps"])
            db.add(item); db.commit()
        return {"id": job_id, "filename": item.filename, "status": item.status, **meta}
    except HTTPException:
        shutil.rmtree(folder, ignore_errors=True); raise
    except Exception as e:
        shutil.rmtree(folder, ignore_errors=True)
        raise HTTPException(422, f"Unable to read this video. Check the file and FFmpeg installation. Details: {str(e)[:300]}")

@app.get("/api/jobs")
def list_jobs():
    with Session() as db:
        items = db.query(Job).order_by(Job.created_at.desc()).limit(100).all()
        return [job_out(x) for x in items]

def job_out(x):
    return {"id":x.id,"filename":x.filename,"status":x.status,"duration":x.duration,"width":x.width,"height":x.height,"fps":x.fps,"created_at":x.created_at,
            "transcript":json.loads(x.transcript_json),"clips":json.loads(x.clips_json)}

@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    with Session() as db:
        x = db.get(Job, job_id)
        if not x: raise HTTPException(404, "Project not found.")
        return job_out(x)

@app.get("/api/jobs/{job_id}/source")
def source(job_id: str):
    with Session() as db: x = db.get(Job, job_id)
    if not x: raise HTTPException(404, "Project not found.")
    return FileResponse(x.source_path, media_type="video/mp4", filename=x.filename)

@app.post("/api/jobs/{job_id}/transcribe")
def transcribe(job_id: str):
    with Session() as db:
        x = db.get(Job, job_id)
        if not x: raise HTTPException(404, "Project not found.")
        x.status = "transcribing"; db.commit()
        source_path = x.source_path
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel(cfg.whisper_model, device="cpu", compute_type="int8")
        segments, info = model.transcribe(source_path, word_timestamps=True, vad_filter=True)
        rows = []
        for seg in segments:
            words = []
            for w in (seg.words or []):
                words.append({"start":round(w.start,3),"end":round(w.end,3),"text":w.word})
            rows.append({"start":round(seg.start,3),"end":round(seg.end,3),"text":seg.text.strip(),"words":words})
        with Session() as db:
            x = db.get(Job, job_id); x.transcript_json=json.dumps(rows); x.status="transcribed"; db.commit()
        return {"status":"transcribed","language":info.language,"segments":rows}
    except Exception as e:
        with Session() as db:
            x=db.get(Job,job_id)
            if x: x.status="transcription_failed"; db.commit()
        raise HTTPException(503, f"Transcription is not configured or failed. Install faster-whisper/model dependencies and retry. {str(e)[:250]}")

class SuggestRequest(BaseModel):
    count: int = Field(default=5, ge=1, le=20)
    min_seconds: int = Field(default=15, ge=5, le=180)
    max_seconds: int = Field(default=60, ge=10, le=300)
class ExportRequest(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    aspect: str = "9:16"
    resolution: int = 1080
    caption_text: Optional[str] = None
    caption_srt: Optional[str] = None

@app.post("/api/jobs/{job_id}/suggest")
def suggest(job_id: str, req: SuggestRequest):
    with Session() as db:
        x=db.get(Job,job_id)
        if not x: raise HTTPException(404,"Project not found.")
        transcript=json.loads(x.transcript_json)
        duration=x.duration
    if not transcript: raise HTTPException(409,"Transcribe this video before generating highlight suggestions.")
    # Candidate windows are formed from real transcript segments and sentence boundaries.
    sentences=[]
    for s in transcript:
        text=s["text"].strip()
        if not text: continue
        sentences.append({"start":s["start"],"end":s["end"],"text":text})
    candidates=[]
    for i, seg in enumerate(sentences):
        start=seg["start"]; end=seg["end"]; texts=[seg["text"]]
        if req.min_seconds <= end-start <= req.max_seconds:
            pass
        else:
            j=i+1
            while j < len(sentences) and sentences[j]["end"]-start <= req.max_seconds:
                end=sentences[j]["end"]; texts.append(sentences[j]["text"])
                if end-start >= req.min_seconds and (texts[-1].endswith((".", "!", "?", "۔")) or end-start >= req.max_seconds*.8):
                    break
                j+=1
        dur=end-start
        if req.min_seconds <= dur <= req.max_seconds:
            txt=" ".join(texts)
            # Heuristic estimate only; no claim of guaranteed engagement.
            hooks=sum(1 for term in ["why","how","secret","mistake","important","because","imagine","problem","question"] if term in txt.lower())
            score=min(96, 52 + hooks*6 + (8 if "?" in txt else 0) + (5 if len(txt.split()) > 24 else 0))
            if not any(abs(c["start"]-start)<req.min_seconds*.6 for c in candidates):
                candidates.append({"id":str(uuid.uuid4()),"start":round(start,2),"end":round(end,2),"duration":round(dur,2),"transcript":txt,"score":score,"score_label":"Estimated engagement potential","reason":"Self-contained transcript segment with a clear sentence boundary."})
    candidates=sorted(candidates,key=lambda c:c["score"],reverse=True)[:req.count]
    candidates=sorted(candidates,key=lambda c:c["start"])
    with Session() as db:
        x=db.get(Job,job_id); x.clips_json=json.dumps(candidates); x.status="clips_ready"; db.commit()
    return {"clips":candidates,"note":"Scores are heuristic estimates, not predictions of actual performance."}

@app.post("/api/jobs/{job_id}/export")
def export_clip(job_id: str, req: ExportRequest):
    with Session() as db: x=db.get(Job,job_id)
    if not x: raise HTTPException(404,"Project not found.")
    if req.end <= req.start or req.end > x.duration + .25: raise HTTPException(422,"Clip timestamps are outside the source video.")
    if req.aspect not in {"9:16","16:9","1:1"}: raise HTTPException(422,"Unsupported aspect ratio.")
    if req.resolution not in {720,1080,1440,2160}: raise HTTPException(422,"Unsupported resolution.")
    out = str((Path(x.source_path).parent / f"clip-{uuid.uuid4().hex[:8]}.mp4"))
    w,h={"9:16":(req.resolution*9//16,req.resolution),"16:9":(req.resolution,req.resolution*9//16),"1:1":(req.resolution,req.resolution)}[req.aspect]
    # Scale to fill, then center crop. For advanced subject tracking, UI can use manual positioning in a later worker integration.
    vf=f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1"
    srt_path = None
    if req.caption_srt:
        srt_path = Path(x.source_path).parent / f"captions-{uuid.uuid4().hex[:8]}.srt"
        srt_path.write_text(req.caption_srt, encoding="utf-8")
        escaped_srt = str(srt_path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        vf += f",subtitles='{escaped_srt}'"
    cmd=["ffmpeg","-y","-ss",str(req.start),"-i",x.source_path,"-t",str(req.end-req.start),"-vf",vf,"-c:v","libx264","-preset","veryfast","-crf","20","-c:a","aac","-b:a","192k","-movflags","+faststart",out]
    try: run(cmd)
    except Exception as e: raise HTTPException(500,f"FFmpeg render failed: {str(e)[:400]}")
    return {"status":"completed","download_url":f"/api/download/{Path(out).name}","filename":Path(out).name}

@app.get("/api/download/{filename}")
def download(filename: str):
    # Prevent path traversal: only files directly inside configured job folders and matching clip prefix.
    if not filename.startswith("clip-") or "/" in filename or "\\" in filename: raise HTTPException(400,"Invalid filename.")
    for folder in MEDIA.iterdir():
        candidate=folder/filename
        if folder.is_dir() and candidate.is_file():
            return FileResponse(candidate,media_type="video/mp4",filename=filename)
    raise HTTPException(404,"Export not found.")
