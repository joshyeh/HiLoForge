import { Component, type ReactNode, Suspense, useEffect, useMemo, useState } from "react";
import { Canvas } from "@react-three/fiber";
import { Environment, OrbitControls, useGLTF } from "@react-three/drei";

type JobStatus = {
  job_id: string;
  status: string;
  created_at?: string | null;
  ended_at?: string | null;
  result_path?: string | null;
  error?: string | null;
  output_id?: string | null;
};

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

function getHashRoute() {
  const hash = window.location.hash || "#/";
  const [path, query = ""] = hash.replace(/^#/, "").split("?");
  const params = new URLSearchParams(query);
  return { path, params };
}


function ModelScene({ url }: { url: string }) {
  const { scene } = useGLTF(url);
  return <primitive object={scene} />;
}

type ViewerErrorBoundaryProps = {
  fallback: ReactNode;
  children?: ReactNode;
};

class ViewerErrorBoundary extends Component<
  ViewerErrorBoundaryProps,
  { hasError: boolean }
> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback;
    }
    return this.props.children;
  }
}

function ModelViewer({ url }: { url: string }) {
  return (
    <Canvas camera={{ position: [0, 1.6, 3.2], fov: 45 }}>
      <ambientLight intensity={0.4} />
      <directionalLight position={[4, 6, 3]} intensity={1.1} />
      <Suspense fallback={null}>
        <ModelScene url={url} />
        <Environment preset="city" />
      </Suspense>
      <OrbitControls makeDefault enableDamping />
    </Canvas>
  );
}
async function fetchStatus(jobId: string): Promise<JobStatus> {
  const res = await fetch(`${API_BASE}/jobs/${jobId}`);
  if (!res.ok) {
    throw new Error(`Status request failed: ${res.status}`);
  }
  return res.json();
}

export default function App() {
  const [jobId, setJobId] = useState<string | null>(null);
  const [rqJobId, setRqJobId] = useState<string | null>(null);
  const [status, setStatus] = useState("Idle");
  const [queuedAt, setQueuedAt] = useState<string>("—");
  const [endedAt, setEndedAt] = useState<string>("—");
  const [error, setError] = useState<string>("");
  const [polling, setPolling] = useState(false);
  const [route, setRoute] = useState(() => getHashRoute());
  const [selectedFile, setSelectedFile] = useState<string>("No file selected");
  const [fileInputKey, setFileInputKey] = useState(0);
  const [localModelUrl, setLocalModelUrl] = useState<string | null>(null);

  const clearLocalModelPreview = () => {
    setLocalModelUrl((prev) => {
      if (prev) {
        URL.revokeObjectURL(prev);
      }
      return null;
    });
  };


  const downloadUrl = useMemo(() => {
    if (!rqJobId || status !== "finished") {
      return null;
    }
    return `${API_BASE}/jobs/${rqJobId}/download`;
  }, [rqJobId, status]);

  const compareJobId =
    route.params.get("job") || route.params.get("output") || jobId;
  const compareBefore = compareJobId
    ? `${API_BASE}/jobs/${compareJobId}/preview/before`
    : null;
  const compareAfter = compareJobId
    ? `${API_BASE}/jobs/${compareJobId}/preview/after`
    : null;
  const modelUrl = jobId ? `${API_BASE}/jobs/${jobId}/model` : null;
  const selectedExt = selectedFile.includes(".")
    ? selectedFile.toLowerCase().split(".").pop()
    : "";
  const canPreviewLocal = selectedExt === "glb" || selectedExt === "gltf";
  const homePreviewUrl = localModelUrl ?? (status === "finished" ? modelUrl : null);
  const compareModelUrl = compareJobId
    ? `${API_BASE}/jobs/${compareJobId}/model`
    : null;

  useEffect(() => {
    const onHashChange = () => setRoute(getHashRoute());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  useEffect(() => {
    return () => {
      if (localModelUrl) {
        URL.revokeObjectURL(localModelUrl);
      }
    };
  }, [localModelUrl]);

  const pollJob = async (jobIdValue: string) => {
    setPolling(true);
    let active = true;

    const tick = async () => {
      if (!active) {
        return;
      }
      try {
        const data = await fetchStatus(jobIdValue);
        setStatus(data.status);
        setQueuedAt(data.created_at || "—");
        setEndedAt(data.ended_at || "—");
        setError(data.error || "");
        if (data.output_id) {
          setJobId(data.output_id);
        }

        if (data.status === "finished" || data.status === "failed") {
          active = false;
          setPolling(false);
          setSelectedFile("No file selected");
          clearLocalModelPreview();
          setFileInputKey((prev) => prev + 1);
          return;
        }
      } catch (err) {
        setError((err as Error).message);
        setStatus("error");
        active = false;
        setPolling(false);
        return;
      }

      setTimeout(tick, 2000);
    };

    tick();
  };

  const onSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError("");
    setStatus("uploading");
    setQueuedAt("—");
    setEndedAt("—");

    const form = event.currentTarget;
    const formData = new FormData(form);
    const file = formData.get("file");
    if (!file || (file as File).size === 0) {
      setError("Please choose a file before submitting.");
      setStatus("Idle");
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/jobs`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || "Upload failed.");
      }

      const data = await res.json();
      setRqJobId(data.job_id || null);
      setJobId(data.output_id || null);
      setStatus(data.status || "queued");
      await pollJob(data.job_id);
    } catch (err) {
      setStatus("error");
      setError((err as Error).message);
      setPolling(false);
    }
  };

  if (route.path.startsWith("/compare")) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-950 to-slate-900 text-ink">
        <div className="pointer-events-none fixed inset-0 opacity-10 mix-blend-soft-light bg-[url('data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22160%22 height=%22160%22 viewBox=%220 0 160 160%22%3E%3Cfilter id=%22n%22%3E%3CfeTurbulence type=%22fractalNoise%22 baseFrequency=%220.9%22 numOctaves=%222%22/%3E%3C/filter%3E%3Crect width=%22160%22 height=%22160%22 filter=%22url(%23n)%22 opacity=%220.8%22/%3E%3C/svg%3E')]"></div>
        <main className="mx-auto grid max-w-6xl gap-6 px-6 py-12">
          <header className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <div className="font-mono text-xs uppercase tracking-[0.3em] text-accent">HiLoForge</div>
              <h1 className="text-3xl font-semibold sm:text-4xl">Before vs After</h1>
              <p className="text-muted">Static renders from the original and baked meshes.</p>
            </div>
            <a
              href="#/"
              className="rounded-full border border-slate-700/60 px-4 py-2 text-sm text-muted transition hover:border-accent hover:text-ink"
            >
              Back to Job
            </a>
          </header>

          <section className="grid gap-6 lg:grid-cols-2">
            <div className="rounded-2xl border border-panelBorder bg-panel/80 p-4 shadow-panel">
              <div className="mb-3 flex items-center justify-between text-sm text-muted">
                <span>Before</span>
                <span className="font-mono text-xs">{compareJobId || "No job"}</span>
              </div>
              {compareBefore ? (
                <img
                  src={compareBefore}
                  alt="Before render"
                  className="w-full rounded-xl border border-slate-800/60 bg-slate-900/60"
                />
              ) : (
                <div className="rounded-xl border border-dashed border-slate-700/60 p-10 text-center text-muted">
                  No job selected.
                </div>
              )}
            </div>
            <div className="rounded-2xl border border-panelBorder bg-panel/80 p-4 shadow-panel">
              <div className="mb-3 flex items-center justify-between text-sm text-muted">
                <span>After</span>
                <span className="font-mono text-xs">{compareJobId || "No job"}</span>
              </div>
              {compareAfter ? (
                <img
                  src={compareAfter}
                  alt="After render"
                  className="w-full rounded-xl border border-slate-800/60 bg-slate-900/60"
                />
              ) : (
                <div className="rounded-xl border border-dashed border-slate-700/60 p-10 text-center text-muted">
                  No job selected.
                </div>
              )}
            </div>
            
          </section>
          <section className="rounded-2xl border border-panelBorder bg-panel/80 p-6 shadow-panel backdrop-blur">
            <div className="mb-5 flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="text-xl font-semibold">3D Preview</h2>
              <span className="font-mono text-xs text-muted">{compareJobId || "No job"}</span>
            </div>

            {compareModelUrl ? (
              <div className="h-[420px] w-full overflow-hidden rounded-2xl border border-slate-800/70 bg-slate-950/60">
                <ViewerErrorBoundary
                  key={compareModelUrl}
                  fallback={
                    <div className="flex h-full items-center justify-center px-6 text-center text-sm text-muted">
                      3D preview failed to load. The model file might be missing or the endpoint returned an error.
                    </div>
                  }
                >
                  <ModelViewer url={compareModelUrl} />
                </ViewerErrorBoundary>
              </div>
            ) : (
              <div className="rounded-2xl border border-dashed border-slate-700/60 p-10 text-center text-sm text-muted">
                3D preview will appear after processing finishes.
              </div>
            )}
          </section>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-950 to-slate-900 text-ink">
      <div className="pointer-events-none fixed inset-0 opacity-10 mix-blend-soft-light bg-[url('data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22160%22 height=%22160%22 viewBox=%220 0 160 160%22%3E%3Cfilter id=%22n%22%3E%3CfeTurbulence type=%22fractalNoise%22 baseFrequency=%220.9%22 numOctaves=%222%22/%3E%3C/filter%3E%3Crect width=%22160%22 height=%22160%22 filter=%22url(%23n)%22 opacity=%220.8%22/%3E%3C/svg%3E')]"></div>
      <main className="mx-auto grid max-w-5xl gap-7 px-6 py-14">
        <header className="grid gap-4">
          <div className="font-mono text-xs uppercase tracking-[0.3em] text-accent">HiLoForge</div>
          <h1 className="text-3xl font-semibold sm:text-5xl">
            Turn high‑poly scans into low-poly game‑ready assets in minutes.
          </h1>
          <p className="max-w-2xl text-lg text-muted">
            Upload a GLB/GLTF/FBX and get a decimated mesh with baked textures.
          </p>
        </header>

        <section className="rounded-2xl border border-panelBorder bg-panel/80 p-6 shadow-panel backdrop-blur">
          <div className="mb-5 flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-xl font-semibold">New Job</h2>
            <span className="font-mono text-xs text-muted">GLB/GLTF/FBX/OBJ/ZIP</span>
          </div>

          <form className="grid gap-5" onSubmit={onSubmit}>
            <label className="group grid cursor-pointer rounded-2xl border border-dashed border-slate-600/70 bg-slate-900/40 p-6 transition hover:border-accent">
              <input
                key={fileInputKey}
                name="file"
                type="file"
                accept=".glb,.gltf,.fbx,.obj,.zip"
                className="hidden"
                onChange={(event) => {
                  const file = event.currentTarget.files?.[0];
                  setSelectedFile(file ? file.name : "No file selected");
                  clearLocalModelPreview();
                  if (!file) {
                    return;
                  }
                  const ext = file.name.toLowerCase().split(".").pop() || "";
                  if (ext === "glb" || ext === "gltf") {
                    setLocalModelUrl(URL.createObjectURL(file));
                  }
                }}
              />
              <span className="text-lg font-medium">Drop your asset here</span>
              <span className="text-sm text-muted">or click to browse</span>
              <span className="mt-3 text-xs font-mono text-muted">{selectedFile}</span>
            </label>

            <div className="grid gap-4 sm:grid-cols-3">
              <label className="grid gap-2 text-sm text-muted">
                <span>Target Triangles (tris)</span>
                <input
                  name="target_tris"
                  type="number"
                  defaultValue={5000}
                  min={100}
                  step={100}
                  className="rounded-xl border border-slate-600/60 bg-slate-900/60 px-3 py-2 text-base text-ink"
                />
              </label>
              <label className="grid gap-2 text-sm text-muted">
                <span>Texture Size (px)</span>
                <select
                  name="tex_size"
                  defaultValue={4096}
                  className="rounded-xl border border-slate-600/60 bg-slate-900/60 px-3 py-2 text-base text-ink"
                >
                  <option value={1024}>1024</option>
                  <option value={2048}>2048</option>
                  <option value={4096}>4096</option>
                </select>
              </label>
              <label className="grid gap-2 text-sm text-muted">
                <span>Ray Distance (units)</span>
                <input
                  name="ray_distance"
                  type="number"
                  defaultValue={0.02}
                  min={0.001}
                  step={0.001}
                  className="rounded-xl border border-slate-600/60 bg-slate-900/60 px-3 py-2 text-base text-ink"
                />
              </label>
            </div>

            <div className="grid gap-4 sm:grid-cols-3">
              <label className="grid gap-2 text-sm text-muted">
                <span>UV Island Margin (UV)</span>
                <input
                  name="island_margin"
                  type="number"
                  defaultValue={0.06}
                  min={0.0}
                  step={0.01}
                  className="rounded-xl border border-slate-600/60 bg-slate-900/60 px-3 py-2 text-base text-ink"
                />
              </label>
              <label className="grid gap-2 text-sm text-muted">
                <span>Bake Margin (px)</span>
                <input
                  name="bake_margin"
                  type="number"
                  defaultValue={12}
                  min={0}
                  step={1}
                  className="rounded-xl border border-slate-600/60 bg-slate-900/60 px-3 py-2 text-base text-ink"
                />
              </label>
              <label className="grid gap-2 text-sm text-muted">
                <span>Cage Extrusion (units)</span>
                <input
                  name="cage_extrusion"
                  type="number"
                  defaultValue={0.06}
                  min={0.0}
                  step={0.01}
                  className="rounded-xl border border-slate-600/60 bg-slate-900/60 px-3 py-2 text-base text-ink"
                />
              </label>
            </div>

            <div className="grid gap-4 sm:grid-cols-3">
              <label className="grid gap-2 text-sm text-muted">
                <span>Auto Smooth Angle (deg) (Experimental)</span>
                <input
                  name="auto_smooth_angle"
                  type="number"
                  defaultValue={0}
                  min={0}
                  max={180}
                  step={1}
                  className="rounded-xl border border-slate-600/60 bg-slate-900/60 px-3 py-2 text-base text-ink"
                />
              </label>
              <label className="grid gap-2 text-sm text-muted">
                <span>Shrinkwrap Offset (units) (Experimental)</span>
                <input
                  name="shrinkwrap_offset"
                  type="number"
                  defaultValue={0.0}
                  min={0.0}
                  step={0.01}
                  className="rounded-xl border border-slate-600/60 bg-slate-900/60 px-3 py-2 text-base text-ink"
                />
              </label>
              <label className="grid gap-2 text-sm text-muted">
                <span>Remesh Voxel Size (units) (Experimental)</span>
                <input
                  name="remesh_voxel_size"
                  type="number"
                  defaultValue={0.0}
                  min={0.0}
                  step={0.001}
                  className="rounded-xl border border-slate-600/60 bg-slate-900/60 px-3 py-2 text-base text-ink"
                />
              </label>
            </div>






            <button
              type="submit"
              disabled={polling}
              className="rounded-xl bg-gradient-to-r from-accent to-accent2 px-5 py-3 font-semibold text-slate-900 transition hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {polling ? "Processing..." : "Start Processing"}
            </button>
          </form>
        </section>
        <section className="rounded-2xl border border-panelBorder bg-panel/80 p-6 shadow-panel backdrop-blur">
          <div className="mb-5 flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-xl font-semibold">3D Preview</h2>
            <span className="font-mono text-xs text-muted">{jobId || "No job yet"}</span>
          </div>

          {homePreviewUrl ? (
            <div className="h-[420px] w-full overflow-hidden rounded-2xl border border-slate-800/70 bg-slate-950/60">
              <ViewerErrorBoundary
                key={homePreviewUrl}
                fallback={
                  <div className="flex h-full items-center justify-center px-6 text-center text-sm text-muted">
                    3D preview failed to load. The model file might be missing or the endpoint returned an error.
                  </div>
                }
              >
                <ModelViewer url={homePreviewUrl} />
              </ViewerErrorBoundary>
            </div>
          ) : (
            <div className="rounded-2xl border border-dashed border-slate-700/60 p-10 text-center text-sm text-muted">
              {canPreviewLocal
                ? "Select a GLB/GLTF file to preview it before processing."
                : "Local 3D preview is available for GLB/GLTF. Other formats will preview after processing."}
            </div>
          )}
        </section>

        <section className="rounded-2xl border border-panelBorder bg-panel/80 p-6 shadow-panel backdrop-blur">
          <div className="mb-5 flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-xl font-semibold">Status</h2>
            <span className="font-mono text-xs text-muted">{jobId || "No job yet"}</span>
          </div>

          <div className="grid gap-3 text-sm text-muted">
            <div className="flex items-center justify-between">
              <span>State</span>
              <span
                className={`rounded-full px-3 py-1 font-mono text-xs ${
                  status === "failed" || status === "error"
                    ? "bg-red-500/20 text-red-200"
                    : "bg-accent2/20 text-blue-100"
                }`}
              >
                {status}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span>Queued</span>
              <span>{queuedAt}</span>
            </div>
            <div className="flex items-center justify-between">
              <span>Finished</span>
              <span>{endedAt}</span>
            </div>
            <div className="flex items-center justify-between">
              <span>Download</span>
              {downloadUrl ? (
                <div className="flex items-center gap-3">
                  <a className="font-semibold text-accent" href={downloadUrl}>
                    Download ZIP
                  </a>
                  <a
                    className="rounded-full border border-slate-700/60 px-3 py-1 text-xs text-muted transition hover:border-accent hover:text-ink"
                    href={`#/compare?job=${jobId}`}
                  >
                    View Comparison
                  </a>
                </div>
              ) : (
                <span className="text-muted">Not ready</span>
              )}
            </div>
            {error && (
              <pre className="rounded-xl bg-red-500/10 p-3 text-xs text-red-200">{error}</pre>
            )}
          </div>
        </section>

        <footer className="flex flex-wrap items-center justify-between gap-3 font-mono text-xs text-muted">
          <div>High‑detail bakes for low‑poly meshes.</div>
        </footer>
      </main>
    </div>
  );
}
