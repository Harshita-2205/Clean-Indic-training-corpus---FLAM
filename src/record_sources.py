#!/usr/bin/env python3
"""Record source provenance and hashes without altering downloaded files."""
import hashlib, json, pathlib, sys
from datetime import datetime, timezone
root = pathlib.Path(sys.argv[1])
rows=[]
for p in sorted(x for x in root.rglob('*') if x.is_file() and x.name not in {'sources.json','.gitkeep'}):
    h=hashlib.sha256(); size=0
    with p.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024), b''):
            size += len(block); h.update(block)
    if 'wiki' in p.parts:
        name='Hindi Wikipedia current pages-articles dump'; url='https://dumps.wikimedia.org/hiwiki/20261001/hiwiki-20261001-pages-articles-multistream.xml.bz2'; license='CC BY-SA 4.0 (Wikipedia text; attribution/share-alike required)'
    elif p.name.lower().startswith('phinc'):
        name='PHINC Hinglish corpus'; url='https://huggingface.co/datasets/LingoIITGN/PHINC/resolve/44b5471df75e508b9d6fcdbcc93df04bb1e84056/PHINC.csv'; license='CC BY 4.0 (per dataset card)'
    else: name=p.parent.name; url=''; license='verify source license before use'
    rows.append({'name':name,'url':url,'license':license,'path':str(p.relative_to(root.parent)),'download_recorded_utc':datetime.now(timezone.utc).isoformat(),'bytes':size,'sha256':h.hexdigest()})
(root/'sources.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(f'Recorded {len(rows)} raw file(s) in {root}/sources.json')
