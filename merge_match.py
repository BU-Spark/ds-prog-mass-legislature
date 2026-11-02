"""
merge_match.py - How much of a merged bill made it into the bill it was merged into.

For every (original bill -> new bill) pair, this script:
  1. splits both bill texts into SECTIONs,
  2. checks each original section against the new bill three ways:
       - wording:  share of the section's 5-word chunks found in the new bill (containment)
       - meaning:  cosine similarity to the closest new-bill section (sentence embeddings)
       - concepts: share of the section's statute citations, dollar amounts,
                   budget line items and defined terms found in the new bill
  3. marks a section as incorporated if it is verbatim (50%+ shared wording) or reworded
     (meaning 0.80+ with 15%+ shared wording). "Partial" (meaning 0.70+, or shared
     citations/amounts/terms only) is reported separately: same topic, check by hand,
  4. scores the bill as the share of its sections (and of its words) that were incorporated.

Inputs (from the dataset-transform pipeline):
  output/all_bills.jsonl          one bill per line: bill_number ("H.3422"), bill_text, ...
  output/bill_relationships.csv   source_bill, related_bill, action, ...

Which relationships count as merges (read from the `action` text):
  "Accompanied a new draft, see H5590" on H1405  -> H1405 merged into H5590
  "Accompanied by H3591 and H3598"     on H3594  -> H3591 and H3598 merged into H3594
  "Accompanied a study order, see ..."           -> skipped (sent to study, not merged)
  anything else                                  -> skipped, counted in the summary

Outputs:
  output/merge_scores.csv    one row per pair
  output/merge_sections.csv  one row per original-bill section, with its best match

Run from the repo root:
  pip install pandas sentence-transformers
  python merge_match.py --limit 5        # try 5 pairs first
  python merge_match.py                  # all pairs
  python merge_match.py --no-embed       # wording + concepts only, no model download

The thresholds are first guesses. Tune them against ~20 hand-labeled pairs before
reporting numbers to Progressive Mass.
"""

import argparse
import re
from pathlib import Path

import pandas as pd

SHINGLE_SIZE = 5
MIN_SECTION_WORDS = 12  # shorter sections ("This act shall take effect upon passage.") are boilerplate

# ---------------------------------------------------------------- text helpers

def norm_bill_id(x):
    """'H.4405', 'h 4405' -> 'H4405'."""
    return re.sub(r"[^A-Z0-9]", "", str(x).upper())


def clean(text):
    """Lowercase, drop punctuation, collapse whitespace."""
    text = str(text or "").replace("\r", " ").replace("\t", " ")
    text = re.sub(r"[^a-z0-9$ ]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


# "SECTION 1." / "SECTION 12A." in capitals marks a bill section. Lowercase "section 5"
# inside the text is a statute citation, so the match is case-sensitive on purpose.
SECTION_RE = re.compile(r"\bSECTION\s+(\d+[A-Z]?)\.")


# "Section 3." with a capital S and a period starts a section of a chapter the bill
# inserts. Lowercase "section 3 of chapter 111" is a citation and is not matched.
SUBSECTION_RE = re.compile(r"\bSection\s+(\d+[A-Z]*)\.")


def _split_on(pattern, text, prefix):
    marks = list(pattern.finditer(text))
    if not marks:
        return [(prefix, text)]
    out = []
    if text[:marks[0].start()].strip():
        out.append((f"{prefix} intro".strip(), text[:marks[0].start()].strip()))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        out.append((f"{prefix} {m.group(0).rstrip('.')}".strip(), text[m.end():end].strip()))
    return out


def _chunk(label, text, chunk_words):
    words = text.split()
    if len(words) <= chunk_words * 1.5:
        return [(label, text)]
    return [(f"{label} part {i // chunk_words + 1}", " ".join(words[i:i + chunk_words]))
            for i in range(0, len(words), chunk_words)]


def split_sections(text, max_words=300, chunk_words=200):
    """Return a list of (label, raw_text) units of a manageable size:
    1. split at bill sections ("SECTION 1."),
    2. split long ones at inserted-chapter sections ("Section 1."),
    3. break anything still long into ~200-word parts."""
    text = str(text or "")
    units = []
    for label, body in _split_on(SECTION_RE, text, ""):
        pieces = _split_on(SUBSECTION_RE, body, label) if len(body.split()) > max_words else [(label, body)]
        for sub_label, sub_body in pieces:
            units.extend(_chunk(sub_label or "text", sub_body, chunk_words))
    return [(l, t) for l, t in units if t.strip()]


def shingles(text, n=SHINGLE_SIZE):
    w = clean(text).split()
    return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}


def containment(a, b):
    """Share of a that appears in b. Not Jaccard: the new bill is often much bigger."""
    return len(a & b) / len(a) if a else 0.0


# ---------------------------------------------------------------- concepts

CITE_A = re.compile(r"section\s+(\d+[a-z]*)\s+of\s+chapter\s+(\d+[a-z]?)", re.I)
CITE_B = re.compile(r"chapter\s+(\d+[a-z]?)(?:\s+of\s+the\s+general\s+laws)?,?\s+(?:is\s+hereby\s+amended\s+by\s+\w+\s+)?(?:in\s+)?section\s+(\d+[a-z]*)", re.I)
CHAPTER = re.compile(r"chapter\s+(\d+[a-z]?)\s+of\s+the\s+general\s+laws", re.I)
DOLLARS = re.compile(r"\$\s?([\d,]+(?:\.\d+)?)")
LINE_ITEM = re.compile(r"\b(\d{4}-\d{4})\b")
DEFINED = re.compile(r"[\"“]([A-Za-z][^\"”]{1,60})[\"”],?\s+(?:shall\s+mean|means)", re.I)


def concepts(text):
    text = str(text or "")
    found = set()
    for sec, ch in CITE_A.findall(text):
        found.add(f"mgl c{ch.lower()} s{sec.lower()}")
    for ch, sec in CITE_B.findall(text):
        found.add(f"mgl c{ch.lower()} s{sec.lower()}")
    for ch in CHAPTER.findall(text):
        found.add(f"mgl c{ch.lower()}")
    for amt in DOLLARS.findall(text):
        found.add(f"${float(amt.replace(',', '')):.2f}")  # "$5,000,000" and "$5,000,000.00" -> "$5000000.00"
    for item in LINE_ITEM.findall(text):
        found.add(f"line item {item}")
    for term in DEFINED.findall(text):
        found.add(f"term: {term.strip().lower()}")
    return found


# ---------------------------------------------------------------- embeddings

class Embedder:
    """Mean of ~200-word window embeddings, so long sections aren't truncated."""

    def __init__(self, model_name):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(model_name)
        self.cache = {}

    def embed(self, texts, window=200):
        import numpy as np
        out = []
        for t in texts:
            if t in self.cache:
                out.append(self.cache[t])
                continue
            words = t.split()
            chunks = [" ".join(words[i:i + window]) for i in range(0, max(len(words), 1), window)]
            vecs = self.model.encode(chunks, normalize_embeddings=True)
            v = vecs.mean(axis=0)
            v = v / (np.linalg.norm(v) or 1.0)
            self.cache[t] = v
            out.append(v)
        return np.vstack(out)


# ---------------------------------------------------------------- matching

def match_pair(src_text, tgt_text, embedder, args):
    src_secs = split_sections(src_text)
    tgt_secs = split_sections(tgt_text)
    # Also compare against each pair of neighboring target units joined together, so a
    # passage that straddles a chunk boundary in the new bill can still be matched.
    tgt_secs = tgt_secs + [
        (f"{tgt_secs[k][0]} + {tgt_secs[k + 1][0]}", tgt_secs[k][1] + " " + tgt_secs[k + 1][1])
        for k in range(len(tgt_secs) - 1)
    ]

    tgt_all_shingles = shingles(tgt_text)
    tgt_sec_shingles = [shingles(t) for _, t in tgt_secs]
    tgt_concepts = concepts(tgt_text)

    sims = None
    if embedder is not None and src_secs and tgt_secs:
        S = embedder.embed([t for _, t in src_secs])
        T = embedder.embed([t for _, t in tgt_secs])
        sims = S @ T.T

    rows = []
    for i, (label, text) in enumerate(src_secs):
        n_words = len(clean(text).split())
        sh = shingles(text)
        lex = containment(sh, tgt_all_shingles)
        lex_by_sec = [containment(sh, t) for t in tgt_sec_shingles]

        sem = None
        best_lex_j = max(range(len(lex_by_sec)), key=lex_by_sec.__getitem__) if lex_by_sec else None
        if sims is not None:
            sem = float(sims[i].max())
            best_j = int(sims[i].argmax())
        else:
            best_j = best_lex_j
        if lex >= args.lex_threshold and best_lex_j is not None:
            best_j = best_lex_j  # copied text: show where the words actually are

        c = concepts(text)
        con = len(c & tgt_concepts) / len(c) if c else None

        boilerplate = n_words < MIN_SECTION_WORDS
        if boilerplate:
            match_type = "boilerplate (not scored)"
        elif lex >= args.lex_threshold:
            match_type = "verbatim"
        elif sem is not None and sem >= args.sem_threshold and lex >= args.reworded_min_words:
            # Needs some shared phrasing too: a high meaning score with almost no shared
            # words is usually boilerplate (e.g. every commission's member list).
            match_type = "reworded"
        elif con is not None and con >= args.concept_threshold and len(c) >= 2:
            match_type = "concepts only"
        elif sem is not None and sem >= args.partial_threshold:
            # Same topic in different terms. Real carryovers and look-alikes both land here,
            # so it is reported separately and not counted as incorporated. Check by hand.
            match_type = "partial"
        else:
            match_type = "not found"

        rows.append({
            "section": label,
            "words": n_words,
            "lexical_containment": round(lex, 3),
            "semantic_similarity": None if sem is None else round(sem, 3),
            "concept_overlap": None if con is None else round(con, 3),
            "concepts": "; ".join(sorted(c)),
            "concepts_missing": "; ".join(sorted(c - tgt_concepts)),
            "best_target_section": tgt_secs[best_j][0] if best_j is not None else None,
            "match_type": match_type,
            # "concepts only" (shared citations/amounts/terms, little shared text) is a flag, not
            # evidence: two bills amending the same section of law share its citation.
            "incorporated": match_type in ("verbatim", "reworded"),
            "scored": not boilerplate,
            "preview": text[:160].replace("\n", " "),
        })
    return rows


def merge_kind(action):
    """Classify a history action. Returns (kind, direction) or (None, None) if it isn't a merge.
    direction 'forward': source_bill was merged into related_bill.
    direction 'reverse': related_bill was merged into source_bill."""
    a = str(action or "").lower()
    if "study order" in a:
        return None, None
    # On the original bill: "Accompanied a new draft, see H5590" / "New draft substituted, see H5305" /
    # "...ought to pass with an amendment, substituting a new draft, see S2696"
    if any(k in a for k in ("accompanied a new draft", "new draft substituted", "substituting a new draft")):
        return "new draft", "forward"
    # On the new draft itself: "New draft of H78, H80 ..." / "Pending new draft of H5293" /
    # "Recommended new draft for S2328" / "Also based on S1059, S1122 ..." / "Substituted, as amended, for S2328"
    if any(k in a for k in ("new draft of", "new draft for", "also based on")) or re.search(r"substituted,?( as amended,?)? for", a):
        return "new draft", "reverse"
    # "Accompanied by H3591" on H3594 and "Accompanied H3594" on H3591 both mean H3591 -> H3594.
    if "accompanied by" in a:
        return "accompanied by", "reverse"
    if re.match(r"accompanied\s+[hs]\d", a):
        return "accompanied by", "forward"
    # Not counted: "Reprinted, as amended" (a new version of the same bill) and
    # "inserting in place thereof the text of S3072" (direction unclear).
    return None, None


def load_pairs(related):
    """Returns (merge pairs, skipped counts, study orders).
    A study order's own history lists the bills it covers as "Accompanied by ...",
    so any pair that also appears as "Accompanied a study order, see X" is a study
    order, not a merge, and is left out of the merge pairs."""
    study = {}
    for _, r in related.iterrows():
        if "study order" in str(r.get("action", "")).lower():
            study[(norm_bill_id(r["source_bill"]), norm_bill_id(r["related_bill"]))] = r.get("action")

    rows, skipped = [], {}
    for _, r in related.iterrows():
        kind, direction = merge_kind(r.get("action"))
        if kind is None:
            label = "study order" if "study order" in str(r.get("action", "")).lower() else "other"
            skipped[label] = skipped.get(label, 0) + 1
            continue
        a, b = norm_bill_id(r["source_bill"]), norm_bill_id(r["related_bill"])
        src, tgt = (a, b) if direction == "forward" else (b, a)
        if (src, tgt) in study:
            skipped["study order (seen from the study order's side)"] = skipped.get("study order (seen from the study order's side)", 0) + 1
            continue
        if src != tgt:
            rows.append({"src": src, "tgt": tgt, "merge_type": kind, "action": r.get("action")})
    pairs = pd.DataFrame(rows, columns=["src", "tgt", "merge_type", "action"])
    study_df = pd.DataFrame([{"original_bill": s, "study_order": t, "action": a} for (s, t), a in study.items()])
    return pairs.drop_duplicates(["src", "tgt"]), skipped, study_df


def load_bills(path):
    """all_bills.jsonl -> {'H3422': bill_text}."""
    bills = pd.read_json(path, lines=True, dtype={"bill_number": str})
    return {norm_bill_id(n): (t or "") for n, t in zip(bills["bill_number"], bills["bill_text"])}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--bills", default="output/all_bills.jsonl")
    p.add_argument("--related", default="output/bill_relationships.csv")
    p.add_argument("--out", default="output")
    p.add_argument("--lex-threshold", type=float, default=0.50)
    p.add_argument("--sem-threshold", type=float, default=0.80)
    p.add_argument("--concept-threshold", type=float, default=0.80)
    p.add_argument("--reworded-min-words", type=float, default=0.15,
                   help="minimum word overlap for 'reworded'; below it a high meaning score counts as 'partial'")
    p.add_argument("--partial-threshold", type=float, default=0.70,
                   help="meaning score for 'partial' (same topic, different terms); not counted as incorporated")
    p.add_argument("--model", default="sentence-transformers/all-MiniLM-L6-v2")
    p.add_argument("--no-embed", action="store_true", help="skip the meaning check")
    p.add_argument("--limit", type=int, help="only score the first N pairs (for testing)")
    args = p.parse_args()

    text_of = load_bills(args.bills)
    pairs, skipped, study_df = load_pairs(pd.read_csv(args.related, dtype=str))
    print(f"{len(text_of)} bills loaded; {len(pairs)} merge pairs found; skipped: {skipped}")
    Path(args.out).mkdir(parents=True, exist_ok=True)
    study_df.to_csv(Path(args.out) / "study_orders.csv", index=False)
    print(f"{len(study_df)} bills sent to a study order -> {args.out}/study_orders.csv")
    if args.limit:
        pairs = pairs.head(args.limit)

    embedder = None if args.no_embed else Embedder(args.model)

    pair_rows, section_rows = [], []
    for _, pr in pairs.iterrows():
        src_text = text_of.get(pr.src, "")
        tgt_text = text_of.get(pr.tgt, "")
        base = {"original_bill": pr.src, "merged_into": pr.tgt, "merge_type": pr.merge_type, "action": pr.action}

        missing = [b for b, t in ((pr.src, src_text), (pr.tgt, tgt_text)) if not str(t).strip()]
        if missing:
            pair_rows.append({**base, "status": "missing text: " + ", ".join(missing)})
            continue

        secs = match_pair(src_text, tgt_text, embedder, args)
        for s in secs:
            section_rows.append({**base, **s})

        scored = [s for s in secs if s["scored"]]
        words = sum(s["words"] for s in scored)
        pair_rows.append({
            **base,
            "status": "ok",
            "sections_scored": len(scored),
            "sections_incorporated": sum(s["incorporated"] for s in scored),
            "pct_sections_incorporated": round(sum(s["incorporated"] for s in scored) / len(scored), 3) if scored else None,
            "pct_words_incorporated": round(sum(s["words"] for s in scored if s["incorporated"]) / words, 3) if words else None,
            "pct_words_partial": round(sum(s["words"] for s in scored if s["match_type"] in ("partial", "concepts only")) / words, 3) if words else None,
            "verbatim": sum(s["match_type"] == "verbatim" for s in scored),
            "reworded": sum(s["match_type"] == "reworded" for s in scored),
            "concepts_only": sum(s["match_type"] == "concepts only" for s in scored),
            "partial": sum(s["match_type"] == "partial" for s in scored),
            "not_found": sum(s["match_type"] == "not found" for s in scored),
        })

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(pair_rows).to_csv(out / "merge_scores.csv", index=False)
    pd.DataFrame(section_rows).to_csv(out / "merge_sections.csv", index=False)
    print(f"Scored {sum(r.get('status') == 'ok' for r in pair_rows)} of {len(pair_rows)} pairs -> {out}/merge_scores.csv, merge_sections.csv")


if __name__ == "__main__":
    main()
