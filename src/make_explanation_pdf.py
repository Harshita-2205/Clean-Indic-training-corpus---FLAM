#!/usr/bin/env python3
"""Build a detailed, metrics-backed walkthrough of the assignment project."""
import json, pathlib, sys
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, KeepTogether

root=pathlib.Path(__file__).resolve().parents[1]
out=pathlib.Path(sys.argv[2] if len(sys.argv)>2 else root/'docs/project_explanation.pdf')
manifest_path=pathlib.Path(sys.argv[1] if len(sys.argv)>1 else root/'out/manifest.json')
manifest=json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {}
counts=manifest.get('counts',{}); bylang=manifest.get('counts_by_language',{})
near_path=manifest_path.parent/'near_duplicate_examples.jsonl'
near_rows=[]
if near_path.exists():
    for line in near_path.read_text(encoding='utf-8').splitlines():
        if line: near_rows.append(json.loads(line))
near_rows.sort(key=lambda r:(abs(float(r.get('jaccard',0))-.82),int(r.get('hamming',64)),r.get('candidate_id','')))
near_rows=near_rows[:3]
def n(k): return f"{counts.get(k,0):,}"
styles=getSampleStyleSheet()
styles.add(ParagraphStyle(name='CoverTitle',parent=styles['Title'],fontName='Helvetica-Bold',fontSize=24,leading=29,textColor=colors.HexColor('#17324d'),alignment=TA_CENTER,spaceAfter=9*mm))
styles.add(ParagraphStyle(name='CoverSub',parent=styles['Normal'],fontSize=12,leading=17,textColor=colors.HexColor('#536879'),alignment=TA_CENTER,spaceAfter=5*mm))
styles.add(ParagraphStyle(name='H1x',parent=styles['Heading1'],fontName='Helvetica-Bold',fontSize=17,leading=21,textColor=colors.HexColor('#17324d'),spaceBefore=2*mm,spaceAfter=4*mm))
styles.add(ParagraphStyle(name='H2x',parent=styles['Heading2'],fontName='Helvetica-Bold',fontSize=11.5,leading=14,textColor=colors.HexColor('#236477'),spaceBefore=3*mm,spaceAfter=1.5*mm))
styles.add(ParagraphStyle(name='Bodyx',parent=styles['BodyText'],fontSize=9.3,leading=13.2,textColor=colors.HexColor('#23313b'),spaceAfter=2.2*mm))
styles.add(ParagraphStyle(name='Smallx',parent=styles['BodyText'],fontSize=8.2,leading=11,textColor=colors.HexColor('#536879'),spaceAfter=1.5*mm))
styles.add(ParagraphStyle(name='Callout',parent=styles['BodyText'],fontSize=9.4,leading=13.5,textColor=colors.HexColor('#17324d'),backColor=colors.HexColor('#eaf4f4'),borderColor=colors.HexColor('#b7d5d6'),borderWidth=.6,borderPadding=8,spaceBefore=2*mm,spaceAfter=3*mm))
doc=SimpleDocTemplate(str(out),pagesize=A4,rightMargin=19*mm,leftMargin=19*mm,topMargin=17*mm,bottomMargin=17*mm,title='Flam assignment project walkthrough',author='')
story=[]
def p(text,style='Bodyx'): story.append(Paragraph(text,styles[style]))
def h(text): p(text,'H1x')
def sub(text): p(text,'H2x')
def bullet(text): p('• '+text,'Bodyx')
def table(rows,widths=None):
    cell=ParagraphStyle(name='TableCell',fontName='Helvetica',fontSize=8.1,leading=10.3,textColor=colors.HexColor('#23313b'))
    head=ParagraphStyle(name='TableHead',parent=cell,fontName='Helvetica-Bold',textColor=colors.white)
    wrapped=[[Paragraph(escape(str(value)),head if r==0 else cell) for value in row] for r,row in enumerate(rows)]
    t=Table(wrapped,colWidths=widths,repeatRows=1,hAlign='LEFT')
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#17324d')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),8.1),('LEADING',(0,0),(-1,-1),10.3),('GRID',(0,0),(-1,-1),.35,colors.HexColor('#c9d5dc')),('VALIGN',(0,0),(-1,-1),'TOP'),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f2f6f8')]),('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
    story.append(t); story.append(Spacer(1,3*mm))

def footer(canvas, document):
    canvas.saveState(); w,h=A4
    canvas.setStrokeColor(colors.HexColor('#d5e0e5')); canvas.line(19*mm,13*mm,w-19*mm,13*mm)
    canvas.setFont('Helvetica',7.5); canvas.setFillColor(colors.HexColor('#687b86'))
    canvas.drawString(19*mm,8.5*mm,'Flam Data Assignment | Project walkthrough')
    canvas.drawRightString(w-19*mm,8.5*mm,f'Page {document.page}')
    canvas.restoreState()

story += [Spacer(1,25*mm)]
p('Building a clean Indic training corpus','CoverTitle')
p('A detailed walkthrough of the collection, cleaning, language labeling, deduplication, PII, holdout evaluation, and reproducibility decisions','CoverSub')
story.append(Spacer(1,13*mm))
p('Purpose','H2x')
p('This document explains the project in the same order the assignment evaluates it. It is written to help a reviewer reproduce the run and to help you explain the engineering in a live follow-up. Counts below are read from the generated manifest; the full corpus is intentionally not bundled in the submission sample.','Bodyx')
story.append(Spacer(1,7*mm))
p(f"Observed run: {n('input')} input records; {n('kept')} retained documents; {manifest.get('eval_items',0):,} held-out eval items; {counts.get('eval_items_affected',0):,} eval items with contamination matches.",'Callout')
story.append(Spacer(1,18*mm))
p('Run commands','H2x')
p('<font name="Courier">./download.sh</font> downloads source files and writes hashes. <font name="Courier">./run.sh raw out</font> is the offline curation entry point.','Bodyx')
p('Files to send: source, download.sh, run.sh, DECISIONS.md, eval.jsonl, contamination.jsonl, manifest.json, and a deterministic 1,000-row clean sample. Do not send the full raw or clean corpus.','Smallx')
story.append(PageBreak())

h('1. What the project does')
p('The data path is intentionally simple: preserve source bytes, stream records, normalize and infer language, remove low-quality or sensitive content, deduplicate, remove evaluation leaks, then write a clean JSONL file and a reason ledger. The same ordered pass produces enough evidence to explain why each row survived or was dropped.','Bodyx')
table([['Stage','Action','Evidence written'],['Acquire','Download fixed-source files without editing them','sources.json: URL, license, date, bytes, SHA-256'],['Parse','Stream XML / CSV / JSONL / TXT; isolate malformed rows','ledger row at parse stage'],['Normalize + label','NFC; remove invisible controls; whitespace; infer script/language','manifest funnel counts by language'],['Quality + PII','Conservative text checks; replace requested identifiers','ledger reason; retained text has placeholders'],['Deduplicate','Exact normalized equality; SimHash candidates; Hamming threshold','dup_of pointer and method'],['Evaluation','Hold out 200 PHINC items; scan before keep','eval.jsonl and contamination.jsonl'],['Publish output','Write staging output then swap atomically','clean/, ledger, manifest']],[29*mm,74*mm,69*mm])
p('Key idea: the ledger is the audit trail. A dropped record should be explainable without guessing from the final corpus. A kept record has a stable ID, inferred language, and source.','Callout')
sub('Directory map')
p('<font name="Courier">src/pipeline.py</font> contains the pipeline. <font name="Courier">download.sh</font> handles network access separately. <font name="Courier">run.sh</font> is offline. <font name="Courier">raw/</font> is ignored by Git and holds unchanged downloads. <font name="Courier">out/</font> is generated output. <font name="Courier">submission/</font> contains the sample artifacts to share.','Bodyx')
story.append(PageBreak())

h('2. Sources and rights')
table([['Source','Role and amount','License / handling'],['Hindi Wikipedia, 2026-10-01 snapshot','Primary Devanagari article text; 2026-10-01 current-article XML dump','CC BY-SA 4.0 text reuse path; retain attribution, note edits, preserve share-alike obligations for adapted material.'],['PHINC, LingoIITGN','13,738 Romanized Hinglish-English sentence pairs in the source; first 6,000 logical rows selected; source text is the Sentence field','Dataset card declares CC BY 4.0; cite the dataset and associated paper. The raw CSV is retained as downloaded.']],[37*mm,55*mm,80*mm])
p('The selected corpus uses the first 20,000 Hindi namespace-0 pages and first 6,000 PHINC logical rows in pinned source order; later records are still streamed to the ledger. The downloader is separate because network access and transformation have different reproducibility needs. Raw files are never rewritten; the pipeline reads them directly. `raw/sources.json` records acquisition time and content hashes. In a future rerun, pinning the dump snapshot and preserving the original files makes the corpus reconstructable even if upstream “latest” links move.','Bodyx')
sub('Source caveats')
bullet('Wikipedia is encyclopedic and formal. It gives broad Hindi coverage but does not represent everyday conversation well.')
bullet('PHINC is sentence-level and parallel to English. It supplies naturally code-mixed Roman Hindi, but it is not a broad conversational corpus and may contain source-specific bias or offensive text.')
bullet('The final output should preserve the source identifier. Mixed license terms should be documented per source; do not claim the combined dataset has a single blanket license without reviewing share-alike implications.')
story.append(PageBreak())

h('3. Cleaning, language labels, and privacy')
sub('Normalization')
p('Text is normalized with Unicode NFC, then control and format characters are removed except whitespace. All whitespace runs become one ASCII space. This matters for Devanagari combining marks and invisible direction/zero-width controls: visually identical strings can otherwise compare as different exact duplicates. NFC is chosen as a stable canonical form; compatibility normalization could collapse characters with distinct meaning and is avoided.','Bodyx')
sub('Language identification')
p('The label set is exactly hi, hi-Latn, en, or other. Devanagari presence with a modest script share yields hi, including mixed Devanagari and English. For Latin text, a small, inspectable Romanized-Hindi vocabulary is used to distinguish Hinglish from English. This is a heuristic, not a production language identifier: inspect a hand-labeled sample, expand vocabulary carefully, and report errors rather than trusting the source labels.','Bodyx')
sub('Quality filtering')
p('Filters remove empty or extremely short strings, URL-heavy spam, leftover markup, replacement glyphs, low alphabetic content, and highly repetitive text. They avoid a blanket minimum sentence length beyond a small floor, because short proverbs, headings, poetry, and tables can be legitimate. The exact threshold and example false positives belong in DECISIONS.md.','Bodyx')
sub('PII redaction')
table([['Pattern','Replacement','Conservative behavior'],['Email address','<EMAIL>','Match standard local@domain forms'],['Indian phone number','<PHONE>','Accept common Indian number formatting; inspect edge cases'],['Aadhaar-like 12 digits','<AADHAAR>','Require a contiguous/spaced 12-digit pattern'],['PAN','<PAN>','Five letters, four digits, one letter']],[42*mm,37*mm,93*mm])
p('Redaction occurs before a retained text is written. Plain numbers that do not match these identifier patterns are preserved. The regexes are a best-effort assignment implementation; production PII review would require broader validation and a false-positive audit.','Bodyx')
story.append(PageBreak())

h('4. Deduplication and contamination')
sub('Exact and near-duplicate choices')
p('Exact deduplication keys the redacted, normalized, case-folded string. Near deduplication computes a 64-bit SimHash over character 5-grams. An SQLite index keeps the corpus index on disk. Eight 8-bit bands retrieve candidates, then Hamming distance &lt;= 6, character 5-gram Jaccard >= 0.82, and identical numeric-token sequences are required; digits inside @handles and URLs are ignored. The Jaccard gate was added after reviewing template-like district articles and year pages that SimHash alone would merge. The banding keeps candidate search bounded while guaranteeing that a pair within six bit flips shares at least one 8-bit band.','Bodyx')
p('The threshold is a project choice to be audited, not a universal constant. Review pairs with distances near 6, note false merges and missed paraphrases. SimHash catches surface similarity; it does not understand meaning.','Bodyx')
if near_rows:
    for i,r in enumerate(near_rows,1):
        p(f"Pair {i}: IDs {r.get('candidate_id')} and {r.get('other_id')}; Hamming {r.get('hamming')}, Jaccard {r.get('jaccard',0):.3f}; observed call: {r.get('decision')} at the corpus cutoff H6/J0.82. See DECISIONS.md for the text-level judgment.",'Smallx')
else: p('No candidate pair within eight Hamming bits was captured by this run.','Smallx')
sub('Evaluation split and leakage')
p('Two hundred PHINC records are held out deterministically by selecting the 200 lexicographically smallest SHA-256 hashes of source record keys. The held-out records are written to eval.jsonl and never enter clean training output. Before a candidate can be kept, the pipeline checks equality after normalization, an approximate Devanagari-to-Latin transliteration, and near matches. Each leak is removed from training and recorded with eval_id, train_ids, and method.','Bodyx')
p('Cross-script checking is necessarily approximate because Hinglish has many spelling variants. The transliteration step is a transparent candidate finder, not a guarantee that all cross-script paraphrases are found. Eval screening directly compares each selected training row against all 200 eval vectors, then uses Hamming distance <=16 and character 5-gram Jaccard >=0.70 with equal numeric tokens, more permissive than corpus near-deduplication (<=6 and >=0.82). Digits inside @handles and URLs are ignored so a changed username cannot mask matching text. The run results and reviewed true/false candidate examples appear in DECISIONS.md and the bundled candidate review file.','Bodyx')
sub('Run results')
rows=[['Observed count','Value'],['Input records',n('input')],['Retained records',n('kept')],['Parse failures',n('dropped_parse')],['Quality drops',n('dropped_quality')],['Exact duplicates',n('dropped_exact')],['Near duplicates',n('dropped_near')],['Contamination drops',n('dropped_contamination')],['Held-out eval rows',f"{manifest.get('eval_items',0):,}"],['Affected eval items',str(counts.get('eval_items_affected',0))]]
table(rows,[92*mm,80*mm])
story.append(PageBreak())

h('5. Reliability, restart behavior, and scale')
sub('Streaming and malformed data')
p('MediaWiki pages are parsed with ElementTree iterparse, which releases each page after processing. CSV and JSONL are read record-by-record. A malformed JSONL row is counted and skipped without stopping later records. CSV parsing is isolated by physical line for this assignment source, allowing a malformed line to be counted. For general CSV with quoted embedded newlines, use a quote-aware recoverable parser or explicitly reject that format; a single physical line is not a universal CSV record.','Bodyx')
sub('Deterministic safe reruns')
p('The pipeline builds a fresh staging directory beside the target output. It processes sorted file paths and stable source order; IDs derive from the relative file, source key, and ordinal. Once every output is closed and the manifest is written, the staging directory replaces the prior output. A killed run leaves no newly published partial output, and a rerun starts with an empty index so rows cannot accumulate. This is whole-run restartability, not checkpoint-and-resume; very large jobs would need partition checkpoints.','Bodyx')
sub('If this grew to 2 TB')
p('The first pressure points are single-process parsing throughput, SQLite write amplification and disk space, and the global near-duplicate index. The design would move to deterministic object-store partitions, a distributed streaming engine, content-addressed intermediate files, and a sharded approximate-neighbor index. Each partition would have its own committed manifest; final assembly would be an idempotent manifest merge. Cross-partition dedupe would require global candidate routing or a second pass. Provenance and the row-level ledger remain required even after the compute engine changes.','Bodyx')
sub('Known limitations to say plainly')
bullet('The language heuristic will mislabel Latin English that contains common Hindi tokens and Hinglish with uncommon spellings.')
bullet('SimHash near-duplicate removal may merge repeated boilerplate or miss paraphrases; threshold examples should support the chosen cutoff.')
bullet('The transliteration is approximate. A zero contamination count means “none found by these checks,” not proof of zero leakage.')
bullet('Whole-run restart is safe but does not resume midway. At 2 TB, checkpointing is the first reliability improvement.')
story.append(PageBreak())

h('6. Follow-up preparation')
p('A 45-minute live exercise is likely to test whether you can explain how a decision affects a row and then change the implementation without losing the audit trail. Practice using one malformed record, one genuine short text, one duplicate pair, and one PII example.','Bodyx')
table([['Likely prompt','Strong concise answer'],['Why was this row dropped?','Point to its ledger status, stage, reason, and duplicate ID when applicable.'],['How do you know Hindi vs Hinglish?','Explain script detection and the Romanized-Hindi vocabulary heuristic; acknowledge uncertain cases.'],['What happens if the process is killed?','Incomplete staging is not published; rerun starts from raw input and replaces output after completion.'],['Can you increase recall for cross-script leaks?','Add a stronger transliteration candidate generator, validate it manually, and keep the method and limits in contamination output.'],['Why this threshold?','Show pairs near distance 6 and explain the false-merge / missed-duplicate trade-off.'],['What would you improve next?','Label a sample for language/quality error analysis, improve transliteration/LID, and add resumable partitions.']],[55*mm,117*mm])
p('The best answer is a concrete example plus the ledger row and the relevant function. Avoid claiming a heuristic is perfect. Be clear about what the run measured, what it did not measure, and the next experiment you would make.','Callout')
story.append(Spacer(1,4*mm))
p('Rebuild summary: check Python 3 and curl; run ./download.sh; preserve raw/ and raw/sources.json; run ./run.sh raw out; inspect manifest.json, ledger.jsonl, eval.jsonl, contamination.jsonl; update DECISIONS.md with the observed output; create a fixed-seed 1,000-row sample; commit code and documentation without including the full corpus.','Smallx')

doc.build(story,onFirstPage=footer,onLaterPages=footer)
print(out)
