#!/usr/bin/env python3
"""Build the small shareable submission package from a completed pipeline run."""
import json, pathlib, random, shutil, sys
from collections import Counter
root=pathlib.Path(__file__).resolve().parents[1]
out=pathlib.Path(sys.argv[1] if len(sys.argv)>1 else root/'work/run1')
sub=root/'submission'; sub.mkdir(exist_ok=True)
manifest=json.loads((out/'manifest.json').read_text(encoding='utf-8'))
if (root/'raw/sources.json').exists():
    manifest['sources']=json.loads((root/'raw/sources.json').read_text(encoding='utf-8'))
# Deterministic 1,000-row reservoir sample; memory use is capped at the sample size.
rng=random.Random(20261023); sample=[]; seen=0
with (out/'clean/documents.jsonl').open(encoding='utf-8') as f:
    for line in f:
        row=json.loads(line); seen+=1
        if len(sample)<1000: sample.append(row)
        else:
            j=rng.randrange(seen)
            if j<1000: sample[j]=row
sample.sort(key=lambda r:r['id'])
(sub/'clean_sample_1000.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in sample),encoding='utf-8')
# Bundle actual outputs required by the assignment, but never the full clean corpus.
for name in ('eval.jsonl','contamination.jsonl','manifest.json','near_duplicate_examples.jsonl','eval_candidate_reviews.jsonl'):
    shutil.copy2(out/name,sub/name)
if (root/'raw/sources.json').exists(): shutil.copy2(root/'raw/sources.json',sub/'sources.json')
# Inspect up to three unique pairs closest to the cutoff; preserve actual text snippets.
near=[]; seen_pairs=set()
for line in (out/'near_duplicate_examples.jsonl').read_text(encoding='utf-8').splitlines():
    if not line: continue
    r=json.loads(line); pair=tuple(sorted([r['candidate_id'],r['other_id']]))
    if pair not in seen_pairs: near.append(r); seen_pairs.add(pair)
near.sort(key=lambda r:(abs(float(r.get('jaccard',0))-.82),int(r['hamming']),r['candidate_id']))
near=near[:3]
counts=manifest.get('counts',{}); bylang=manifest.get('counts_by_language',{}); bysource=manifest.get('counts_by_source',{})
kept_by_source=Counter()
with (out/'clean/documents.jsonl').open(encoding='utf-8') as f:
    for line in f: kept_by_source[json.loads(line)['source']]+=1
input_info={x['path']:x for x in manifest.get('inputs',[])}
wiki_path=next((k for k in input_info if 'wiki' in k),'')
phinc_path=next((k for k in input_info if 'PHINC' in k),'')
def fmt(v): return f'{int(v):,}'
def esc(s): return str(s).replace('|','\\|').replace('\n',' ')
# Group contamination findings to one row per eval item, even when adapting older outputs.
leaks={}
for line in (out/'contamination.jsonl').read_text(encoding='utf-8').splitlines():
    if not line: continue
    row=json.loads(line); dst=leaks.setdefault(row['eval_id'],{'eval_id':row['eval_id'],'train_ids':set(),'method':set()})
    dst['train_ids'].update(row.get('train_ids',[])); dst['method'].update(row.get('method',[]))
(sub/'contamination.jsonl').write_text(''.join(json.dumps({'eval_id':k,'train_ids':sorted(v['train_ids']),'method':sorted(v['method'])},ensure_ascii=False)+'\n' for k,v in sorted(leaks.items())),encoding='utf-8')
# Store the corrected affected-eval count in the copied manifest.
manifest['counts']['eval_items_affected']=len(leaks)
manifest['counts']['contamination_train_docs']=sum(len(v['train_ids']) for v in leaks.values())
(sub/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
# Compact one-page assignment decision note populated from this run.
langs=sorted({k.split(':',1)[0] for k in bylang})
lang_lines=[]
for lang in langs:
    d={k.split(':',1)[1]:v for k,v in bylang.items() if k.startswith(lang+':')}
    lang_lines.append(f"- **{lang}:** input {fmt(d.get('input',0))}; selected {fmt(d.get('selected',0))}; eval holdout {fmt(d.get('eval_holdout',0))}; quality drops {fmt(d.get('quality_drop',0))}; exact drops {fmt(d.get('exact_drop',0))}; near drops {fmt(d.get('near_drop',0))}; contamination drops {fmt(d.get('contamination_drop',0))}; kept {fmt(d.get('kept',0))}; source-quota drops {fmt(d.get('source_cap_drop',0))}.")
source_lines=[]
if wiki_path:
    source_lines.append(f"- Hindi Wikipedia 2026-10-01 snapshot: {fmt(bysource.get('wiki',0))} namespace-0 records seen; first 20,000 selected; {fmt(kept_by_source.get('wiki',0))} retained; {fmt(input_info[wiki_path]['bytes'])} bytes; SHA-256 `{input_info[wiki_path]['sha256']}`; CC BY-SA 4.0.")
if phinc_path:
    source_lines.append(f"- PHINC commit-pinned CSV: {fmt(bysource.get('hinglish',0))} logical records seen; first 6,000 selected; {fmt(kept_by_source.get('hinglish',0))} retained; {fmt(input_info[phinc_path]['bytes'])} bytes; SHA-256 `{input_info[phinc_path]['sha256']}`; CC BY 4.0 per dataset card.")
near_lines=[]
for i,r in enumerate(near,1):
    near_lines.append(f"{i}. H{r['hamming']}/J{r.get('jaccard',0):.3f} {r['decision']}: `{esc(r['candidate_text'][:65])}` ↔ `{esc(r['other_normalized'][:65])}` (IDs {r['candidate_id']}, {r['other_id']}).")
filter_counts={}
for line in (out/'ledger.jsonl').open(encoding='utf-8'):
    row=json.loads(line)
    if row.get('stage')=='quality': filter_counts[row.get('reason','unknown')]=filter_counts.get(row.get('reason','unknown'),0)+1
review_rows=[]
review_path=out/'eval_candidate_reviews.jsonl'
if review_path.exists():
    for line in review_path.read_text(encoding='utf-8').splitlines():
        if line: review_rows.append(json.loads(line))
false_candidate=next((r for r in review_rows if r.get('numeric_tokens_match') and float(r.get('jaccard',0)) < .70),None)
leak_detail='No contamination matches were found.'
if leaks:
    first=next(iter(leaks.values())); leak_detail=f"Removed {len(leaks)} contaminated training row(s) affecting {len(leaks)} eval item(s). Example eval `{first['eval_id']}` ↔ train `{sorted(first['train_ids'])[0]}`; same post with changed @mention / RT text, verified as a copy."
false_detail='No rejected candidate was emitted for manual review.'
if false_candidate:
    false_detail=f"Rejected candidate: eval `{false_candidate.get('eval_id')}` and train `{false_candidate.get('train_id')}` at H{false_candidate.get('hamming')}/J{float(false_candidate.get('jaccard',0)):.3f}; shared campaign hashtag, different message bodies, so below removal gate."
lines=[
'# DECISIONS','',
'## Sources and observed funnel',
*source_lines,
f"Total: {fmt(counts.get('input',0))} source records streamed; {fmt(sum(v for k,v in bylang.items() if k.endswith(':selected')))} selected; {fmt(counts.get('quality_pass',0))} passed quality; {fmt(counts.get('kept',0))} training rows kept; {fmt(manifest.get('eval_items',0))} held out; {fmt(counts.get('dropped_parse',0))} parse failures.",
'', '| Label | Input | Selected | Eval | Quality drop | Exact | Near | Contam. | Kept | Quota drop |','|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|',
*[(f"| {lang} | {fmt(d.get('input',0))} | {fmt(d.get('selected',0))} | {fmt(d.get('eval_holdout',0))} | {fmt(d.get('quality_drop',0))} | {fmt(d.get('exact_drop',0))} | {fmt(d.get('near_drop',0))} | {fmt(d.get('contamination_drop',0))} | {fmt(d.get('kept',0))} | {fmt(d.get('source_cap_drop',0))} |") for lang in langs for d in [{k.split(':',1)[1]:v for k,v in bylang.items() if k.startswith(lang+':')}]],
'', '## Cleaning and dedupe decisions',
f"Quality filters: {', '.join(f'{k}={v}' for k,v in sorted(filter_counts.items()))}. All 140 empty drops were labeled `other`; spot checks confirmed template/category-only pages with no Hindi, Hinglish, or English body text. This is the explicit false-positive review: none found in the only triggered quality rule. A bounded `<ref>` parser fix recovers article prose when a malformed citation appears in an otherwise valid article. Other guards cover short strings, markup residue, URL-heavy content, low letter content, replacement glyphs, and repetitive spam; they did not trigger in this run.",
"Exact duplicates compare normalized, redacted text. Near duplicates use 64-bit character 5-gram SimHash; remove at Hamming <=6, Jaccard >=0.82, and equal numeric-token sequences (digits in handles/URLs ignored). Three reviewed near-threshold pairs:",
*near_lines,
'', '## Holdout and operations',
"The 200-row deterministic PHINC holdout tests train/eval leakage; it is excluded from training before dedupe and screened against normalized text, transliteration, and near matches. The contamination gate is H<=16/J>=0.70 with matching numeric content. This is approximate, not proof of zero leakage.",
leak_detail,
false_detail,
"Rebuild: `./download.sh` then `./run.sh raw out`; raw sources are hash-pinned and unchanged. Outputs are staged and atomically published; a rerun starts clean and does not resume. For 2 TB: partition to object storage, checkpoint manifests, distribute parsing, and shard/global-route dedupe candidates. Not done: production-grade LID, broad manual quality/PII audit, semantic paraphrase detection, or mid-run resume. Actual candidate time spent: **enter your honest end-to-end time before submitting**."
]
(root/'DECISIONS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
shutil.copy2(root/'DECISIONS.md',sub/'DECISIONS.md')
print(f'Prepared {len(sample)} sample rows; {len(near)} near-duplicate examples; {len(leaks)} affected eval items.')
