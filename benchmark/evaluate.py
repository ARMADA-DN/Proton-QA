"""
ProtonQA Provenance Evaluator
===================================
Evaluates a RAG system's ability to correctly locate answers
within the PROTON-QA benchmark corpus.

Provenance is the core claim of PROTON-QA: every answer must be
traceable to a specific document and page. This script checks only
that — not whether the answer value itself is correct.

Design principles
-----------------
1. All valid source locations (accepted + suggested answer provenance)
   form the ground truth for retrieval — not just the expert-selected
   accepted answer. This reflects the benchmark goal of discovering
   every valid source.

2. Retrieval is evaluated with both Recall and Precision.
   Recall measures coverage (did the system find all valid sources?).
   Precision measures relevance (are retrieved sources actually valid?).

3. Evidence is matched by normalised exact substring — the benchmark
   stores verbatim quotations and the prompt instructs exact copying.
   Because the oa:exact quotes are manually curated by domain experts,
   a RAG system may retrieve a different sentence from the correct page
   that equally supports the answer. Evidence Exact should therefore be
   interpreted as alignment with the expert-selected quotation, not as
   a binary retrieval pass/fail. Evidence ROUGE-1 F1 is reported as a
   supplementary softer metric and proposed as the primary evidence
   measure in future work.

Five provenance dimensions (weighted → Overall score)
------------------------------------------------------
  1. Document Recall    — fraction of GT documents retrieved            (15%)
  2. Document Precision — fraction of retrieved documents that are valid (10%)
  3. Page Recall        — fraction of GT (document, page) pairs retrieved(30%)
  4. Page Precision     — fraction of retrieved pages that are valid     (20%)
  5. Evidence Exact     — normalised exact substring match of oa:exact   (25%)

Ground truth for all five dimensions comes directly from the TTL:
  prov:hadPrimarySource  → source document   (accepted + suggested)
  oa:FragmentSelector    → page number        (accepted + suggested)
  oa:exact               → verbatim quote     (accepted answer only)

Four supplementary answer quality metrics (informational — not weighted)
------------------------------------------------------------------------
  Value Match           — numeric value within 2% tolerance; ROUGE-1 fallback for text
  Unit Match            — normalised unit string comparison against GT label
  Uncertainty Provided  — whether the system reported uncertainty when GT requires it
  Evidence ROUGE-1      — unigram token overlap between retrieved text and oa:exact quote

Usage
-----
    pip install rdflib

    python evaluate.py validate \\
        --ttl      questions.ttl \\
        --answers  notebooklm_output.json \\
        --ids      q1 q2 q3 q4 q5 q6 q7 q8 q9 q10 \\
        --out      provenance_results.csv

    python evaluate.py metrics --results provenance_results.csv
"""

import argparse, csv, json, re, unicodedata
from pathlib import Path

from rdflib import Graph, Namespace
from rdflib.namespace import RDF, RDFS

# ── Namespaces ────────────────────────────────────────────────────────────────
SCHEMA = Namespace("https://schema.org/")
QA     = Namespace("https://w3id.org/wdaqua/qanary#")
PQA    = Namespace("https://w3id.org/proton-qa/resource#")
QUDT   = Namespace("http://qudt.org/schema/qudt/")
PROV   = Namespace("http://www.w3.org/ns/prov#")
OA     = Namespace("http://www.w3.org/ns/oa#")

# ── Weights ───────────────────────────────────────────────────────────────────
WEIGHTS = {
    "Document Recall":    0.15,
    "Document Precision": 0.10,
    "Page Recall":        0.30,
    "Page Precision":     0.20,
    "Evidence Exact":     0.25,
}

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def safe_div(n, d):
    return n / d if d else 0.0

def _strip_pdf(name):
    return str(name or "").replace(".pdf", "").replace(".PDF", "").strip()

def _extract_qid(obj):
    """Extract question_id — handles '[Q9]' embedded in question string."""
    for k in ("question_id", "id", "qid"):
        v = str(obj.get(k, "")).strip()
        if v:
            num = re.sub(r"\D", "", v)
            return f"q{int(num)}" if num else None
    m = re.search(r"\[Q(\d+)\]", str(obj.get("question", "")), re.IGNORECASE)
    return f"q{int(m.group(1))}" if m else None

def _split_value_unc(val_str):
    """Split '3250±20' → ('3250', '20'), else (val_str, '')."""
    m = re.match(r"^([\d.eE+\-]+)\s*(?:[±]|\+/-)\s*([\d.]+)$",
                 str(val_str).strip())
    return (m.group(1), m.group(2)) if m else (val_str, "")

def _normalise_text(s):
    """
    Normalise text for exact match comparison:
      - NFKC unicode normalisation (handles ± ≥ etc.)
      - collapse whitespace to single space
      - strip leading/trailing whitespace
    Case is preserved — units like 'K', 'MeV' are case-sensitive.
    """
    s = unicodedata.normalize("NFKC", str(s or ""))
    return re.sub(r"\s+", " ", s).strip()


# ─────────────────────────────────────────────────────────────────────────────
# Ground truth extraction from TTL
# ─────────────────────────────────────────────────────────────────────────────

def _get_provenance(g, ans_uri):
    """
    Extract (document, page) and verbatim quote from one answer URI.
    Returns: doc str, page str, quote str
    """
    doc = page = quote = ""
    src = g.value(ans_uri, PROV.hadPrimarySource)
    if src:
        doc = str(src).split("#")[-1].split("/")[-1]
    for ann_uri in g.subjects(OA.hasBody, ans_uri):
        tgt = g.value(ann_uri, OA.hasTarget)
        if not tgt:
            continue
        sel = g.value(tgt, OA.hasSelector)
        if not sel:
            continue
        pv = g.value(sel, RDF.value)
        if pv:
            page = str(pv).replace("page=", "").split("&")[0]
        ref = g.value(sel, OA.refinedBy)
        if ref:
            qv = g.value(ref, OA.exact)
            if qv:
                quote = str(qv)
    return doc, page, quote


def load_ground_truth(ttl_path, target_ids=None):
    """
    Extract provenance ground truth from the benchmark TTL.

    Ground truth for retrieval = union of ALL valid source locations:
      - prov:hadPrimarySource / oa:FragmentSelector of the accepted answer
      - prov:hadPrimarySource / oa:FragmentSelector of every suggested answer

    This reflects the benchmark goal: the system should discover every
    valid source, not only the expert-selected accepted answer.

    Returned structure per question:
    {
      "question_id":       "q1",
      "question":          "What is the melting point...",
      "gt_answer_label":   "3245 ± 10 K",          # display only, not scored
      "all_provenance":    [                         # UNION of all sources
          {"document": "AR_2000_0", "page": "20"},
          {"document": "AR_2000_0", "page": "80"},
          ...
      ],
      "supporting_evidence": [                       # oa:exact from accepted answer
          {"document": "...", "page": "...", "text": "..."}
      ],
    }
    """
    g = Graph()
    g.parse(ttl_path, format="turtle")
    out = {}

    for q_uri in g.subjects(RDF.type, QA.Question):
        q_id = str(q_uri).split("#")[-1].split("/")[-1]
        if target_ids and q_id not in target_ids:
            continue

        label    = str(g.value(q_uri, RDFS.label) or "")
        acc_uris = list(g.objects(q_uri, SCHEMA.acceptedAnswer))
        sug_uris = list(g.objects(q_uri, SCHEMA.suggestedAnswer))
        all_ans  = list(set(acc_uris) | set(sug_uris))
        if not all_ans:
            continue

        a_uri    = acc_uris[0] if acc_uris else sug_uris[0]
        gt_label = str(g.value(a_uri, RDFS.label) or "")

        # ── Build unified provenance ground truth ─────────────────────────────
        # Collect (doc, page) from every answer URI — accepted + suggested.
        # Diagnostic: flag suggested answers missing provenance so the
        # benchmark curator knows which TTL entries need completing.
        seen_prov = set()
        all_provenance = []
        supporting_evidence = []
        incomplete = []

        for ans_uri in all_ans:
            doc, page, quote = _get_provenance(g, ans_uri)
            is_suggested = (ans_uri != a_uri)

            if not doc:
                # Suggested answer has no provenance annotation at all
                if is_suggested:
                    local = str(ans_uri).split("#")[-1].split("/")[-1]
                    incomplete.append(f"{local} (no doc)")
                continue

            # Suggested answer has document but no page annotation
            if is_suggested and not page:
                local = str(ans_uri).split("#")[-1].split("/")[-1]
                incomplete.append(f"{local} (doc={doc}, page missing)")

            key = (doc, page)
            if key not in seen_prov:
                seen_prov.add(key)
                all_provenance.append({
                    "document": doc,
                    "page":     page,
                    "annotated": bool(page),  # False = doc-only, no page
                })

            # Keep verbatim quote only from the accepted answer
            if ans_uri == a_uri and quote:
                supporting_evidence.append({
                    "document": doc,
                    "page":     page,
                    "text":     quote,
                })

        if incomplete:
            print(f"  ⚠  [{q_id}] {len(incomplete)} suggested answer(s) "
                  f"with incomplete provenance: {incomplete}")

        out[q_id] = {
            "question_id":        q_id,
            "question":           label,
            "gt_answer_label":    gt_label,
            "all_provenance":     all_provenance,
            "supporting_evidence": supporting_evidence,
        }

    return dict(sorted(out.items(),
                        key=lambda x: int(re.sub(r"\D", "", x[0]) or 0)))


# ─────────────────────────────────────────────────────────────────────────────
# Normalise prediction JSON → common schema
# ─────────────────────────────────────────────────────────────────────────────

def normalise_pred(raw):
    """
    Accept both structured (accepted_answer dict) and flat formats.
    Strips .pdf suffix. Extracts question_id from '[Q1]' pattern.
    Collects ALL predicted (document, page) pairs into retrieved_documents
    from: retrieved_documents + accepted_answer + suggested_answers.
    """
    q_id = _extract_qid(raw)

    def clean_locs(lst):
        return [{"document": _strip_pdf(d.get("document", "")),
                 "page":     str(d.get("page", ""))}
                for d in (lst or []) if d.get("document")]

    def clean_ev(lst):
        return [{"document": _strip_pdf(e.get("document", "")),
                 "page":     str(e.get("page", "")),
                 "text":     e.get("text", "") or e.get("verbatim_text", "")}
                for e in (lst or [])
                if e.get("text") or e.get("verbatim_text")]

    if "accepted_answer" in raw and isinstance(raw["accepted_answer"], dict):
        acc = raw["accepted_answer"]
        val, unc = _split_value_unc(str(acc.get("value", "")))

        # Collect ALL predicted source locations into one list
        all_pred_locs = []
        seen = set()

        def _add_loc(doc, page):
            doc = _strip_pdf(doc)
            key = (doc, str(page))
            if doc and key not in seen:
                seen.add(key)
                all_pred_locs.append({"document": doc, "page": str(page)})

        # From retrieved_documents
        for d in (raw.get("retrieved_documents") or []):
            _add_loc(d.get("document", ""), d.get("page", ""))
        # From accepted_answer
        _add_loc(acc.get("document", ""), acc.get("page", ""))
        # From suggested_answers
        for s in (raw.get("suggested_answers") or []):
            _add_loc(s.get("document", ""), s.get("page", ""))

        return {
            "question_id":         q_id,
            "accepted_answer":     {"value":    val,
                                    "document": _strip_pdf(acc.get("document", "")),
                                    "page":     str(acc.get("page", ""))},
            "retrieved_documents": all_pred_locs,
            "supporting_evidence": clean_ev(raw.get("supporting_evidence", [])),
        }

    # Flat format fallback
    doc  = _strip_pdf(raw.get("document", ""))
    page = str(raw.get("page", ""))
    return {
        "question_id":    q_id,
        "accepted_answer": {"value":    str(raw.get("answer", "") or ""),
                            "document": doc, "page": page},
        "retrieved_documents": [{"document": doc, "page": page}] if doc else [],
        "supporting_evidence": [{"document": doc, "page": page,
                                  "text": raw.get("verbatim_text", "")
                                           or raw.get("verbatim", "")}]
                                if raw.get("verbatim_text") else [],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Provenance scorers
# ─────────────────────────────────────────────────────────────────────────────

def _gold_docs(gold):
    return {d["document"]
            for d in gold.get("all_provenance", [])
            if d.get("document")}

def _pred_docs(pred):
    return {d["document"]
            for d in pred.get("retrieved_documents", [])
            if d.get("document")}

def _gold_pages(gold):
    return {(d["document"], str(d["page"]))
            for d in gold.get("all_provenance", [])
            if d.get("document") and d.get("page")}

def _pred_pages(pred):
    return {(d["document"], str(d["page"]))
            for d in pred.get("retrieved_documents", [])
            if d.get("document") and d.get("page")}


def score_document_recall(gold, pred):
    """
    Fraction of ground truth source documents retrieved.
    Ground truth = union of prov:hadPrimarySource across all answer URIs.
    1.0 = every valid annual report was found.
    """
    gd = _gold_docs(gold)
    pd = _pred_docs(pred)
    if not gd:
        return 1.0
    return safe_div(len(pd & gd), len(gd))


def score_document_precision(gold, pred):
    """
    Fraction of retrieved documents that are valid source documents.
    1.0 = system retrieved only relevant annual reports.
    0.0 = system retrieved nothing, or only irrelevant documents.
    """
    gd = _gold_docs(gold)
    pd = _pred_docs(pred)
    if not pd:
        return 0.0
    return safe_div(len(pd & gd), len(pd))


def score_page_recall(gold, pred):
    """
    Fraction of ground truth (document, page) pairs retrieved.
    Ground truth = union of oa:FragmentSelector across all answer URIs.
    1.0 = every valid source page was located.
    """
    gp = _gold_pages(gold)
    pp = _pred_pages(pred)
    if not gp:
        return 1.0
    return safe_div(len(pp & gp), len(gp))


def score_page_precision(gold, pred):
    """
    Fraction of retrieved (document, page) pairs that are valid.
    1.0 = system retrieved only relevant pages.
    0.0 = system retrieved nothing, or only irrelevant pages.
    """
    gp = _gold_pages(gold)
    pp = _pred_pages(pred)
    if not pp:
        return 0.0
    return safe_div(len(pp & gp), len(pp))


def score_evidence_exact(gold, pred):
    """
    Normalised exact substring match between predicted supporting text
    and the verbatim quote stored in oa:exact in the TTL.

    For each gold evidence text, score 1 if any predicted supporting
    evidence contains it as a substring (or is contained by it) after
    unicode normalisation and whitespace collapsing.

    Returns 1.0 if the TTL has no verbatim quote (no penalty).
    Returns 0.0 if supporting evidence is missing from the prediction.

    Interpretation note:
      The oa:exact quote is manually curated by a domain expert and
      reflects the curator's chosen representative sentence. A RAG
      system may retrieve a different sentence from the same page that
      equally supports the answer. A score below 1.0 therefore does not
      necessarily indicate a retrieval failure — it may reflect divergence
      between the expert-selected quote and the sentence the retriever
      surfaces. Page Recall and Page Precision are the primary provenance
      indicators; Evidence Exact measures alignment with the manual
      annotation specifically.
    """
    gold_ev = [_normalise_text(e["text"])
               for e in gold.get("supporting_evidence", [])
               if e.get("text")]
    pred_ev = [_normalise_text(e["text"])
               for e in pred.get("supporting_evidence", [])
               if e.get("text")]

    if not gold_ev:
        return 1.0
    if not pred_ev:
        return 0.0

    matched = 0
    for gtext in gold_ev:
        for ptext in pred_ev:
            # Accept if gold is substring of pred (pred quoted more context)
            # or pred is substring of gold (pred quoted a fragment)
            if gtext in ptext or ptext in gtext:
                matched += 1
                break

    return safe_div(matched, len(gold_ev))


# ─────────────────────────────────────────────────────────────────────────────
# Answer quality scorers (supplementary — not weighted into Overall)
# ─────────────────────────────────────────────────────────────────────────────

UNIT_NORM_AQ = {
    "k":"K","kelvin":"K",
    "day":"DAY","days":"DAY","d":"DAY",
    "min":"MIN","minutes":"MIN",
    "a":"ANGSTROM","å":"ANGSTROM","angstrom":"ANGSTROM",
    "pm":"PicoM","nm":"NanoM","m":"M",
    "displacements":"NUM","defects":"NUM",
    "n/a":"","na":"","%":"PERCENT",
    "mol m-2 s-1":"MOL-PER-M2-SEC","mol/m2/s":"MOL-PER-M2-SEC",
}

def _aq_norm_unit(u):
    return UNIT_NORM_AQ.get((u or "").strip().lower(), (u or "").strip().upper())

def _parse_num(s):
    m = re.search(r"[-+]?\d+\.?\d*(?:[eE][-+]?\d+)?", str(s).replace(",",""))
    return float(m.group()) if m else None

def _rouge1_f1(hyp, ref):
    """ROUGE-1 F1 via unigram token overlap — no external dependencies."""
    h = set(_normalise_text(hyp).split())
    r = set(_normalise_text(ref).split())
    if not r: return 1.0
    if not h: return 0.0
    ov = h & r
    p  = len(ov) / len(h)
    rc = len(ov) / len(r)
    return 2 * p * rc / (p + rc) if (p + rc) > 0 else 0.0

def _gt_unit_from_label(label):
    """Extract trailing unit token from a GT label like '3245 ± 10 K'."""
    parts = str(label).strip().split()
    for part in reversed(parts):
        if not re.match(r'^[\d.±eE+\-]+$', part):
            return part
    return ""

def score_value_match(gt_label, pred_val, tol=0.02):
    """
    Numeric value match within 2% tolerance.
    Falls back to ROUGE-1 F1 for non-numeric answers (e.g. technique lists).
    """
    pn = _parse_num(str(pred_val or ""))
    gn = _parse_num(str(gt_label or ""))
    if pn is None or gn is None:
        return _rouge1_f1(str(pred_val or ""), str(gt_label or ""))
    if gn == 0:
        return 1.0 if abs(pn) <= tol else 0.0
    return 1.0 if safe_div(abs(pn - gn), abs(gn)) <= tol else 0.0

def score_unit_match_aq(gt_label, pred_unit):
    """
    Unit string match between GT label unit and predicted unit.
    Returns 1.0 when GT has no unit (not required).
    """
    gu = _aq_norm_unit(_gt_unit_from_label(str(gt_label or "")))
    pu = _aq_norm_unit(str(pred_unit or ""))
    if not gu:
        return 1.0
    return 1.0 if pu == gu else 0.0

def score_uncertainty_provided(gt_label, pred_unc):
    """
    1.0 if GT has no uncertainty (not required).
    1.0 if GT has uncertainty AND system filled the uncertainty field.
    0.0 if GT has uncertainty AND system left the field empty.
    """
    has_unc    = "±" in str(gt_label)
    pred_filled = bool(str(pred_unc or "").strip())
    if not has_unc:
        return 1.0
    return 1.0 if pred_filled else 0.0

def score_evidence_rouge1(gold, raw_pred):
    """
    ROUGE-1 F1 between predicted supporting evidence text and the
    oa:exact verbatim quote in the TTL.

    Softer than Evidence Exact — rewards partial token overlap.
    Proposed as the primary evidence metric in future work to account
    for the expected divergence between manually curated quotes and
    the sentences independently surfaced by the retriever.

    Returns 1.0 if the TTL has no verbatim quote (no penalty).
    """
    gold_ev = [e["text"]
               for e in gold.get("supporting_evidence", [])
               if e.get("text")]
    pred_ev = [e.get("text", "") or e.get("verbatim_text", "")
               for e in (raw_pred.get("supporting_evidence") or [])
               if e.get("text") or e.get("verbatim_text")]
    if not gold_ev:
        return 1.0
    if not pred_ev:
        return 0.0
    per_pred = [max(_rouge1_f1(pt, gt) for gt in gold_ev) for pt in pred_ev]
    return sum(per_pred) / len(per_pred)

def compute_answer_quality(gt_label, raw_pred):
    """
    Compute supplementary answer quality metrics from the raw prediction JSON.
    These are informational — they do not contribute to the provenance Overall score.
    """
    acc = raw_pred.get("accepted_answer", {}) if isinstance(raw_pred, dict) else {}
    return {
        "Value Match":          score_value_match(gt_label, acc.get("value", "")),
        "Unit Match":           score_unit_match_aq(gt_label, acc.get("unit", "")),
        "Uncertainty Provided": score_uncertainty_provided(gt_label, acc.get("uncertainty", "")),
    }


def compute_scores(gold, pred):
    """Compute all five provenance dimensions and weighted overall."""
    s = {
        "Document Recall":    score_document_recall(gold, pred),
        "Document Precision": score_document_precision(gold, pred),
        "Page Recall":        score_page_recall(gold, pred),
        "Page Precision":     score_page_precision(gold, pred),
        "Evidence Exact":     score_evidence_exact(gold, pred),
    }
    s["Overall"] = sum(s[k] * WEIGHTS[k] for k in WEIGHTS)
    return s


# ─────────────────────────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────────────────────────

def cmd_validate(ttl, answers_path, target_ids, out_path):
    gt_all = load_ground_truth(ttl, target_ids)
    print(f"Ground truth loaded : {len(gt_all)} questions")

    raw = Path(answers_path).read_text(encoding="utf-8").strip()
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)
    preds_raw = json.loads(raw)
    if isinstance(preds_raw, dict):
        preds_raw = [preds_raw]

    pred_map = {}   # qid → (raw_pred, normalised_pred)
    for p in preds_raw:
        np_ = normalise_pred(p)
        qid = np_.get("question_id")
        if qid:
            pred_map[qid] = (p, np_)

    print(f"Predictions parsed  : {len(pred_map)} ({sorted(pred_map.keys())})")

    AQ_KEYS = ["Value Match", "Unit Match", "Uncertainty Provided", "Evidence ROUGE-1"]

    rows = []
    for q_id, gold in gt_all.items():
        entry = pred_map.get(q_id)

        if not entry:
            sc = {k: 0.0 for k in WEIGHTS}
            sc["Overall"] = 0.0
            rows.append({
                "question_id":    q_id,
                "question":       gold["question"][:80],
                "gt_answer":      gold["gt_answer_label"],
                "pred_answer":    "MISSING",
                "pred_unit":      "",
                "pred_unc":       "",
                "gt_sources":     len(gold["all_provenance"]),
                "pred_retrieved": 0,
                "note":           "not_in_output",
                **{k: "0.000" for k in list(WEIGHTS) + ["Overall"]},
                **{k: "0.000" for k in AQ_KEYS},
            })
            continue

        raw_pred, pred = entry
        sc  = compute_scores(gold, pred)
        aq  = compute_answer_quality(gold["gt_answer_label"], raw_pred)
        r1  = score_evidence_rouge1(gold, raw_pred)
        aq["Evidence ROUGE-1"] = r1

        acc = pred.get("accepted_answer", {})
        rows.append({
            "question_id":    q_id,
            "question":       gold["question"][:80],
            "gt_answer":      gold["gt_answer_label"],
            "pred_answer":    acc.get("value", ""),
            "pred_unit":      raw_pred.get("accepted_answer", {}).get("unit", ""),
            "pred_unc":       raw_pred.get("accepted_answer", {}).get("uncertainty", ""),
            "gt_sources":     len(gold["all_provenance"]),
            "pred_retrieved": len(pred.get("retrieved_documents", [])),
            "note":           "",
            **{k: f"{v:.3f}" for k, v in sc.items()},
            **{k: f"{v:.3f}" for k, v in aq.items()},
        })

    fields = ["question_id", "question", "gt_answer", "pred_answer",
              "pred_unit", "pred_unc",
              "gt_sources", "pred_retrieved", "note",
              "Document Recall", "Document Precision",
              "Page Recall", "Page Precision",
              "Evidence Exact", "Overall",
              "Value Match", "Unit Match", "Uncertainty Provided", "Evidence ROUGE-1"]

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, quoting=csv.QUOTE_ALL)
        w.writeheader()
        w.writerows(rows)

    print(f"✓ Results → {out_path}")
    _print_metrics(rows)


def _print_metrics(rows):
    dims = list(WEIGHTS.keys()) + ["Overall"]

    print()
    print("═" * 72)
    print("  ProtonQA — Provenance Evaluation")
    print("═" * 72)
    print(f"  {'Dimension':<22} {'Weight':>6}  {'Avg':>6}  Bar")
    print("─" * 72)
    for dim in dims:
        vals = [float(r[dim]) for r in rows if r.get(dim) not in ("", None)]
        avg  = sum(vals) / len(vals) if vals else 0.0
        w_s  = f"{WEIGHTS.get(dim, 0):.0%}" if dim in WEIGHTS else "  —"
        bar  = "█" * int(avg * 20) + "░" * (20 - int(avg * 20))
        sep  = "─" * 72 if dim == "Evidence Exact" else ""
        print(f"  {dim:<22} {w_s:>6}  {avg:>5.3f}  {bar}")
        if sep:
            print(sep)
    print("═" * 72)

    # Per-question table
    print()
    print(f"  {'ID':<6}  {'DocR':>5}  {'DocP':>5}  {'PgR':>5}  {'PgP':>5}  "
          f"{'Evid':>5}  {'OVR':>6}  "
          f"{'GT':>4}srcs  {'Pred':>4}ret  Note")
    print("  " + "─" * 90)
    for r in rows:
        dr = float(r["Document Recall"])
        dp = float(r["Document Precision"])
        pr = float(r["Page Recall"])
        pp = float(r["Page Precision"])
        ev = float(r["Evidence Exact"])
        ov = float(r["Overall"])
        pg_icon = "✅" if pr == 1.0 else "❌"
        ev_icon = "✅" if ev == 1.0 else "❌"
        note = r.get("note", "")
        print(f"  {r['question_id']:<6}  {dr:5.2f}  {dp:5.2f}  {pr:5.2f}  "
              f"{pp:5.2f}  {ev:5.2f}  {ov:6.3f}  "
              f"{pg_icon}{ev_icon}  "
              f"{r['gt_sources']:>4}      {r['pred_retrieved']:>4}  {note}")

    # Flag page recall failures
    failed = [r for r in rows if float(r["Page Recall"]) < 1.0]
    if failed:
        print()
        print(f"  ⚠ Page Recall < 1.0 in {len(failed)} question(s):")
        for r in failed:
            print(f"    [{r['question_id']}] "
                  f"gt_sources={r['gt_sources']}  "
                  f"pred_retrieved={r['pred_retrieved']}")

    # ── Supplementary: Answer Quality ────────────────────────────────────────
    AQ_KEYS = ["Value Match", "Unit Match", "Uncertainty Provided", "Evidence ROUGE-1"]
    if all(k in rows[0] for k in AQ_KEYS) if rows else False:
        print()
        print("═" * 72)
        print("  Supplementary — Answer Quality Metrics (not weighted into Overall)")
        print("═" * 72)
        print(f"  {'Dimension':<25}  {'Avg':>6}  Bar")
        print("─" * 72)
        for key in AQ_KEYS:
            vals = [float(r[key]) for r in rows if r.get(key) not in ("", None)]
            avg  = sum(vals) / len(vals) if vals else 0.0
            bar  = "█" * int(avg * 20) + "░" * (20 - int(avg * 20))
            # note = ("  ← proposed future metric" if key == "Evidence ROUGE-1" else "")
            print(f"  {key:<25}  {avg:>5.3f}  {bar}{note}")
        print("─" * 72)
        print()
        print(f"  {'ID':<6}  {'ValM':>5}  {'UnitM':>5}  {'UncP':>5}  "
              f"{'R1':>5}  GT answer → Predicted")
        print("  " + "─" * 72)
        for r in rows:
            vm  = float(r.get("Value Match", 0))
            um  = float(r.get("Unit Match", 0))
            up  = float(r.get("Uncertainty Provided", 0))
            r1  = float(r.get("Evidence ROUGE-1", 0))
            vm_i = "✅" if vm == 1.0 else ("🟡" if vm >= 0.5 else "❌")
            um_i = "✅" if um == 1.0 else "❌"
            up_i = "✅" if up == 1.0 else "❌"
            r1_i = "✅" if r1 >= 0.8 else ("🟡" if r1 >= 0.5 else "❌")
            pu = r.get("pred_unit","")
            pp = r.get("pred_unc","")
            pred_str = r["pred_answer"]
            if pu: pred_str += f" {pu}"
            if pp: pred_str += f" ±{pp}"
            gt_str   = r["gt_answer"][:22]
            pred_str = pred_str[:22]
            print(f"  {r['question_id']:<6}  {vm:.2f}{vm_i} {um:.2f}{um_i} "
                  f"{up:.2f}{up_i} {r1:.2f}{r1_i}  "
                  f"{gt_str:<22} → {pred_str}")
        print()
        print("  Definitions:")
        print("  ValM   Value Match           — numeric within 2% tolerance (ROUGE-1 fallback for text)")
        print("  UnitM  Unit Match            — normalised unit string comparison")
        print("  UncP   Uncertainty Provided  — 1.0 if GT requires uncertainty AND system provided it")
        print("  R1     Evidence ROUGE-1 F1   — unigram token overlap vs oa:exact quote (no dependencies)")
    print()


def cmd_metrics(results_path):
    with open(results_path, encoding="utf-8") as f:
        _print_metrics(list(csv.DictReader(f)))


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="ProtonQA Provenance Evaluator v3",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = ap.add_subparsers(dest="cmd")

    pv = sub.add_parser("validate", help="Evaluate provenance against TTL ground truth")
    pv.add_argument("--ttl",     required=True, help="questions.ttl")
    pv.add_argument("--answers", required=True, help="RAG system JSON output")
    pv.add_argument("--ids",     nargs="+",     default=None,
                    help="Question IDs to evaluate (default: all)")
    pv.add_argument("--out",     default="provenance_results.csv")

    pm = sub.add_parser("metrics", help="Re-print metrics from saved CSV")
    pm.add_argument("--results", required=True)

    args = ap.parse_args()
    if args.cmd == "validate":
        cmd_validate(args.ttl, args.answers,
                     set(args.ids) if args.ids else None, args.out)
    elif args.cmd == "metrics":
        cmd_metrics(args.results)
    else:
        ap.print_help()