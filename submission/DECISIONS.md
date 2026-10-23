# DECISIONS

## Sources and observed funnel
- Hindi Wikipedia 2026-10-01 snapshot: 246,802 namespace-0 records seen; first 20,000 selected; 17,902 retained; 251,878,194 bytes; SHA-256 `a10c4915880277d518585c74ee294fd8d6e8158f85bc2ec07a0b83e94e2234c3`; CC BY-SA 4.0.
- PHINC commit-pinned CSV: 13,738 logical records seen; first 6,000 selected; 5,789 retained; 2,125,039 bytes; SHA-256 `325ba383cd6d73e0c3128885e2a79133e612ec03d18c8b55506d0b4b12ec68ed`; CC BY 4.0 per dataset card.
Total: 260,540 source records streamed; 26,000 selected; 25,658 passed quality; 23,691 training rows kept; 200 held out; 0 parse failures.

| Label | Input | Selected | Eval | Quality drop | Exact | Near | Contam. | Kept | Quota drop |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| en | 3,410 | 1,340 | 25 | 0 | 5 | 1 | 0 | 1,309 | 2,070 |
| hi | 245,608 | 19,826 | 2 | 0 | 1,720 | 236 | 0 | 17,868 | 225,782 |
| hi-Latn | 11,382 | 4,694 | 173 | 0 | 2 | 3 | 2 | 4,514 | 6,688 |
| other | 140 | 140 | 0 | 140 | 0 | 0 | 0 | 0 | 0 |

## Cleaning and dedupe decisions
Quality filters: empty=140. All 140 empty drops were labeled `other`; spot checks confirmed template/category-only pages with no Hindi, Hinglish, or English body text. This is the explicit false-positive review: none found in the only triggered quality rule. A bounded `<ref>` parser fix recovers article prose when a malformed citation appears in an otherwise valid article. Other guards cover short strings, markup residue, URL-heavy content, low letter content, replacement glyphs, and repetitive spam; they did not trigger in this run.
Exact duplicates compare normalized, redacted text. Near duplicates use 64-bit character 5-gram SimHash; remove at Hamming <=6, Jaccard >=0.82, and equal numeric-token sequences (digits in handles/URLs ignored). Three reviewed near-threshold pairs:
1. H6/J0.820 drop: `सौल_बेल् अमेरिका का राष्ट्रिय पुस्तक पुरस्कार विजेता` ↔ `अमेरिका का राष्ट्रिय पुस्तक पुरस्कार विजेता` (IDs ae653cdf7748a656cbb1, 347f73688dd3ea6d8f99).
2. H6/J0.820 drop: `Wow yar Pakistani khawateen to kaam ki nikleen ! Congratulations ` ↔ `rt @saadhere_ : wow yar pakistani khawateen to kaam ki nikleen ! ` (IDs c8ecb360c3a4f4b2099d, 3c51c7766123426e8135).
3. H8/J0.819 keep: `मा बु चिंग चीन में एक मुखिया था जळि बिसवान शताब्दी मैं। किताब जनम` ↔ `मा हांग बिन (1884-1960 馬鴻賓) चीन में एक मुखिया था जळि बिसवान शताब्` (IDs c16babf08f8010820a94, 3ae4a9f3306c3c00ae6c).

## Holdout and operations
The 200-row deterministic PHINC holdout tests train/eval leakage; it is excluded from training before dedupe and screened against normalized text, transliteration, and near matches. The contamination gate is H<=16/J>=0.70 with matching numeric content. This is approximate, not proof of zero leakage.
Removed 2 contaminated training row(s) affecting 2 eval item(s). Example eval `009083ae6854f160f19e` ↔ train `946df374f15ecec1440f`; same post with changed @mention / RT text, verified as a copy.
Rejected candidate: eval `04a857a8e7220fb93f69` and train `043b4497413d9f29815c` at H16/J0.329; shared campaign hashtag, different message bodies, so below removal gate.
Rebuild: `./download.sh` then `./run.sh raw out`; raw sources are hash-pinned and unchanged. Outputs are staged and atomically published; a rerun starts clean and does not resume. For 2 TB: partition to object storage, checkpoint manifests, distribute parsing, and shard/global-route dedupe candidates. Not done: production-grade LID, broad manual quality/PII audit, semantic paraphrase detection, or mid-run resume. Actual candidate time spent: **enter your honest end-to-end time before submitting**.
