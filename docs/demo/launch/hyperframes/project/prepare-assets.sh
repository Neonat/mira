#!/bin/bash
# Reconstruct the two evidence crops used by index.html. Requires curl, pdftoppm, sips and shasum.
set -euo pipefail
project_dir="$(cd "$(dirname "$0")" && pwd)"
repo_dir="$(cd "$project_dir/../../../../.." && pwd)"
asset_dir="$project_dir/assets"
report="$repo_dir/reports/demo-output/current/03-regulatory-facts.png"
pdf_url='https://brdr.hkma.gov.hk/eng/doc-ldg/docId/getPdf/20260827-4-EN/20260827-4-EN.pdf'
mkdir -p "$asset_dir"
[ -f "$report" ] || { echo "Missing historical report screenshot: $report" >&2; exit 1; }
printf '%s  %s\n' '09626bcfe1b09eac67ca46962760c8777f1a7ea799ff9ed2a09e0aee77a98174' "$report" | shasum -a 256 -c -
cp "$report" "$asset_dir/report-facts.png"
# Supply a previously downloaded copy as argument 1 to avoid a network request.
if [ "$#" -gt 0 ]; then cp "$1" "$asset_dir/hkma-pep.pdf"; else curl --fail --location --silent --show-error "$pdf_url" -o "$asset_dir/hkma-pep.pdf"; fi
printf '%s  %s\n' 'a306c79c180122597cabe57e454b0335b011b686ad8d36adf83fd2324a9bf577' "$asset_dir/hkma-pep.pdf" | shasum -a 256 -c -
pdftoppm -f 2 -l 2 -scale-to-y 1800 -scale-to-x -1 -png -singlefile "$asset_dir/hkma-pep.pdf" "$asset_dir/pep-source-page-2"
sips -c 105 795 --cropOffset 155 285 "$asset_dir/report-facts.png" --out "$asset_dir/report-paragraph.png" >/dev/null
sips -z 210 1590 "$asset_dir/report-paragraph.png" >/dev/null
sips -c 40 915 --cropOffset 315 205 "$asset_dir/pep-source-page-2.png" --out "$asset_dir/pep-first-line.png" >/dev/null
sips -z 72 1647 "$asset_dir/pep-first-line.png" >/dev/null
printf 'Prepared evidence assets in %s\n' "$asset_dir"
