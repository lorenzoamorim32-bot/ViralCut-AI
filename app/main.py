import os, re, uuid, shutil, subprocess
from pathlib import Path
from typing import List
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, HttpUrl
from yt_dlp import YoutubeDL

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
JOBS = {}

app = FastAPI(title="ViralCut AI")
app.mount("/static", StaticFiles(directory=ROOT / "app" / "static"), name="static")

class URLRequest(BaseModel):
    url: HttpUrl

class ReviewRequest(BaseModel):
    selected_ids: List[str]

def valid_youtube_url(url: str) -> bool:
    return bool(re.match(r"^https?://(www\.)?(youtube\.com|youtu\.be)/", url, re.I))

def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout or "Falha no processamento")[-2500:])
    return p.stdout

def download_youtube(url: str, folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    opts = {
        "format": "best[ext=mp4]/best",
        "outtmpl": str(folder / "source.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "max_filesize": 2 * 1024 * 1024 * 1024,
    }
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            path = Path(ydl.prepare_filename(info))
    except Exception as e:
        raise RuntimeError(f"Não foi possível obter o vídeo do YouTube: {e}")
    if not path.exists():
        candidates = list(folder.glob("source.*"))
        if not candidates:
            raise RuntimeError("O download não gerou um arquivo de vídeo.")
        path = candidates[0]
    return path

def duration_seconds(video: Path) -> float:
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "default=noprint_wrappers=1:nokey=1", str(video)])
    return float(out.strip())

def transcribe(video: Path):
    from faster_whisper import WhisperModel
    model_name = os.getenv("WHISPER_MODEL", "base")
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(str(video), vad_filter=True)
    return [{"start": float(s.start), "end": float(s.end), "text": s.text.strip()}
            for s in segments if s.text.strip()]

def make_candidates(segments, duration):
    if not segments:
        return []
    # Heurística inicial: prioriza trechos com fala e frases mais expressivas.
    markers = ["porque", "olha", "nunca", "melhor", "pior", "incrível", "sério",
               "aconteceu", "ninguém", "descobri", "segredo", "absurdo", "finalmente"]
    windows = []
    for s in segments:
        start = max(0, s["start"] - 5)
        end = min(duration, max(s["end"] + 12, start + 25))
        if end - start < 12:
            continue
        text = " ".join(x["text"] for x in segments
                        if x["start"] < end and x["end"] > start)
        if len(text.split()) < 12:
            continue
        score = min(99, 35 + min(len(text.split()), 50) + sum(m in text.lower() for m in markers) * 4)
        windows.append({"start": round(start, 2), "end": round(end, 2),
                        "text": text[:450], "score": score})
    windows.sort(key=lambda x: x["score"], reverse=True)
    chosen = []
    for w in windows:
        if all(abs(w["start"] - x["start"]) > 18 for x in chosen):
            chosen.append(w)
        if len(chosen) >= 12:
            break
    chosen.sort(key=lambda x: x["start"])
    return [{"id": str(i+1), **w} for i, w in enumerate(chosen)]

@app.get("/")
def home():
    return FileResponse(ROOT / "app" / "static" / "index.html")

@app.post("/api/analyze-url")
def analyze_url(req: URLRequest, background_tasks: BackgroundTasks):
    url = str(req.url)
    if not valid_youtube_url(url):
        raise HTTPException(400, "Cole um link válido do YouTube.")
    job_id = uuid.uuid4().hex[:12]
    folder = DATA / job_id
    JOBS[job_id] = {"status": "processing", "message": "Obtendo vídeo do YouTube...", "clips": []}
    background_tasks.add_task(process_job, job_id, url, folder)
    return {"job_id": job_id}

def process_job(job_id, url, folder):
    try:
        video = download_youtube(url, folder)
        JOBS[job_id]["message"] = "Transcrevendo e analisando o vídeo..."
        dur = duration_seconds(video)
        segments = transcribe(video)
        clips = make_candidates(segments, dur)
        JOBS[job_id].update({"status": "ready", "message": "Análise concluída.", "clips": clips,
                             "video": str(video), "folder": str(folder)})
    except Exception as e:
        JOBS[job_id].update({"status": "error", "message": str(e)})

@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "Análise não encontrada.")
    return {k: v for k, v in job.items() if k not in ("video", "folder")}

@app.post("/api/jobs/{job_id}/export")
def export_clips(job_id: str, req: ReviewRequest):
    job = JOBS.get(job_id)
    if not job or job.get("status") != "ready":
        raise HTTPException(400, "A análise ainda não está pronta.")
    selected = [c for c in job["clips"] if c["id"] in req.selected_ids]
    if not selected:
        raise HTTPException(400, "Selecione pelo menos um corte.")
    outdir = Path(job["folder"]) / "exports"
    outdir.mkdir(exist_ok=True)
    exported = []
    for i, clip in enumerate(selected, 1):
        out = outdir / f"corte_{i:02d}.mp4"
        start, length = clip["start"], clip["end"] - clip["start"]
        # Recorte central vertical 9:16; não faz rastreamento automático de rosto.
        run(["ffmpeg", "-y", "-ss", str(start), "-i", job["video"], "-t", str(length),
             "-vf", "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
             "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out)])
        exported.append(out)
    zip_path = outdir / "ViralCut_cortes.zip"
    import zipfile
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in exported:
            z.write(p, p.name)
    return {"download_url": f"/api/jobs/{job_id}/download"}

@app.get("/api/jobs/{job_id}/download")
def download_export(job_id: str):
    path = DATA / job_id / "exports" / "ViralCut_cortes.zip"
    if not path.exists():
        raise HTTPException(404, "Exporte os cortes primeiro.")
    return FileResponse(path, filename="ViralCut_cortes.zip", media_type="application/zip")

@app.get("/health")
def health():
    return {"ok": True}
