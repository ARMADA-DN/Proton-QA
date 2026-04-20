# PROTON-QA
A consolidated benchmark for Grounded Natural Language to QA on Technical Nuclear-related documents

## Overview
A knowledge-grounded annotated question and answer dataset built from 67 institutional 
documents spanning 1966–2013. The corpus covers two document types: progress reports 
and action reports.

## Corpus Structure
| Series | Period      | Type             | Count |
|--------|-------------|------------------|-------|
| SR     | 1966–1985   | Progress reports | 40    |
| AR     | 1986–2013   | Action reports   | 27    |

## Naming Convention
Each document follows a three-part ID: `{type}_{YY}_{sequence}`

| Part       | Description                                              |
|------------|----------------------------------------------------------|
| `type`     | Document type — `SR` (progress report) or `AR` (action report) |
| `YYYY`       | Last two digits of the year (e.g., `1986` for 1986)       |
| `sequence` | Sequence number within the same year (e.g., quarterly)  |

**Examples:**
- `AR_1986_1.pdf` — first action report of 1986
- `SR_1966_1.pdf` — first progress report of 1966

These IDs are used as URIs in the TTL knowledge files, e.g. `ex:AR_86_1`.

## Repository Structure

```
repo-root/
├── corpus/                               # Documents (stored via Git LFS)
│   ├── AR_YYYY_seq.pdf                  # Action Reports (27 files)
│   └── SR_YYYY_seq.pdf                  # Progress Reports (40 files)
│
├── vocab/
│   ├── eurovoc_in_skos_core_concepts.rdf  # EuroVoc vocabulary (SKOS)
│   └── concept_extensions.ttl             # Custom domain concepts
│
├── questions.ttl                         # Q&A pairs with semantic annotations
└── README.md                             # Project documentation
```


## Knowledge Files


### `questions.ttl`
Encodes each question, answer, source document reference, EuroVoc term, and ground 
truth annotation. Questions and answers are explicitly linked using:
- `schema:acceptedAnswer` — high-confidence answers
- `schema:suggestedAnswer` — lower-confidence answers

Provenance is tracked separately via PROV. This makes question–answer relations 
direct and easy to query while preserving full provenance.

### `nuclear-bench.owl.ttl`
OWL ontology defining the benchmark schema. 
Note: currently under review — 


### `vocab/concept_extensions.ttl`
Extends existing vocabularies (EuroVoc, Wikidata) with domain-specific terms not 
found in either. Follows SKOS conventions (aligned with EuroVoc).

Current terms:
- `PuCoGa5`
- `PuRhGa5`
- `Dissolution rate`

Concepts are defined under the `ex:` prefix.

> **Note:** EuroVoc follows SKOS conventions. Wikidata does not — it uses its own 
> ontology and is not a controlled vocabulary.

## Naming Convention for Knowledge Entities

| Entity                   | ID Pattern                        | Example                          |
|--------------------------|-----------------------------------|----------------------------------|
| Question                 | `ex:{docID}_q{n}`                 | `ex:AR_2000_0_q3`                  |
| Answer                   | `ex:{docID}_q{n}_a{m}`            | `ex:AR_2000_0_q3_a1`               |
| Provenance               | `ex:{docID}_q{n}_src`             | `ex:AR_2000_0_q3_src`              |
| Annotation (term-specific)| `ex:{docID}_q{n}_ann_{term}`     | `ex:AR_2000_0_q3_ann_latticeparameter` |

This ensures consistency and full traceability back to the source document across 
questions, answers, provenance, and annotations.

## Cloning with Git LFS
```bash
git clone https://github.com/ARMADA-DN/NuclearGroundBench.git
cd NuclearGroundBench
git lfs pull
```

## Git LFS Tracked Files
The following file types are managed via Git LFS:
- `*.ttl` — all Turtle/RDF files
- `corpus/*.pdf` — all corpus documents

## Citation
*To be added.*

## TODO
domain to be registered 
https://w3id.org/proton-qa/
Prefix - pqa 