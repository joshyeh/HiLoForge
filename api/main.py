import os
import json
import shutil
from uuid import uuid4
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from redis import Redis
from rq import Queue
from rq.job import Job

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))

UPLOADS_DIR = DATA_DIR / "uploads"
OUTPUTS_DIR = DATA_DIR / "outputs"

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

redis_conn = Redis.from_url(REDIS_URL)
queue = Queue("scan2game", connection=redis_conn)

app = FastAPI(title="scan2game MVP")

ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class JobStatus(BaseModel):
    job_id: str
    output_id: Optional[str] = None
    status: str
    created_at: Optional[str] = None
    ended_at: Optional[str] = None
    result_path: Optional[str] = None
    error: Optional[str] = None
    meta: dict = Field(default_factory=dict)


def _safe_int(value: Optional[str], default: int) -> int:
    try:
        return int(value) if value is not None else default
    except Exception:
        return default


@app.get("/")
def root():
    return {
        "ok": True,
        "message": "scan2game MVP running",
        "endpoints": ["/jobs (POST)", "/jobs/{job_id} (GET)", "/jobs/{job_id}/download (GET)"],
    }


@app.post("/jobs")
async def create_job(
    file: UploadFile = File(...),
    target_tris: Optional[str] = Form(None),
    tex_size: Optional[str] = Form(None),
    ray_distance: Optional[str] = Form(None),
    island_margin: Optional[str] = Form(None),
    bake_margin: Optional[str] = Form(None),
    cage_extrusion: Optional[str] = Form(None),
    shrinkwrap_offset: Optional[str] = Form(None),
    remesh_voxel_size: Optional[str] = Form(None),
    auto_smooth_angle: Optional[str] = Form(None),
):
    """
    Upload a 3D asset:
      - .glb / .gltf recommended
      - .obj/.mtl/textures must be uploaded as .zip (Phase 1 - optional later)
      - .fbx optional later
    """
    ext = Path(file.filename).suffix.lower()
    if ext not in {".glb", ".gltf", ".fbx", ".zip", ".obj"}:
        raise HTTPException(status_code=400, detail="Unsupported file type. Use .glb/.gltf (recommended), .zip (OBJ bundle), or .fbx.")

    job_id = str(uuid4())
    job_upload_dir = UPLOADS_DIR / job_id
    job_output_dir = OUTPUTS_DIR / job_id
    job_upload_dir.mkdir(parents=True, exist_ok=True)
    job_output_dir.mkdir(parents=True, exist_ok=True)

    input_path = job_upload_dir / file.filename

    # Save upload
    with input_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    # Options (keep MVP tight)
    opts = {
        "job_id": job_id,
        "input_path": str(input_path),
        "output_dir": str(job_output_dir),
        "target_tris": _safe_int(target_tris, 5000),
        "tex_size": _safe_int(tex_size, 4096),
        "ray_distance": float(ray_distance) if ray_distance is not None else 0.02,
        "island_margin": float(island_margin) if island_margin is not None else 0.06,
        "bake_margin": _safe_int(bake_margin, 12),
        "cage_extrusion": float(cage_extrusion) if cage_extrusion is not None else 0.06,
        "shrinkwrap_offset": float(shrinkwrap_offset) if shrinkwrap_offset is not None else 0.0,
        "remesh_voxel_size": float(remesh_voxel_size) if remesh_voxel_size is not None else 0.0,
        "auto_smooth_angle": float(auto_smooth_angle) if auto_smooth_angle is not None else 0.0,
    }

    rq_job = queue.enqueue("worker.process_job", opts, job_timeout=60 * 30)  # 30 min
    return {"job_id": rq_job.id, "status": "queued", "output_id": job_id, "opts": opts}


@app.get("/jobs/{job_id}", response_model=JobStatus)
def get_job(job_id: str):
    try:
        job = Job.fetch(job_id, connection=redis_conn)
    except Exception:
        raise HTTPException(status_code=404, detail="Job not found")

    status = job.get_status()
    meta = dict(job.meta) if job.meta else {}

    result_path = meta.get("result_zip")
    error = None
    if job.is_failed:
        error = str(job.exc_info)[:2000] if job.exc_info else "Unknown error"

    return JobStatus(
        job_id=job.id,
        status=status,
        created_at=str(job.enqueued_at) if job.enqueued_at else None,
        ended_at=str(job.ended_at) if job.ended_at else None,
        result_path=result_path,
        error=error,
        meta=meta,
        output_id=meta.get("output_id") or meta.get("job_id"),
    )


@app.get("/jobs/{job_id}/download")
def download_result(job_id: str):
    try:
        job = Job.fetch(job_id, connection=redis_conn)
    except Exception:
        raise HTTPException(status_code=404, detail="Job not found")

    if not job.is_finished:
        raise HTTPException(status_code=400, detail="Job not finished yet")

    meta = dict(job.meta) if job.meta else {}
    result_zip = meta.get("result_zip")
    if not result_zip or not Path(result_zip).exists():
        raise HTTPException(status_code=404, detail="Result not found")

    return FileResponse(
        path=result_zip,
        filename=Path(result_zip).name,
        media_type="application/zip",
    )


@app.get("/jobs/{job_id}/preview/{which}")
def download_preview(job_id: str, which: str):
    if which not in {"before", "after"}:
        raise HTTPException(status_code=400, detail="Invalid preview type")

    preview_path = OUTPUTS_DIR / job_id / f"preview_{which}.png"
    if not preview_path.exists():
        raise HTTPException(status_code=404, detail="Preview not found")

    return FileResponse(
        path=preview_path,
        filename=preview_path.name,
        media_type="image/png",
    )


@app.get("/jobs/{job_id}/model")
def download_model(job_id: str):
    model_path = OUTPUTS_DIR / job_id / "model_low.glb"
    if not model_path.exists():
        # Allow passing the RQ job id; map to output_id if available.
        try:
            rq_job = Job.fetch(job_id, connection=redis_conn)
            meta = dict(rq_job.meta) if rq_job.meta else {}
            output_id = meta.get("output_id") or meta.get("job_id")
            if output_id:
                model_path = OUTPUTS_DIR / output_id / "model_low.glb"
        except Exception:
            pass
    if not model_path.exists():
        raise HTTPException(status_code=404, detail="Model not found")

    return FileResponse(
        path=model_path,
        filename=model_path.name,
        media_type="model/gltf-binary",
    )
