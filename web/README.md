# Sightline Web

Browser version of Sightline. Face blurring, manual smudging and transcription
run on the user's device in Web Workers; nothing is ever uploaded. See
`../WEB_APP_PLAN.md` for the architecture and hosting options.

## Develop

```bash
npm install
npm run dev        # http://localhost:5173, served with COOP/COEP headers
npm test           # vitest unit tests for the ported algorithms
npm run typecheck
npm run build      # dist/ built for the /sightline/app/ subpath
```

`public/models/centerface.onnx` is deface's CenterFace model with dynamic
input dimensions (`onnx.tools.update_model_dims` on the file shipped in the
`deface` package). The ONNX Runtime WASM files are imported with Vite `?url`
in `src/lib/ortPaths.ts` and emitted as hashed assets.

## Hosting

The build is static and deploys to GitHub Pages next to the landing page:
`.github/workflows/web.yml` assembles `docs/` plus this build under `app/`
and publishes it to adamschepis.com/sightline/app/. Vite's `base` is set to
that subpath. GitHub Pages cannot send the cross-origin isolation headers
that multi-threaded WebAssembly needs, so the CPU fallback runs on one
thread there; WebGPU is unaffected. A host that allows custom headers (or a
header-injecting service worker) would restore multi-threading.

## Layout

- `src/engine/` job queue and the `LocalExecutor` that runs jobs in workers.
- `src/faceblur/` port of deface's CenterFace decoding and masking, ONNX
  Runtime Web detector, and the media worker.
- `src/video/` mp4box demux, WebCodecs decode/encode, mp4-muxer output.
- `src/smudge/` smudge operations and the random-access `FrameSource`.
- `src/transcribe/` Whisper via transformers.js, pyannote segmentation plus
  WavLM x-vectors for speakers, output formatting.
- `src/pages/` one React page per tool.
