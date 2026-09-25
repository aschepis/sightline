# Sightline Web: plan

Goal: turn Sightline into a web application hosted alongside Damocles, keep every
current and future feature possible, and keep infrastructure cost near zero by
running as much as possible in the browser.

Written 2026-09-25 against `main` at `90f8b8f`.

---

## 1. What exists today

**Sightline** is a Python/CustomTkinter desktop app (PyInstaller bundles for
macOS, Windows, Linux). Three tools, one config file, no accounts, no network.

| Tool | How it works now | Key knobs |
|---|---|---|
| Face Blur (`views/face_blur_view.py`) | Spawns the `deface` CLI per file, up to 8 concurrent, parses stdout for progress. deface runs the CenterFace ONNX model and uses ffmpeg (imageio-ffmpeg) for decode/encode. | `thresh`, `scale`, `boxes`, `mask_scale`, `replacewith` (blur / solid / mosaic / img / none), `keep_audio`, `keep_metadata` |
| Face Smudge (`face_smudge.py`) | In-process editor: OpenCV decodes frames, LRU frame cache, click/drag paints Gaussian circles, undo/redo stack, playback scrubbing. Export re-encodes with `cv2.VideoWriter` (mp4v) and remuxes audio with ffmpeg. | radius, sigma |
| Transcription (`views/transcription_view.py`) | In-process WhisperX: `base` model, wav2vec2 alignment, pyannote `speaker-diarization-3.1` (gated, needs HF token). Writes `start–end SPEAKER: text` lines. | HF token, model download dialog |

Privacy is the product: "All processing is performed locally on your device.
No data is ever sent to the cloud." Any web version has to keep that promise
as the default, which is also what makes it cheap.

The last five commits are all packaging pain (conda, ffmpeg on macOS,
linting for the release pipeline). A web build removes most of that.

**Damocles** (`~/src/github.com/aschepis/damocles`) hosts on:

- Scaleway Kapsule Kubernetes, Cilium, Terraform in `infra/`.
- Node pools: `general` (DEV1-M x4–5) and `cv` (GP1-XS x1–3, CPU only, tainted
  for the Flask CV service that runs YOLOv5, InsightFace, EasyOCR).
- One Scaleway LB-S, Terraform-owned. The Rails `Service` is `type:
  LoadBalancer` and the Scaleway cloud controller binds it to that LB. There is
  no ingress controller, so host-based routing to a second app does not exist yet.
- GitOps: ArgoCD app-of-apps → Helm chart in `k8s/charts/damocles`. Images
  built to GHCR by `.github/workflows/deploy.yml` with a 5-minute debounce.
- External Secrets Operator backed by Scaleway Secret Manager.
- Scaleway Object Storage buckets with CORS for direct browser uploads.
- Grafana / Loki / Alloy observability, Tailscale for private access.

---

## 2. Architecture

```
┌──────────────────────────── browser (PWA) ───────────────────────────┐
│  UI (TypeScript SPA)                                                  │
│    └─ Job engine ── selects an executor per job ───────────────┐      │
│         ├─ LocalExecutor (Web Workers)                         │      │
│         │    face-blur: WebCodecs + ONNX Runtime Web (CenterFace)     │
│         │    smudge:    WebCodecs + canvas, same export pipeline      │
│         │    transcribe: transformers.js Whisper (WebGPU/WASM)        │
│         │    diarize:   sherpa-onnx WASM (pyannote seg + embeddings)  │
│         │    mux/demux: mp4box.js + mp4-muxer, ffmpeg.wasm fallback   │
│         └─ RemoteExecutor (opt-in, off by default) ────────────┐      │
│  Model cache: Cache Storage / OPFS, "Manage models" page       │      │
└────────────────────────────────────────────────────────────────┼──────┘
                                                                 │ HTTPS
                       ┌─────────────────────────────────────────▼──────┐
                       │ sightline-api (FastAPI, tiny)  ── presigned PUT │
                       │ sightline-worker (existing Python core, CPU)    │
                       │   scale-to-zero; runs in damocles Kapsule       │
                       │   or on RunPod serverless GPU for big jobs      │
                       │ Scaleway bucket, 24h lifecycle delete           │
                       └─────────────────────────────────────────────────┘
```

Two rules make "all features and future features possible":

1. **Every feature is defined as a job** with typed inputs, options, progress,
   and outputs. The UI never calls a model directly.
2. **Two executors implement every job.** The local executor runs in the
   browser. The remote executor runs the existing Python code in a container.
   A new feature ships on the remote executor first if the browser cannot do
   it yet, then moves local when it can. Nothing is ever blocked by browser
   limits, and the privacy default stays local.

The remote executor is opt-in per job, labeled clearly, and can be left
undeployed entirely if you want a $0 browser-only product.

---

## 3. Feature by feature: browser vs server

### 3.1 Face Blur

**Browser (recommended default).** deface's model is a 7 MB CenterFace ONNX
file shipped inside the `deface` package. ONNX Runtime Web runs it on WebGPU
(Chrome, Edge, Safari 26+, Firefox 141+) or WASM SIMD everywhere else. Port
deface's pre/post-processing (scale, threshold, NMS, ellipse or box mask,
`mask_scale`, replacewith modes) to TypeScript so results match the desktop.

Pipeline per video:
mp4box.js demux → `VideoDecoder` → CenterFace inference in a worker → mask +
blur in a canvas/WebGL shader → `VideoEncoder` (H.264 or VP9/AV1 by browser
support) → mp4-muxer, copying the original audio track untouched. Images go
through the same inference and draw straight to a canvas.

Expected speed on a laptop with WebGPU: roughly real time for 1080p. WASM
only: 3–10x slower than real time. Both show progress and can be cancelled.

Gaps versus desktop, with mitigations:
- `keep_metadata` copies container-level metadata with ffmpeg. In-browser we
  can copy the `udta`/`meta` boxes via mp4box; EXIF on images via a small
  library. Full parity is a remote-executor job.
- Exotic containers (`.avi`, `.mkv`, `.m4p`) may not demux with mp4box. Fall
  back to ffmpeg.wasm (LGPL build, ~30 MB, downloaded on demand) for demux and
  mux, or to the remote executor.
- Files larger than free memory must be streamed. `File.slice` + mp4box handles
  input; output goes to OPFS or `showSaveFilePicker` (Chrome) then a blob
  download elsewhere.

**Server.** Runs `deface` exactly as today via the extracted core package.

### 3.2 Face Smudge

**Browser (recommended, it is a better fit than desktop).** The editor is
canvas UI: frame-accurate seeking via WebCodecs (the `<video>` element cannot
be trusted to land on an exact frame), an LRU frame cache like today,
`SmudgeOperation` list with undo/redo, playback and scrubber. Export reuses
the Face Blur encode pipeline and copies audio, which fixes the current
mp4v-then-ffmpeg two-step.

Save the operation list as a sidecar JSON so edits are resumable and can be
applied server-side if someone wants a remote export.

**Server.** `apply_smudge_to_frame` already exists in `face_smudge.py`; the
worker applies a JSON operation list to a file.

### 3.3 Transcription with diarization

This is the hardest piece in-browser and the one where I recommend shipping
the remote executor alongside from day one.

**Browser.**
- Whisper: transformers.js v3 runs `whisper-base` through `whisper-large-v3-turbo`
  on WebGPU (turbo is ~800 MB quantized, base ~75 MB). It returns word-level
  timestamps from cross-attention, which replaces WhisperX's wav2vec2 alignment
  step with slightly lower precision. Audio decode uses `AudioContext.decodeAudioData`
  or ffmpeg.wasm for odd formats.
- Diarization: sherpa-onnx ships a WASM build that runs pyannote
  `segmentation-3.0` plus a speaker-embedding model and clustering, producing the
  same `SPEAKER_xx` turns. Word-to-speaker assignment is the same logic as
  `whisperx.assign_word_speakers`, a few dozen lines to port.
- pyannote weights are gated on Hugging Face only for stats collection; the
  ONNX exports are published openly (`onnx-community/pyannote-segmentation-3.0`
  and sherpa-onnx's model zoo). No HF token needed, which removes the "Manage
  models" token dialog entirely.

Expected speed: WebGPU turbo ~2–5x faster than real time; WASM base ~real time.
A one-hour recording is feasible but slow on WASM, which is why the remote
executor matters here.

**Server.** Existing WhisperX code, CPU or GPU. On the cv node pool CPU (GP1-XS)
`base` runs ~1x real time; larger models want a GPU (see 5.3).

### 3.4 Batch processing

Browser: a job queue in a worker with a concurrency limit, same as
`MAX_BATCH_SIZE = 8` today but defaulting lower on WASM. Server: one job per file.

### 3.5 Future features

Anything new (license plate blur, text/OCR redaction, audio voice masking,
object removal, watermarking) follows the same path: implement in the Python
core first, expose as a job on the remote executor, then port to the local
executor when an ONNX/WASM path exists. Damocles' CV service already has
YOLOv5, InsightFace and EasyOCR wired up, so plate and text redaction could
share models.

---

## 4. Frontend

- **Stack:** Vite + TypeScript + React (transformers.js and ONNX Runtime Web
  examples are React; Svelte works equally if you prefer). Tailwind with the
  existing `sightline_theme.json` colors ported. PWA via `vite-plugin-pwa`.
- **Offline-first:** service worker precaches the app shell; models are
  downloaded once into Cache Storage with a "Manage models" page showing sizes
  and a delete button. After first load the app works with no network, which is
  the strongest version of the privacy promise and something the desktop app
  also offers.
- **Threading:** all inference and codec work in Web Workers. Multi-threaded
  ONNX Runtime and ffmpeg.wasm need `SharedArrayBuffer`, which needs the
  cross-origin isolation headers `Cross-Origin-Opener-Policy: same-origin` and
  `Cross-Origin-Embedder-Policy: require-corp`. This constrains hosting (see 5.1).
- **Capability probe at startup:** WebGPU, WebCodecs, memory, SharedArrayBuffer.
  The engine picks WebGPU → WASM → remote and shows why. The user can pin a
  choice.
- **Repo layout:** `web/` inside this repo, or a new `sightline-web` repo. Keep
  it in this repo so the Python core and the web client version together.

---

## 5. Hosting and cost

### 5.1 Static app: three options

| Option | Monthly cost | COOP/COEP headers | Notes |
|---|---|---|---|
| **A. Cloudflare Pages (recommended)** | $0 | Yes, via `_headers` file | Unlimited bandwidth, global CDN, custom domain, preview deploys per PR. R2 sits next to it for model files if needed. |
| B. GitHub Pages | $0 | No; needs the `coi-serviceworker` shim, which reloads the page once | Docs site already lives there. Fine for a first spike, awkward long term. |
| C. nginx pod in the Damocles cluster | ~$0 compute, but needs routing | Yes | Requires either an ingress controller in front of Rails (a Damocles change) or a second Scaleway LB-S (~€10/mo). Only worth it if you want one pane of glass. |

Recommendation: A. It costs nothing, keeps the cluster untouched for the
part that gets the most traffic, and Cloudflare's headers support is exactly
what the threaded WASM path needs.

**Model files.** transformers.js and sherpa-onnx models come from the Hugging
Face Hub CDN, free. CenterFace (7 MB) and any custom ONNX we export go in a
`models/` folder of the Pages deploy or in Cloudflare R2 (10 GB storage and
all egress free). Do not serve models from the Scaleway bucket: egress there
costs money.

### 5.2 Remote executor: where the API and worker run

Deploy only when you want the server fallback. Components:

- `sightline-api`: FastAPI, ~50 lines. Issues presigned PUT/GET URLs for a
  Scaleway bucket (same pattern as Damocles media uploads, CORS already
  understood), enqueues a job, reports status. Protected by Cloudflare
  Turnstile plus a per-IP rate limit, optionally an access code from Secret
  Manager. No accounts.
- `sightline-worker`: the existing Python core in a container (base it on
  `cv-service/Dockerfile`'s CPU torch pattern, ~2 GB image without models,
  models pulled from a bucket at start like cv-service does). Runs as a
  Kubernetes `Job` per request, or a `Deployment` scaled to zero with KEDA on
  queue depth. Tolerates the `cv` taint so it lands on the GP1-XS pool, which
  has ~14 GB free today.
- Bucket: `sightline-scratch`, lifecycle rule deletes objects after 24 hours.
  Processing never touches disk outside the pod's emptyDir.
- **Exposure: Cloudflare Tunnel** (`cloudflared` Deployment in the namespace,
  free). This avoids adding an ingress controller or a second load balancer to
  Damocles at all. `api.sightline.<domain>` resolves at Cloudflare and tunnels
  into the cluster. Tailscale would work too but you already have Cloudflare
  in the chain for Pages.
- Packaging: a `k8s/charts/sightline` Helm chart in this repo, an ArgoCD
  `Application` added next to `damocles-app.yaml` in the app-of-apps directory,
  GHCR image built by a workflow copied from Damocles' `deploy.yml`. Secrets via
  the existing External Secrets Operator.

Incremental cost on the existing cluster: effectively $0 while idle (scale to
zero), and CPU time you already pay for while running. Object storage is
cents. If the cv pool ever has to grow a node because of Sightline, that is
roughly €0.10/hr for a GP1-XS.

### 5.3 GPU, only if needed

CPU handles `deface` and Whisper `base` fine. For `large-v3` transcription or
long videos on the server path:

| Option | Cost | Fit |
|---|---|---|
| **RunPod serverless (recommended if GPU is ever needed)** | ~$0.0002–0.0004 per second while a job runs, $0 idle | Per-job, pay only for runtime. You already use RunPod. The worker image runs unchanged with CUDA torch. Media leaves the EU, so label it. |
| Scaleway GPU node pool (L4) with `min_size = 0` | ~€0.75/hr while a node exists, plus scale-up latency of a few minutes | Keeps data in fr-par next to Damocles. Autoscaler handles scale to zero. |

Skip GPU in the first release. Add it as a third executor target if usage
shows demand.

### 5.4 Cost summary

| Configuration | Monthly | Privacy |
|---|---|---|
| Browser only (Cloudflare Pages, HF Hub models) | $0 plus domain | Nothing leaves the device |
| + CPU remote executor in Damocles cluster via Cloudflare Tunnel | ~$0 incremental, scale to zero | Opt-in per job, EU, deleted in 24h |
| + RunPod GPU for heavy jobs | Pay per second, ~$1/hr of GPU time actually used | Opt-in, non-EU |
| Alternative: second Scaleway LB for an in-cluster static site | ~€10/mo | n/a |

Prices are approximate as of September 2026; verify before committing.

---

## 6. Phases

**Phase 0: spikes (1 week).** De-risk the two uncertain pieces before writing
product code. Each spike is a throwaway page with a number at the end.
1. CenterFace on ONNX Runtime Web (WebGPU and WASM) + WebCodecs decode/encode +
   mp4-muxer on a 1080p clip. Measure frames per second and confirm audio copy.
2. transformers.js Whisper + sherpa-onnx diarization on a 10-minute recording.
   Measure wall time on WebGPU and WASM and eyeball speaker accuracy against
   the desktop output.
Decision gate: if either spike is more than ~10x slower than real time on
WASM, ship that feature remote-first and local as "experimental".

**Phase 1: extract the Python core.** Move deface argument building, smudge
operations, and the WhisperX pipeline out of the Tkinter views into a
`sightline_core` package with a CLI. Desktop app keeps working, now as a thin
UI over the core. This is the container image for the remote executor and
the reference implementation the browser port is tested against. Add golden
tests: same input, same options, same output boxes and segments.

**Phase 2: web shell + Face Blur.** Vite/React PWA, capability probe, job
engine with the local executor, model manager, Face Blur for images then
video, batch queue. Deploy to Cloudflare Pages with preview deploys. This is
the first public release.

**Phase 3: Face Smudge editor.** Canvas editor, WebCodecs frame access,
undo/redo, sidecar JSON, export through the shared encoder.

**Phase 4: Transcription.** Whisper first, diarization second, model picker
with size warnings. Output matches the desktop text format plus JSON and SRT.

**Phase 5: remote executor.** FastAPI + worker + Helm chart + ArgoCD app +
Cloudflare Tunnel + scratch bucket with lifecycle rule. Turnstile and rate
limit. Wire the RemoteExecutor in the client behind an explicit toggle.
Optional: RunPod GPU target.

**Phase 6: desktop decision.** Options: (a) keep the PyInstaller app as-is over
the core package; (b) wrap the PWA in Tauri with the Python core as a sidecar,
which drops the CustomTkinter UI and most of the packaging pain; (c) retire it
once the PWA is installable and offline. Decide after Phase 4 with real usage.

---

## 7. Risks

- **Browser support drift.** WebGPU on Safari and Firefox is recent. The WASM
  path is mandatory, not optional, and CI should run the golden tests in both
  modes (Playwright with WebGPU on, then off).
- **Memory.** A tab gets roughly 2–4 GB. Streaming decode and OPFS output are
  the design, not a later optimization. Cap input size per mode and say why.
- **Codec licensing.** H.264 encode via `VideoEncoder` uses the browser's
  licensed encoder, which is fine. ffmpeg.wasm must be the LGPL build without
  x264; use it for demux/mux and audio only.
- **Diarization quality.** sherpa-onnx's clustering is not byte-identical to
  pyannote 3.1's pipeline. Set expectations in the UI and keep the remote path
  for the exact desktop result.
- **Abuse of the remote executor.** It is a free video-processing API. Keep it
  behind Turnstile, rate limits, size and duration caps, and an optional access
  code. Scale-to-zero also bounds the blast radius.
- **Damocles coupling.** The only Damocles change is one ArgoCD `Application`
  file. Everything else lives in this repo. If Damocles moves clouds,
  Sightline's worker moves with the chart.

---

## 8. Open decisions for you

1. Domain: subdomain of an existing one, or new?
2. Ship the remote executor in the first release, or browser-only first?
3. React or Svelte for the SPA?
4. Keep the desktop app long term, or plan for Tauri/retirement in Phase 6?

Nothing in this plan changes code yet. Phase 1 (core extraction) is the first
code change and I will describe the exact current behavior of each moved
module before touching it.
