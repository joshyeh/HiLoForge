# HiLoForge

HiLoForge is a full-stack app that converts high-poly scans into game-ready low-poly assets.
It runs Blender headless in a worker, bakes base color and normal maps, and serves results through a FastAPI backend and a React frontend.

## Demo
### 1) Video Walkthrough

<p align="left">
  <a href="https://youtu.be/LP9zZ3jD4C0">
    <img src="public/exampleHome.png" alt="HiLoForge Demo" width="720" />
  </a>
</p>

### 2) App Flow (Home -> Compare)

Home UI

<img src="public/exampleHome.png" alt="exampleHome" width="720" />

Compare UI

<img src="public/examplePreview.png" alt="examplePreview" width="720" />

### 3) Example Result Quality

Before / After (Textures)

<table>
  <tr>
    <td><img src="public/beforeBoulder.png" alt="beforeBoulder" width="360" /></td>
    <td><img src="public/afterBoulder.png" alt="afterBoulder" width="360" /></td>
  </tr>
</table>

Before / After (Wireframe)

<table>
  <tr>
    <td><img src="public/beforeWireframe.png" alt="beforeWireframe" width="360" /></td>
    <td><img src="public/afterWireframe.png" alt="afterWireframe" width="360" /></td>
  </tr>
</table>

### 4) Example Metrics

- Input: 64,826 faces
- Output: ~5,000 faces
- Reduction: ~92%
- Output package: `model_low.glb` + baked textures + previews

## Repository Structure
```text
/
  api/                # FastAPI service
  worker/             # RQ worker + Blender script
  frontend/           # React + Tailwind UI
  data/               # Runtime data (uploads/outputs)
  examples/           # Example inputs/assets
  public/             # Demo assets for README
  docker-compose.yml  # Service orchestration
  README.md
```

## Features
- Uploads `.glb/.gltf/.fbx/.obj/.zip`
- Creates HIGH and LOW duplicates
- Decimates LOW to target triangle count
- Smart-UV unwrap for atlas baking
- Bakes base color and tangent-space normal maps
- Exports `model_low.glb` plus textures and previews
- Interactive 3D preview in app (home and compare pages)
- Local pre-upload preview for `.glb/.gltf` on home page

## Tech Stack
- Frontend: React + Vite + TypeScript + Tailwind CSS + Three.js (`@react-three/fiber`, `@react-three/drei`)
- API: FastAPI (Python)
- Worker: RQ + Blender (headless)
- Queue/Cache: Redis
- Web Server (frontend container): Nginx
- Containerization: Docker + Docker Compose

## API Endpoints
```text
POST /jobs
GET  /jobs/{job_id}
GET  /jobs/{job_id}/download
GET  /jobs/{job_id}/preview/before
GET  /jobs/{job_id}/preview/after
GET  /jobs/{job_id}/model
```

Notes:
- `/jobs/{job_id}/download` uses the RQ job id.
- Preview and model files are stored under output id (`/data/outputs/{output_id}`).
- `/jobs/{job_id}/model` accepts output id directly and also resolves from RQ job id when available.

## Run with Docker
```bash
docker compose up -d --build
```

Open:
- UI: `http://localhost:3000`
- API: `http://localhost:8000`

## Pipeline Parameters (UI -> Blender)
Core:
- Target Triangles: Decimate ratio (`target / current`)
- Texture Size: Bake image size
- Ray Distance: `Render > Bake > Max Ray Distance`
- UV Island Margin: Smart UV Project island margin
- Bake Margin (px): `Render > Bake > Margin`

Experimental:
- Cage Extrusion: `Render > Bake > Cage Extrusion` (requires cage)
- Shrinkwrap Offset: Shrinkwrap modifier offset on LOW
- Remesh Voxel Size: Voxel Remesh before decimation
- Auto Smooth Angle: Auto Smooth angle (0 disables)

## Output
Each job writes:
```text
/data/outputs/<output_id>/
  model_low.glb
  textures/atlas_basecolor.png
  textures/atlas_normal.png
  preview_before.png
  preview_after.png
  output.zip
  manifest.txt
  process.log
```

## Tips
- If base color is black, increase Ray Distance and/or Cage Extrusion.
- If the low mesh has holes, raise Target Triangles and keep Remesh Voxel Size at `0`.
- Increase Bake Margin and UV Island Margin to reduce texture seam artifacts.

## Notes
- GPU baking is supported when Docker has GPU access and Blender is configured for GPU.
- Some third-party viewers do not display GLB PBR materials correctly. Validate in Blender or the in-app viewer.
- Local in-app 3D preview (before processing) supports `.glb/.gltf` only. Uploaded `.fbx/.obj/.zip` files can still be processed, and their processed output is previewed as `model_low.glb`.

## Future Improvements
- Main Priority: Batch processing for multiple uploads
- Multi-resolution baking workflow
- Multi-LOD export (`LOD0/LOD1/LOD2`)
- Preset profiles per asset type
- Auto-retry heuristics for failed/black bakes
- Post-decimation artifact cleanup
