# NuclearGroudBench
A consolidated benchmark for Grounded Natural Language to QA on Technical Nuclear-related documents

# TU Corpus — Annotated QnA Dataset

## Overview
A knowledge-grounded annotated question and answer dataset built from 67 institutional 
documents spanning 1966–2012. The corpus covers two document types, progress reports 
and action reports.

## Corpus structure
| Series | Original prefix | Period      | Type             | Count |
|--------|----------------|-------------|------------------|-------|
| SR     | TUSR           | 1966–1985   | Progress reports | 40    |
| AR     | TUAR / TUar    | 1986–2013   | Action reports   | 27    |

## Folder structure

```
corpus/
├── AR_001.pdf … AR_027.pdf    ← action reports
├── SR_001.pdf … SR_040.pdf    ← progress reports
questions.ttl                  ← Q&A pairs with annotations
eurovoc_special.ttl            ← domain vocabulary aligned to EuroVoc
README.md
```

## Cloning with Git LFS
```bash
git clone https://github.com/yourname/yourrepo.git
cd yourrepo
git lfs pull
```

## ID scheme
Each document has a stable two-part ID: series prefix + zero-padded number.
- `SR_001` — first progress report (1966)
- `AR_001` — first action report (1985)

These IDs are used as URIs in the TTL knowledge files, e.g. `ex:SR_001`.

## Knowledge files
- `questions.ttl` — encodes each question, answer, source document reference,
   EuroVoc term, and ground truth annotation
- `eurovoc_special.ttl` — maps domain-specific terms to EuroVoc concepts

## Citation
