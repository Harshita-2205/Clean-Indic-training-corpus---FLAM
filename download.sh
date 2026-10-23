#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
RAW="$ROOT/raw"
mkdir -p "$RAW/wiki" "$RAW/hinglish"
UA='FlamDataAssignment/1.0 (reproducible educational corpus exercise)'
WIKI_URL='https://dumps.wikimedia.org/hiwiki/20261001/hiwiki-20261001-pages-articles-multistream.xml.bz2'
PHINC_URL='https://huggingface.co/datasets/LingoIITGN/PHINC/resolve/44b5471df75e508b9d6fcdbcc93df04bb1e84056/PHINC.csv?download=true'
curl --fail --location --retry 3 --user-agent "$UA" "$WIKI_URL" -o "$RAW/wiki/hiwiki-20261001-pages-articles-multistream.xml.bz2"
curl --fail --location --retry 3 --user-agent "$UA" "$PHINC_URL" -o "$RAW/hinglish/PHINC.csv"
python3 "$ROOT/src/record_sources.py" "$RAW"
echo 'Downloads complete. Raw files are preserved; run ./run.sh raw out.'
