#!/usr/bin/env bash
set -euo pipefail

# Run PyInstaller while temporarily hiding conda-meta so PyInstaller's conda hook
# does not parse broken metadata (KeyError: 'depends').

if [ "$#" -lt 1 ]; then
  echo "Usage: $0 <spec-file> [additional PyInstaller args...]" >&2
  exit 1
fi

spec_file="$1"
shift || true

# Resolve conda-meta path from inside the current Python env (assumes conda run wrapper).
meta_dir="$(python - <<'PY'
import sys, pathlib
print(pathlib.Path(sys.prefix, "conda-meta").as_posix())
PY
)"

restore_meta() {
  if [ -d "${meta_dir}.bak" ]; then
    mv "${meta_dir}.bak" "${meta_dir}"
  fi
}

trap restore_meta EXIT

if [ -d "${meta_dir}" ]; then
  mv "${meta_dir}" "${meta_dir}.bak"
fi

PYINSTALLER_NO_CONDA=1 python -m PyInstaller "${spec_file}" "$@"
