# Sightline

[![Web](https://github.com/aschepis/sightline/workflows/Web/badge.svg)](https://github.com/aschepis/sightline/actions)
[![CI](https://github.com/aschepis/sightline/workflows/CI/badge.svg)](https://github.com/aschepis/sightline/actions)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Privacy-first tools for blurring faces, redacting video by hand, and
transcribing speech with speaker labels. Everything runs on your own
device. Nothing is uploaded.

**Use it now: <https://adamschepis.com/sightline/app/>**

## The web app

Sightline runs entirely inside your browser. Your photos, videos and
recordings are opened, processed and saved on your computer; they are never
sent to a server, and no outside service ever sees them. The only downloads
the app makes are the recognition models, which are fetched once, kept in the
browser, and work offline afterwards. You can install it from the browser
menu like a normal app.

- **Blur Faces**: finds faces in photos and videos and blurs them, in batches.
  Same CenterFace detector and masking as the desktop app; detections match
  to within a pixel.
- **Face Smudge**: paint a blur over anything, frame by frame, and follow a
  face by hand while the video plays. Export a new copy with the audio kept.
- **Transcription**: Whisper speech-to-text with word timing and speaker
  identification. Name the speakers in the app and the names go into the
  saved `.txt`, `.srt` and `.json` files.
- **Models**: download the models ahead of time for offline use, see what is
  stored, delete what you no longer need.

Works in Chrome, Edge, Safari 16.4+ and Firefox 130+. A graphics card is
used automatically when the browser allows it, which makes face blurring run
at roughly real time and transcription several times faster than real time.
Browsers without that support fall back to the main processor.

Video input is MP4, MOV and M4V today. Supporting the web app costs nothing
to host; if it saves you time, [buy me a coffee](https://ko-fi.com/N4N8U0J6M).

### Running the web app locally

```bash
cd web
npm install
npm run dev        # http://localhost:5173/sightline/app/
npm test
npm run build      # static site in web/dist
```

See [web/README.md](web/README.md) for the layout and
[WEB_APP_PLAN.md](WEB_APP_PLAN.md) for the architecture and the decisions
behind it. Pushes to `main` that touch `web/` or `docs/` deploy to GitHub
Pages automatically.

## The desktop app (deprecated)

The original Sightline is a Python desktop application for macOS, Windows and
Linux with the same three tools. It is **deprecated in favour of the web
app**: it still works and the
[latest release](https://github.com/aschepis/sightline/releases/latest) stays
available, but new features land in the web app first and the desktop
builds will not be updated.

Reasons to still use it: you need WebM, MKV or AVI input, which the web app
does not read yet, or you want the exact WhisperX and pyannote pipeline for
transcription. Everything else is better served by the web app.

### Requirements

- Python 3.8 or higher with `tkinter`
- [FFmpeg](https://ffmpeg.org/) for video processing and audio extraction
- [Conda](https://docs.conda.io/en/latest/) for environment management

### Install from source

```bash
git clone https://github.com/aschepis/sightline.git
cd sightline
conda create -n sightline-build python=3.12
make install
make run
```

### Build a standalone executable

```bash
make clean build   # output in dist/
```

For the signed macOS `.app` bundle see `make build-macos` and
[RELEASING.md](RELEASING.md).

### Development

```bash
make install-dev
make test
make lint
```

## License

MIT. See [LICENSE](LICENSE).

## Attributions

- [deface](https://github.com/ORB-HD/deface) and its CenterFace model for face detection.
- [Whisper](https://github.com/openai/whisper) via [transformers.js](https://github.com/huggingface/transformers.js) and [WhisperX](https://github.com/m-bain/whisperX) for transcription.
- [pyannote](https://github.com/pyannote/pyannote-audio) and [WavLM](https://github.com/microsoft/unilm/tree/master/wavlm) for speaker identification.
- [ONNX Runtime Web](https://onnxruntime.ai/), [mp4box.js](https://github.com/gpac/mp4box.js) and [mp4-muxer](https://github.com/Vanilagy/mp4-muxer) in the web app.
- [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter), [tkinterdnd2](https://github.com/pmgagne/tkinterdnd2), [OpenCV](https://opencv.org/), [NumPy](https://numpy.org/) and [Pillow](https://python-pillow.org/) in the desktop app.
- [Uicons](https://www.flaticon.com/uicons) for the icons.
