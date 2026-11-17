# -*- coding: utf-8 -*-
"""
YouTube Downloader API - yt-dlp only (no cookies, no proxy)

Endpoints:
  GET /mp3?url=<youtube-link>              -> MP3 download
  GET /video?url=<youtube-link>&quality=720 -> Video download (best up to quality, default best)
  GET /qualities?url=<youtube-link>        -> OTTA requestil ella qualitykum ulla DOWNLOAD LINKS response aayi kittum

Run:
  uvicorn main:app --host 0.0.0.0 --port 8000
"""

import os
import shutil
import tempfile
import uuid
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
import yt_dlp

app = FastAPI(title="YouTube Downloader API", version="1.1")

DOWNLOAD_DIR = tempfile.mkdtemp(prefix="ytdl_")


def _cleanup(path: str):
    shutil.rmtree(path, ignore_errors=True) if os.path.isdir(path) else (
        os.path.exists(path) and os.remove(path)
    )


def _safe_name(title: str) -> str:
    for ch in '<>:"/\\|?*':
        title = title.replace(ch, "_")
    return title.strip()[:120] or "video"


def _base_url(request: Request) -> str:
    """API-nte base URL (public deploy cheyyumbol X-Forwarded settings venam)."""
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.headers.get("host"))
    return f"{proto}://{host}"


# ---------------- 1) MP3 ----------------
@app.get("/mp3")
def download_mp3(url: str = Query(..., description="YouTube video link")):
    task_id = str(uuid.uuid4())[:8]
    outtmpl = os.path.join(DOWNLOAD_DIR, f"{task_id}_audio.%(ext)s")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
        "quiet": True,
        "noplaylist": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info).rsplit(".", 1)[0] + ".mp3"
        if not os.path.exists(filename):
            raise FileNotFoundError("MP3 conversion failed (ffmpeg check cheyyuka)")
        return FileResponse(
            filename,
            media_type="audio/mpeg",
            filename=f"{_safe_name(info.get('title', 'audio'))}.mp3",
            background=lambda: _cleanup(filename),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"MP3 download failed: {e}")


# ---------------- 2) Video (single quality) ----------------
@app.get("/video")
def download_video(
    url: str = Query(..., description="YouTube video link"),
    quality: str = Query("best", description="e.g. 1080, 720, 480, 360 or 'best'"),
):
    task_id = str(uuid.uuid4())[:8]
    outtmpl = os.path.join(DOWNLOAD_DIR, f"{task_id}_video.%(ext)s")

    if quality == "best":
        fmt = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
    else:
        fmt = (
            f"bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/"
            f"best[height<={quality}][ext=mp4]/best[height<={quality}]/best"
        )

    ydl_opts = {
        "format": fmt,
        "outtmpl": outtmpl,
        "merge_output_format": "mp4",
        "quiet": True,
        "noplaylist": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info).rsplit(".", 1)[0] + ".mp4"
        if not os.path.exists(filename):
            raise FileNotFoundError("Video download failed")
        return FileResponse(
            filename,
            media_type="video/mp4",
            filename=f"{_safe_name(info.get('title', 'video'))}.mp4",
            background=lambda: _cleanup(filename),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Video download failed: {e}")


# ---------------- 3) OTTA requestil ella qualitykum ulla DOWNLOAD LINKS ----------------
@app.get("/qualities")
def list_qualities(url: str = Query(..., description="YouTube video link"),
                   request: Request = None):
    """Otta requestil: available ella qualitykalum + mp3, ellaam
    download cheyyaan pattunna link-ukal JSON response aayi kittum."""
    ydl_opts = {"quiet": True, "noplaylist": True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Info fetch failed: {e}")

    base = _base_url(request) if request else ""
    encoded_url = quote(url, safe="")

    seen, qualities = set(), []
    for f in info.get("formats", []):
        if f.get("vcodec") == "none":
            continue
        h = f.get("height")
        if h and h not in seen:
            seen.add(h)
            qualities.append({
                "quality": f"{h}p",
                "height": h,
                "ext": f.get("ext"),
                "download_url": f"{base}/video?url={encoded_url}&quality={h}",
            })
    qualities.sort(key=lambda q: -q["height"])

    return JSONResponse({
        "title": info.get("title"),
        "duration_seconds": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
        "downloads": {
            "mp3": f"{base}/mp3?url={encoded_url}",
            "best_video": f"{base}/video?url={encoded_url}&quality=best",
            "all_qualities": [
                {"quality": q["quality"], "download_url": q["download_url"]}
                for q in qualities
            ],
        },
    })


@app.get("/")
def health():
    return {"status": "ok", "endpoints": ["/mp3?url=", "/video?url=&quality=", "/qualities?url="]}
