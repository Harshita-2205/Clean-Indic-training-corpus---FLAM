#!/usr/bin/env python3
"""Deterministic, streaming Hindi/Hinglish curation pipeline (stdlib only)."""
from __future__ import annotations
import bz2, csv, hashlib, html, json, os, pathlib, re, shutil, sqlite3, sys, tempfile, unicodedata, xml.etree.ElementTree as ET
from collections import Counter, defaultdict

DEV = re.compile(r'[\u0900-\u097F]')
LATIN = re.compile(r'[A-Za-z]')
EMAIL = re.compile(r'(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b')
PAN = re.compile(r'(?i)\b[A-Z]{5}[0-9]{4}[A-Z]\b')
AADHAAR = re.compile(r'(?<!\d)(?:\d[ -]?){11}\d(?!\d)')
PHONE = re.compile(r'(?<!\w)(?:\+?91[ -]?)?(?:\(?0?\d{2,4}\)?[ -]?)?[6-9]\d{9}(?!\w)')
URL = re.compile(r'(?i)\b(?:https?://|www\.)\S+')
TAG = re.compile(r'<[^>]{1,300}>')
WIKI_MARKUP = re.compile(r'\{\{[^{}]*\}\}|\[\[([^]|]+\|)?([^]]+)\]\}|\[https?://[^ ]+ ([^]]+)\]|\[https?://[^]]+\]|\'{2,5}')
SPACE = re.compile(r'\s+')
SOURCE_CAPS={'wiki':20000,'hinglish':6000}
# Evaluation leakage checks are intentionally more permissive than corpus
# dedupe: a copied post can differ only in its @mention or punctuation.
EVAL_NEAR_HAMMING=16
EVAL_NEAR_JACCARD=0.70
HINDI_WORDS = set('hai hain tha thi the ho hoga hogi kar kya kaise kahan kab kyun nahi nahin aur par se ko ka ki ke mein mai hum tum aap mera meri apna apne bahut achha accha bura yaar bhai dost mujhe tumhe chahiye karo kripya namaste dhanyavaad haii'.split())

class BadRecord(Exception): pass

def norm(s):
    s=unicodedata.normalize('NFC', s)
    s=''.join(c for c in s if unicodedata.category(c) not in {'Cf','Cc'} or c in '\n\t\r')
    return SPACE.sub(' ',s).strip()

def strip_balanced_templates(s):
    out=[]; i=0; last=0; depth=0
    while i<len(s):
        # Some imported wikitext has an unclosed infobox/template. Do not let
        # one broken opener consume the rest of an article: section headings
        # are a safe recovery boundary because they begin outside template
        # parameter syntax in this dump.
        if depth and s[i]=='\n' and re.match(r'\n={2,6}[^=\n].*?={2,6}\s*(?:\n|$)',s[i:]):
            depth=0
            last=i+1
            i+=1
            continue
        if s.startswith('{{',i):
            if depth==0: out.append(s[last:i])
            depth+=1; i+=2
        elif s.startswith('}}',i) and depth:
            depth-=1; i+=2
            if depth==0: last=i
        else: i+=1
    if depth==0: out.append(s[last:])
    return ''.join(out)

def replace_wikilink(m):
    body=m.group(1).strip()
    parts=body.split('|')
    target=parts[0].strip().lstrip(':').casefold()
    if target.startswith(('category:','श्रेणी:')): return ' '
    if target.startswith(('file:','image:','चित्र:','फ़ाइल:')):
        return parts[-1] if len(parts)>1 and len(parts[-1])>5 else ' '
    return parts[-1].strip() if len(parts)>1 else parts[0].split('#',1)[0].strip()

def scrub_wiki(s):
    s=html.unescape(s)
    s=re.sub(r'(?is)<!--.*?-->',' ',s)
    # Bound paired-reference removal so an unclosed <ref> cannot consume the
    # remainder of a page. Very long or malformed refs lose only their tag.
    s=re.sub(r'(?is)<ref\b[^>]*>.{0,4000}?</ref>',' ',s)
    s=re.sub(r'(?is)<ref\b[^>]*/>',' ',s)
    s=re.sub(r'(?i)<ref\b[^>]*>',' ',s)
    s=strip_balanced_templates(s)
    for _ in range(20):
        cleaned=re.sub(r'\[\[([^\[\]]*)\]\]',replace_wikilink,s)
        if cleaned==s: break
        s=cleaned
    s=re.sub(r'(?i)\[https?://[^\s\]]+(?:\s+([^\]]+))?\]',lambda m:m.group(1) or ' ',s)
    s=re.sub(r"'{2,5}",'',s)
    s=re.sub(r'(?m)^\s*(?:\{\||\|\}|\|-).*$', ' ', s)
    s=s.replace('||',' | ').replace('!!',' | ')
    s=re.sub(r'(?m)^\s*[|!+]\s?', ' ', s)
    s=re.sub(r'(?m)^\s*[=*#;:]+\s*', ' ', s)
    s=re.sub(r'(?m)\s*=+\s*$', ' ', s)
    s=TAG.sub(' ', s)
    s=URL.sub(' ',s)
    s=s.replace('[[',' ').replace(']]',' ').replace('{{',' ').replace('}}',' ')
    s=norm(s)
    s=re.sub(r'[\[\]]',' ',s)
    return norm(s)

def redact(s):
    s=EMAIL.sub('<EMAIL>',s)
    s=PAN.sub('<PAN>',s)
    s=AADHAAR.sub('<AADHAAR>',s)
    s=PHONE.sub('<PHONE>',s)
    return s

def language(s):
    dev=sum(1 for _ in DEV.finditer(s)); latin=sum(1 for _ in LATIN.finditer(s))
    if dev and dev >= max(3, latin*0.12): return 'hi'
    words=re.findall(r'[a-z]+',s.lower())
    hits=sum(w in HINDI_WORDS for w in words)
    if hits >= 2 or (hits >= 1 and len(words) <= 12): return 'hi-Latn'
    return 'en' if latin else 'other'

def quality(s):
    if not s: return 'empty'
    if len(s) < 4 and not any(ch.isdigit() for ch in s): return 'too_short'
    if len(URL.findall(s)) >= 10: return 'url_heavy'
    if re.search(r'\{\{|\}\}|\[\[|\]\]',s): return 'markup_residue'
    letters=sum(ch.isalpha() for ch in s)
    if letters == 0 and not any(ch.isdigit() for ch in s): return 'low_letter_content'
    if letters and sum('\ufffd'==ch for ch in s)/max(len(s),1) > .01: return 'replacement_glyphs'
    toks=s.split()
    if len(toks)>=30 and len(set(t.lower() for t in toks))/len(toks) < .10: return 'repetitive_spam'
    return ''

def transliterate(s):
    """Readable Devanagari-to-Latin approximation for cross-script leak candidates."""
    consonants={'क':'k','ख':'kh','ग':'g','घ':'gh','ङ':'ng','च':'ch','छ':'chh','ज':'j','झ':'jh','ञ':'ny','ट':'t','ठ':'th','ड':'d','ढ':'dh','ण':'n','त':'t','थ':'th','द':'d','ध':'dh','न':'n','प':'p','फ':'ph','ब':'b','भ':'bh','म':'m','य':'y','र':'r','ल':'l','व':'v','श':'sh','ष':'sh','स':'s','ह':'h','ळ':'l','क़':'q','ख़':'kh','ग़':'gh','ज़':'z','ड़':'r','ढ़':'rh','फ़':'f'}
    vowels={'अ':'a','आ':'aa','इ':'i','ई':'ii','उ':'u','ऊ':'uu','ऋ':'ri','ए':'e','ऐ':'ai','ओ':'o','औ':'au'}
    matras={'ा':'a','ि':'i','ी':'ii','ु':'u','ू':'uu','ृ':'ri','े':'e','ै':'ai','ो':'o','ौ':'au'}
    out=[]; i=0
    while i<len(s):
        ch=s[i]
        if ch in consonants:
            out.append(consonants[ch]); i+=1
            if i<len(s) and s[i] in matras: out.append(matras[s[i]]); i+=1
            elif i<len(s) and s[i]=='्': i+=1
            else: out.append('a')
        elif ch in vowels: out.append(vowels[ch]); i+=1
        elif ch in {'ं','ँ'}: out.append('n'); i+=1
        elif ch=='ः': out.append('h'); i+=1
        elif ch=='़': i+=1
        else: out.append(ch.lower()); i+=1
    return norm(''.join(out))

def shingles(s,k=5):
    s=' '+s.lower()+' '
    if len(s)<=k: return {s}
    return {s[i:i+k] for i in range(len(s)-k+1)}

def jaccard(a,b):
    sa=shingles(a); sb=shingles(b)
    return len(sa & sb)/max(1,len(sa | sb))

def numeric_signature(s):
    # Digits embedded in social handles and URLs identify accounts/links, not
    # claims in the text. Preserve dates and quantities for the numeric guard.
    s=re.sub(r'(?<!\w)@[A-Za-z0-9_]+',' ',s)
    s=URL.sub(' ',s)
    return tuple(re.findall(r'\d+',s))

def simhash(s):
    v=[0]*64
    for sh in shingles(s):
        x=int.from_bytes(hashlib.blake2b(sh.encode(),digest_size=8).digest(),'big')
        for i in range(64): v[i] += 1 if (x>>i)&1 else -1
    return sum((1<<i) for i,x in enumerate(v) if x>=0)

def hamming(a,b): return bin((a^b)&((1<<64)-1)).count('1')
def sqlite_i64(x): return x if x < (1<<63) else x-(1<<64)

def sha_file(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def records(path):
    """Yield (stable source key, text); XML is parsed incrementally."""
    suf=''.join(path.suffixes).lower()
    source='wiki' if 'wiki' in str(path).lower() or '.xml' in suf else 'hinglish' if 'phinc' in path.name.lower() else path.parent.name
    if path.name.endswith('.xml.bz2') or path.suffix=='.bz2':
        with bz2.open(path,'rb') as f:
            for _,el in ET.iterparse(f,events=('end',)):
                if el.tag.endswith('page'):
                    ns=el.findtext('./{*}ns')
                    title=el.findtext('./{*}title') or ''
                    txt=el.findtext('.//{*}revision/{*}text') or ''
                    if ns=='0' and txt:
                        yield source+':'+title, txt
                    el.clear()
        return
    if path.suffix.lower()=='.csv':
        with path.open(encoding='utf-8-sig',newline='',errors='replace') as f:
            reader=csv.reader(f,strict=True)
            try: headers=next(reader)
            except (StopIteration,csv.Error):
                yield source+':badheader', None
                return
            i=0
            while True:
                try: values=next(reader)
                except StopIteration: break
                except csv.Error:
                    # csv.reader tracks physical lines while yielding logical records.
                    yield source+':badrecord:'+str(reader.line_num), None
                    i+=1
                    continue
                row=dict(zip(headers,values))
                key=row.get('id') or str(i)
                text=next((v for k,v in row.items() if k and ('hinglish' in k.lower() or 'code-mixed' in k.lower() or k.lower()=='sentence')),None)
                if text is None: text=next((v for k,v in row.items() if k and 'translation' not in k.lower()),'')
                yield source+':'+str(key), text or ''
                i+=1
        return
    if path.suffix.lower() in {'.jsonl','.ndjson'}:
        with path.open(encoding='utf-8',errors='replace') as f:
            for i,line in enumerate(f):
                if not line.strip(): continue
                try: row=json.loads(line)
                except json.JSONDecodeError: yield source+':badline:'+str(i), None; continue
                txt=row.get('text') if isinstance(row,dict) else row
                yield source+':'+str(row.get('id',i) if isinstance(row,dict) else i), txt if isinstance(txt,str) else ''
        return
    if path.suffix.lower()=='.txt':
        with path.open(encoding='utf-8',errors='replace') as f:
            for i,line in enumerate(f): yield source+':'+str(i),line
        return

def main(raw_dir,out_dir):
    raw=pathlib.Path(raw_dir).resolve(); out=pathlib.Path(out_dir).resolve()
    if not raw.is_dir(): raise SystemExit(f'raw_dir not found: {raw}')
    files=sorted(p for p in raw.rglob('*') if p.is_file() and p.name!='sources.json' and any(p.name.endswith(x) for x in ('.csv','.jsonl','.ndjson','.txt','.xml.bz2','.bz2')))
    if not files: raise SystemExit('No supported raw files found (CSV, JSONL, TXT, or XML.bz2).')
    out.parent.mkdir(parents=True,exist_ok=True)
    stage=pathlib.Path(tempfile.mkdtemp(prefix=out.name+'.building-',dir=out.parent))
    clean=stage/'clean'; clean.mkdir()
    cleanf=(clean/'documents.jsonl').open('w',encoding='utf-8')
    ledger=(stage/'ledger.jsonl').open('w',encoding='utf-8')
    evalf=(stage/'eval.jsonl').open('w',encoding='utf-8')
    contf=(stage/'contamination.jsonl').open('w',encoding='utf-8')
    db=sqlite3.connect(stage/'index.sqlite')
    db.execute('PRAGMA journal_mode=WAL'); db.execute('CREATE TABLE docs(id TEXT PRIMARY KEY, norm TEXT, sh INTEGER, lang TEXT)')
    db.execute('CREATE TABLE exact(norm TEXT PRIMARY KEY, id TEXT)'); db.execute('CREATE TABLE band(band INTEGER, val INTEGER, id TEXT, PRIMARY KEY(band,val,id))')
    db.execute('CREATE TABLE held(id TEXT PRIMARY KEY, text TEXT, norm TEXT, translit TEXT)')
    counts=Counter(); bylang=Counter(); all_hashes=[]; n=0; eval_n=0; source_counts=Counter()
    # Select a deterministic 200-item holdout from PHINC by hashing source key. The
    # fixed rule avoids split drift; stream first-pass reserves lowest 200 hashes.
    candidates=[]
    held_text_by_key={}
    for p in files:
        if p.suffix.lower()=='.csv' and 'phinc' in p.name.lower():
            for source_row,(key,text) in enumerate(records(p)):
                if source_row>=SOURCE_CAPS['hinglish']: break
                if not text: continue
                candidates.append((hashlib.sha256(key.encode()).hexdigest(),key,norm(text)))
                held_text_by_key[key]=norm(text)
            break
    held_selected=sorted(candidates)[:200]
    held_keys={x[1] for x in held_selected}
    eval_vectors=[]
    eval_exact={}; eval_by_key={}
    for _,key,etext in held_selected:
        etext=norm(redact(etext))
        ev=(key,etext.casefold(),transliterate(etext).casefold(),simhash(etext.casefold()),simhash(transliterate(etext).casefold()))
        eval_vectors.append(ev); eval_by_key[key]=ev
        for value in (ev[1],ev[2]):
            eval_exact.setdefault(value,[]).append(key)
    best_rejected_eval_candidates={}
    near_examples=[]
    leaks_by_eval=defaultdict(lambda: {'train_ids':set(),'method':set()})
    for p in files: all_hashes.append({'path':str(p.relative_to(raw)),'sha256':sha_file(p),'bytes':p.stat().st_size})
    try:
        for p in files:
            source='wiki' if 'wiki' in str(p).lower() or '.xml' in ''.join(p.suffixes).lower() else 'hinglish' if 'phinc' in p.name.lower() else p.parent.name
            try:
                iterator=records(p)
                for key,text in iterator:
                    n+=1; counts['input']+=1; source_counts[source]+=1
                    if n%10000==0: print(f'processed {n:,} input records',file=sys.stderr,flush=True)
                    rid=hashlib.sha256((str(p.relative_to(raw))+'\0'+key+'\0'+str(n)).encode()).hexdigest()[:20]
                    if text is None:
                        ledger.write(json.dumps({'id':rid,'status':'dropped','stage':'parse','reason':'malformed_record','dup_of':None,'lang':'other'})+'\n'); counts['dropped_parse']+=1; bylang[('other','parse_error')]+=1; continue
                    # A fixed source cap keeps the training corpus assignment-sized while
                    # the full raw dump is still streamed and every page is ledgered.
                    over_cap=source in SOURCE_CAPS and source_counts[source]>SOURCE_CAPS[source]
                    if over_cap:
                        # Quota-dropped records still contribute language/input
                        # counts, but need not be copied, normalized, or cleaned.
                        lang=language(text)
                        bylang[(lang,'input')]+=1
                        ledger.write(json.dumps({'id':rid,'status':'dropped','stage':'selection','reason':f'{source}_source_quota_{SOURCE_CAPS[source]}','dup_of':None,'lang':lang})+'\n'); counts['dropped_collection_cap']+=1; bylang[(lang,'source_cap_drop')]+=1; continue
                    cleantext=norm(scrub_wiki(text) if source=='wiki' else text)
                    lang=language(cleantext)
                    counts['normalized']+=1; bylang[(lang,'input')]+=1; bylang[(lang,'normalized')]+=1
                    bylang[(lang,'selected')]+=1
                    if key in held_keys:
                        db.execute('INSERT OR REPLACE INTO held VALUES(?,?,?,?)',(rid,cleantext,cleantext.lower(),transliterate(cleantext)))
                        cleantext=redact(cleantext)
                        evalf.write(json.dumps({'eval_id':hashlib.sha256(key.encode()).hexdigest()[:20],'text':cleantext,'lang':lang,'source':source},ensure_ascii=False)+'\n'); eval_n+=1
                        ledger.write(json.dumps({'id':rid,'status':'dropped','stage':'split','reason':'held_out_eval','dup_of':None,'lang':lang})+'\n'); counts['heldout']+=1; bylang[(lang,'eval_holdout')]+=1; continue
                    # Drop any train-side exact, normalized, near, or cross-script leak.
                    train_text=redact(cleantext)
                    train_norm=train_text.casefold(); train_trans=transliterate(train_text).casefold()
                    train_sh=simhash(train_norm); train_tsh=simhash(train_trans)
                    leak_methods=set(); leak_keys=set()
                    for ek in eval_exact.get(train_norm,[]): leak_methods.add('normalized_exact'); leak_keys.add(ek)
                    for ek in eval_exact.get(train_trans,[]): leak_methods.add('cross_script_transliteration'); leak_keys.add(ek)
                    for ek in sorted(eval_by_key):
                        _,et,en,esh,ensh=eval_by_key[ek]
                        matches=[]; candidate_scores=[]
                        for left,right,ta,tb in ((train_sh,esh,train_norm,et),(train_tsh,ensh,train_trans,et),(train_sh,ensh,train_norm,en)):
                            distance=hamming(left,right)
                            if distance<=EVAL_NEAR_HAMMING:
                                score=jaccard(ta,tb)
                                nums_equal=numeric_signature(ta)==numeric_signature(tb)
                                candidate_scores.append((score,distance,nums_equal))
                                if score>=EVAL_NEAR_JACCARD and nums_equal: matches.append((score,distance))
                        if matches:
                            leak_methods.add('near_simhash_and_jaccard'); leak_keys.add(ek)
                        elif candidate_scores:
                            best_score,best_distance,nums_equal=max(candidate_scores,key=lambda x:(x[0],-x[1]))
                            if best_score>=0.15:
                                eval_id=hashlib.sha256(ek.encode()).hexdigest()[:20]
                                previous=best_rejected_eval_candidates.get(eval_id)
                                if previous is None or (best_score,-best_distance)>(previous['jaccard'],-previous['hamming']):
                                    best_rejected_eval_candidates[eval_id]={'eval_id':eval_id,'train_id':rid,'hamming':best_distance,'jaccard':round(best_score,4),'numeric_tokens_match':nums_equal,'reason':'numeric_tokens_mismatch' if not nums_equal else 'jaccard_below_threshold','eval_text':et[:220],'train_text':train_norm[:220]}
                    if leak_methods:
                        for ek in sorted(leak_keys):
                            leak=leaks_by_eval[hashlib.sha256(ek.encode()).hexdigest()[:20]]
                            leak['train_ids'].add(rid); leak['method'].update(leak_methods)
                        ledger.write(json.dumps({'id':rid,'status':'dropped','stage':'contamination','reason':','.join(sorted(leak_methods)),'dup_of':None,'lang':lang})+'\n')
                        counts['dropped_contamination']+=1; counts['contamination_train_docs']+=1; bylang[(lang,'contamination_drop')]+=1; continue
                    why=quality(cleantext)
                    if why:
                        ledger.write(json.dumps({'id':rid,'status':'dropped','stage':'quality','reason':why,'dup_of':None,'lang':lang,'text_preview':redact(cleantext)[:240]},ensure_ascii=False)+'\n'); counts['dropped_quality']+=1; bylang[(lang,'quality_drop')]+=1; continue
                    red=train_text; counts['quality_pass']+=1; bylang[(lang,'quality_pass')]+=1
                    normalized=norm(red).casefold()
                    hit=db.execute('SELECT id FROM exact WHERE norm=?',(normalized,)).fetchone()
                    if hit:
                        ledger.write(json.dumps({'id':rid,'status':'dropped','stage':'dedupe_exact','reason':'exact_duplicate','dup_of':hit[0],'lang':lang})+'\n'); counts['dropped_exact']+=1; bylang[(lang,'exact_drop')]+=1; continue
                    sh=simhash(normalized); buckets=[(i,(sh>>(8*i))&255) for i in range(8)]
                    seen=set()
                    for band,val in buckets:
                        seen.update(x[0] for x in db.execute('SELECT id FROM band WHERE band=? AND val=?',(band,val)))
                    best_id=None; best_distance=65; best_jaccard=0.0; duplicate_id=None; duplicate_score=-1.0; duplicate_distance=65
                    for cid in sorted(seen):
                        row=db.execute('SELECT norm,sh FROM docs WHERE id=?',(cid,)).fetchone()
                        if row:
                            distance=hamming(sh,row[1] & ((1<<64)-1))
                            if distance<=8:
                                score=jaccard(normalized,row[0])
                                if (score>best_jaccard) or (score==best_jaccard and distance<best_distance):
                                    best_id,best_distance,best_jaccard=cid,distance,score
                                nums_equal=numeric_signature(normalized)==numeric_signature(row[0])
                                if distance<=6 and score>=0.82 and nums_equal and (score>duplicate_score or (score==duplicate_score and distance<duplicate_distance)):
                                    duplicate_id,duplicate_score,duplicate_distance=cid,score,distance
                    if best_id is not None and len(near_examples)<200:
                        kept=db.execute('SELECT norm FROM docs WHERE id=?',(best_id,)).fetchone()[0]
                        near_examples.append({'candidate_id':rid,'other_id':best_id,'hamming':best_distance,'jaccard':round(best_jaccard,4),'numbers_match':numeric_signature(normalized)==numeric_signature(db.execute('SELECT norm FROM docs WHERE id=?',(best_id,)).fetchone()[0]),'candidate_text':red[:300],'other_normalized':kept[:300],'decision':'drop' if duplicate_id==best_id else 'keep'})
                    if duplicate_id is not None:
                        ledger.write(json.dumps({'id':rid,'status':'dropped','stage':'dedupe_near','reason':'simhash_le_6_and_char5gram_jaccard_ge_0.82','dup_of':duplicate_id,'lang':lang})+'\n'); counts['dropped_near']+=1; bylang[(lang,'near_drop')]+=1; continue
                    db.execute('INSERT INTO docs VALUES(?,?,?,?)',(rid,normalized,sqlite_i64(sh),lang)); db.execute('INSERT INTO exact VALUES(?,?)',(normalized,rid))
                    for band,val in buckets: db.execute('INSERT OR IGNORE INTO band VALUES(?,?,?)',(band,val,rid))
                    cleanf.write(json.dumps({'id':rid,'text':red,'lang':lang,'source':source},ensure_ascii=False)+'\n')
                    ledger.write(json.dumps({'id':rid,'status':'kept','stage':'complete','reason':'passed_all_filters','dup_of':None,'lang':lang})+'\n')
                    counts['kept']+=1; bylang[(lang,'kept')]+=1
                    if n%5000==0: db.commit()
            except (OSError,EOFError,ET.ParseError,csv.Error,UnicodeError) as e:
                counts['input_files_failed']+=1
                # preserve run and identify a stream-level failure in manifest
                counts['file_error:'+p.name+':'+type(e).__name__]+=1
        db.commit()
        db.commit()
        counts['eval_items_affected']=len(leaks_by_eval)
        for eid,leak in sorted(leaks_by_eval.items()):
            contf.write(json.dumps({'eval_id':eid,'train_ids':sorted(leak['train_ids']),'method':sorted(leak['method'])},ensure_ascii=False)+'\n')
        (stage/'eval_candidate_reviews.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for _,x in sorted(best_rejected_eval_candidates.items())),encoding='utf-8')
        cleanf.close(); ledger.close(); evalf.close(); contf.close(); db.close()
        (stage/'near_duplicate_examples.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in near_examples),encoding='utf-8')
        manifest={'pipeline_version':'1.2','normalization':'Unicode NFC; remove format/control characters; collapse whitespace','near_duplicate_method':'64-bit SimHash over character 5-grams; candidate lookup by eight 8-bit bands; near duplicate requires Hamming distance <= 6, character 5-gram Jaccard >= 0.82, and identical numeric-token sequences after removing digits inside @handles and URLs','near_duplicate_threshold_hamming':6,'near_duplicate_threshold_jaccard':0.82,'near_duplicate_require_same_numeric_tokens':True,'evaluation_leakage_thresholds':{'simhash_hamming_max':EVAL_NEAR_HAMMING,'char5gram_jaccard_min':EVAL_NEAR_JACCARD,'numeric_token_sequences_must_match':True,'numeric_tokens_ignore_handles_and_urls':True,'candidate_search':'compare every selected training row against all 200 eval vectors; no band-retrieval recall gap','note':'More permissive than corpus near-deduplication; separate candidate and conservative removal gate.'},'pii':'email, Indian Aadhaar-like 12 digit, PAN, Indian phone; replaced with placeholders','inputs':all_hashes,'counts':dict(counts),'counts_by_language':{f'{lang}:{stage}':n for (lang,stage),n in sorted(bylang.items())},'counts_by_source':dict(source_counts),'selection_policy':{'wiki_max_selected_records':20000,'hinglish_max_selected_records':6000,'selection_order':'first 20,000 namespace-0 wiki pages with text and first 6,000 PHINC logical records in pinned source order; all later source records are streamed to ledger as source_quota drops'},'near_duplicate_examples':'near_duplicate_examples.jsonl','eval_candidate_reviews':'eval_candidate_reviews.jsonl','eval_items':eval_n,'reproducibility':'Each invocation builds a fresh staging directory, writes deterministic JSONL in sorted file/input order, then atomically swaps the completed directory into place. Interrupted staging is not treated as output; rerun replaces it.'}
        (stage/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        # sqlite is an implementation artifact, not part of the deliverable output.
        for q in stage.glob('index.sqlite*'): q.unlink(missing_ok=True)
        backup=out.with_name(out.name+'.previous')
        if backup.exists(): shutil.rmtree(backup)
        if out.exists(): os.replace(out,backup)
        os.replace(stage,out)
        if backup.exists(): shutil.rmtree(backup)
        print(json.dumps(manifest,ensure_ascii=False,indent=2))
    except Exception:
        cleanf.close(); ledger.close(); evalf.close(); contf.close(); db.close()
        # Leave failed staging for forensic inspection, never publish it as final output.
        raise

if __name__=='__main__':
    if len(sys.argv)!=3: raise SystemExit('Usage: pipeline.py <raw_dir> <out_dir>')
    main(sys.argv[1],sys.argv[2])
