# PROTON-QA
A consolidated benchmark for Grounded Natural Language to QA on Technical Nuclear-related documents

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.XXXXXXX.svg)](https://doi.org/10.5281/zenodo.XXXXXXX)

## Overview
A knowledge-grounded annotated question and answer dataset built from 67 institutional 
documents spanning 1966–2013. The corpus covers two document types: progress reports 
and action reports.

PROTON-QA addresses four key gaps in existing domain-specific benchmarks:
1. Document provenance traceability for grounding questions and answers
2. Unit-aware numerical answer representation
3. Concept-level entity linking for semantic interoperability
4. Ontology-grounded representation enabling reasoning over diverse answer types

## Corpus Structure
| Series | Period      | Type             | Count |
|--------|-------------|------------------|-------|
| SR     | 1966–1985   | Progress reports | 40    |
| AR     | 1986–2013   | Action reports   | 27    |

## Naming Convention
Each document follows a three-part ID: `{type}_{YYYY}_{sequence}`

| Part       | Description                                                     |
|------------|-----------------------------------------------------------------|
| `type`     | Document type — `SR` (progress report) or `AR` (action report) |
| `YYYY`     | Full four-digit year (e.g., `2000` for 2000)                    |
| `sequence` | Sequence number within the same year (e.g., quarterly)          |

**Examples:**
- `AR_2000_0.pdf` — first action report of 2000
- `SR_1966_1.pdf` — first progress report of 1966

These IDs are used as URIs in the TTL knowledge files, e.g. `pqa:AR_2000_0`.

## Repository Structure



```
repo-root/
├── LICENSE                                # MIT License
├── croissant.jsonld                       # Croissant dataset metadata
├── croissant.ttl                          # Croissant metadata in Turtle format
├── README.md                              # Project documentation
│
├── corpus/                                # Documents (stored via Git LFS)
│   ├── AR_YYYY_seq.pdf                   # Action Reports (27 files)
│   └── SR_YYYY_seq.pdf                   # Progress Reports (40 files)
│
├── vocab/
│   ├── eurovoc_in_skos_core_concepts.rdf  # EuroVoc vocabulary (SKOS)
│   ├── concept_extensions.ttl             # Custom domain concepts
│   ├── qudt.ttl                           # QUDT core ontology (quantities & dimensions)
│   └── qudt-unit.ttl                      # QUDT units vocabulary
│
└── questions.ttl                          # Q&A pairs with semantic annotations

```

## Knowledge Files

### `questions.ttl`
Encodes each question, answer, source document reference, entity linking annotations,
and provenance. Questions and answers are explicitly linked using:
- `schema:acceptedAnswer` — high-confidence gold standard answers
- `schema:suggestedAnswer` — alternative candidate answers with lower confidence

Provenance is tracked via the W3C Open Annotation (`oa:`) and PROV-O (`prov:`) 
vocabularies, linking each answer to a specific page in the source document.
Units are represented using the QUDT vocabulary.

### `vocab/concept_extensions.ttl`
Extends existing vocabularies (EuroVoc, Wikidata) with domain-specific terms not 
found in either. Follows SKOS conventions and is aligned with EuroVoc.

Current custom concepts (`pqa:` namespace):

| Term | Description | SKOS Mapping |
|---|---|---|
| `pqa:MgAmO2` | Magnesium Americium Oxide | `skos:relatedMatch` wd:Q898519 |
| `pqa:LatticeParameter` | Lattice parameter / constant | `skos:exactMatch` wd:Q625641 |
| `pqa:DissolutionRate` | Rate of solid dissolution in liquid | `skos:closeMatch` wd:Q3133701 |
| `pqa:PNCC` | Passive Neutron Coincidence Counting | `skos:narrowMatch` wd:Q60552688 |
| `pqa:HRGS` | High Resolution Gamma Spectrometry | `skos:closeMatch` wd:Q906816 |
| `pqa:ActinideCe115Family` | Actinide 115 family compounds | `skos:relatedMatch` wd:Q5695236 |
| `pqa:IrradiatedFuel` | Irradiated / spent nuclear fuel | `skos:closeMatch` wd:Q1863171 |
| `pqa:DIAMEX` | DIAMide EXtraction process | `skos:broader` wd:Q386477 |

> **Note:** EuroVoc follows SKOS conventions. Wikidata does not — it uses its own 
> ontology and is not a controlled vocabulary.

## Naming Convention for Knowledge Entities

| Entity                    | ID Pattern                       | Example                            |
|---------------------------|----------------------------------|------------------------------------|
| Question                  | `pqa:q{n}`                       | `pqa:q1`                           |
| Answer                    | `pqa:q{n}_a{m}`                  | `pqa:q1_a1`                        |
| Provenance annotation     | `pqa:q{n}_src{m}`                | `pqa:q1_src1`                      |
| Entity linking annotation | `pqa:q{n}_ann_{term}`            | `pqa:q1_ann_magnesia`              |
| Source document           | `pqa:{type}_{YYYY}_{seq}`        | `pqa:AR_2000_0`                    |

## Prefixes Used

| Prefix | Namespace |
|--------|-----------|
| `pqa:` | `https://w3id.org/proton-qa/resource#` |
| `qa:`  | `https://w3id.org/wdaqua/qanary#` |
| `oa:`  | `http://www.w3.org/ns/oa#` |
| `prov:`| `http://www.w3.org/ns/prov#` |
| `qudt:`| `http://qudt.org/schema/qudt/` |
| `unit:`| `http://qudt.org/vocab/unit/` |
| `wd:`  | `http://www.wikidata.org/entity/` |
| `skos:`| `http://www.w3.org/2004/02/skos/core#` |

## Croissant Metadata
This dataset includes a [Croissant](https://docs.mlcommons.org/croissant/) metadata 
file (`croissant.jsonld`) for machine-readable dataset description, compatible with 
Google Dataset Search and ML frameworks.

To validate:
```bash
mlcroissant validate --jsonld croissant.jsonld
```

To convert to Turtle:
```bash
riot --output=turtle croissant.jsonld > croissant.ttl
riot --validate croissant.ttl
```

## Cloning with Git LFS
```bash
git clone https://github.com/ARMADA-DN/Proton-QA.git
cd Proton-QA
git lfs pull
```

## Git LFS Tracked Files
The following file types are managed via Git LFS:
- `*.pdf` — all corpus documents

## Authors
- Thushari Pahalage Dona
- Antonio Bulgheroni
- Lorenzo Fongaro
- Matteo Lissandrini

## Citation
*To be added after Zenodo publication.*

## License
This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

## TODO
- [ ] Register domain `https://w3id.org/proton-qa/`
- [ ] Zenodo publication and DOI assignment

