#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m PyInstaller ti_tracker.spec --noconfirm

version="$(python -c 'from titrack.version import __version__; print(__version__)')"
mkdir -p dist
(
    cd dist
    zip -r "TITrack-${version}-linux.zip" TITrack
)

echo "Built dist/TITrack and dist/TITrack-${version}-linux.zip"
