# Sightline

[![CI](https://github.com/aschepis/sightline/workflows/CI/badge.svg)](https://github.com/aschepis/sightline/actions)
[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A comprehensive privacy and redaction suite for the desktop. Sightline combines automated face blurring, interactive manual redaction, and offline transcription into a single, easy-to-use application.

## Features

- **🛡️ Automated Redaction**: Automatically detect and blur faces in images and videos using the `deface` library.
- **🎨 Interactive Face Smudge**: Manually redact faces or sensitive information in videos with a frame-by-frame editor.
- **📝 Transcription**: Convert speech to text locally with speaker diarization (speaker identification) using WhisperX.
- **🔒 Privacy-First**: All processing is performed locally on your device. No data is ever sent to the cloud.
- **🖥️ Cross-Platform**: Native support for macOS, Windows, and Linux.

## Requirements

- Python 3.8 or higher
- `tkinter` (usually included with Python)
- [FFmpeg](https://ffmpeg.org/) (required for video processing and audio extraction)
- [Conda](https://docs.conda.io/en/latest/) (for environment management)

## Installation

### Option 1: Install from Source

````bash
# Clone the repository
git clone https://github.com/aschepis/sightline.git
cd sightline

# Create a Conda environment
conda create -n sightline-build python=3.12

# Install dependencies
make install

# Run the application
```bash
make run
````

### Option 2: Build Standalone Executable

You can build a standalone executable for your platform:

```bash
make clean build
# Output will be in the dist/ directory
```

## Usage

1.  **Launch Sightline**: Run `make run` or open your built executable.
2.  **Choose a Module**:
    - **Face Blur**: For automated redaction of images and videos.
    - **Transcription**: For generating transcripts with speaker labels.
    - **Face Smudge**: For manual, precise video redaction (access via the "Smudge" button or menu).
3.  **Process Files**: Drag and drop your files, configure your settings (blur intensity, model selection), and click "Start".

## Development

To set up a development environment:

```bash
make install-dev
make test
make lint
```

For building the macOS `.app` bundle with signing support, see `make build-macos`.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Attributions

- [Uicons](https://www.flaticon.com/uicons) for the icons.
- [deface](https://github.com/ORB-HD/deface) for face detection.
- [WhisperX](https://github.com/m-bain/whisperX) for transcription and diarization.
- [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) for the modern GUI.
- [tkinterdnd2](https://github.com/pmgagne/tkinterdnd2) for the drag and drop support.
- [OpenCV](https://opencv.org/) for the computer vision library.
- [NumPy](https://numpy.org/) for the numerical computing.
- [Pillow](https://python-pillow.org/) for the image processing.
