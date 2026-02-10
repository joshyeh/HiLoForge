import os
import json
import subprocess
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from redis import Redis
from rq import Worker, Queue, Connection

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))

listen = ["scan2game"]
redis_conn = Redis.from_url(REDIS_URL)


def process_job(opts: dict):
    """
    RQ job entrypoint.
    Runs Blender headless to process a single input model.
    """
    input_path = Path(opts["input_path"])
    output_dir = Path(opts["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    target_tris = int(opts.get("target_tris", 5000))
    tex_size = int(opts.get("tex_size", 4096))
    ray_distance = float(opts.get("ray_distance", 0.02))
    island_margin = float(opts.get("island_margin", 0.06))
    bake_margin = int(opts.get("bake_margin", 12))
    cage_extrusion = float(opts.get("cage_extrusion", 0.06))
    shrinkwrap_offset = float(opts.get("shrinkwrap_offset", 0.0))
    remesh_voxel_size = float(opts.get("remesh_voxel_size", 0.0))
    auto_smooth_angle = float(opts.get("auto_smooth_angle", 0.0))

    # If user uploaded a zip/obj bundle, you'd unzip here (Phase 1+).
    # MVP: assume input_path is a GLB/GLTF (or FBX/OBJ if you want).
    blender_cmd = [
        "blender",
        "-b",
        "-P",
        "/app/blender_process.py",
        "--",
        "--input",
        str(input_path),
        "--output_dir",
        str(output_dir),
        "--target_tris",
        str(target_tris),
        "--tex_size",
        str(tex_size),
        "--ray_distance",
        str(ray_distance),
        "--island_margin",
        str(island_margin),
        "--bake_margin",
        str(bake_margin),
        "--cage_extrusion",
        str(cage_extrusion),
        "--shrinkwrap_offset",
        str(shrinkwrap_offset),
        "--remesh_voxel_size",
        str(remesh_voxel_size),
        "--auto_smooth_angle",
        str(auto_smooth_angle),
    ]

    # Run Blender
    proc = subprocess.run(
        blender_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(output_dir),
    )

    log_path = output_dir / "process.log"
    log_path.write_text(proc.stdout)

    if proc.returncode != 0:
        raise RuntimeError(f"Blender failed. See log at {log_path}")

    # Zip outputs
    zip_path = output_dir / "output.zip"
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as z:
        for p in output_dir.rglob("*"):
            if p.is_file() and p.name != "output.zip":
                z.write(p, arcname=str(p.relative_to(output_dir)))

    # Store result path in job meta
    # RQ provides get_current_job() inside the worker process
    from rq import get_current_job
    job = get_current_job()
    job.meta["result_zip"] = str(zip_path)
    job.meta["log_path"] = str(log_path)
    job.meta["preview_before"] = str(output_dir / "preview_before.png")
    job.meta["preview_after"] = str(output_dir / "preview_after.png")
    job.meta["output_id"] = opts.get("job_id")
    job.save_meta()

    return {"result_zip": str(zip_path), "job_id": opts.get("job_id")}


if __name__ == "__main__":
    with Connection(redis_conn):
        worker = Worker(map(Queue, listen))
        worker.work()
