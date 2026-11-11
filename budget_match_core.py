"""Budget-specific matching logic, separate from the original merge_match.py.

Reuse its tokenization, section splitter, concept extraction, and embedding
interface without changing the bill-to-bill matcher or its behavior.

Unlike merge_match.match_pair(), matching against a very long budget uses
LOCAL lexical and concept overlap: evidence must occur in one budget passage
(or two adjacent passages), not scattered throughout the entire budget.
"""

from merge_match import (
    MIN_SECTION_WORDS,
    clean,
    concepts,
    containment,
    shingles,
    split_sections,
)


def prepare_budget_target(budget_text, budget_sections, embedder=None):
    """Build a reusable index once for the chosen budget version.

    ``budget_sections`` is a list of (section/line-item label, raw text).
    Include adjacent two-passage windows to catch matches split by chunking.
    """
    passages = list(budget_sections)
    passages += [
        (f"{passages[k][0]} + {passages[k + 1][0]}",
         passages[k][1] + " " + passages[k + 1][1])
        for k in range(len(passages) - 1)
    ]
    return {
        "passages": passages,
        "passage_shingles": [shingles(text) for _, text in passages],
        "passage_concepts": [concepts(text) for _, text in passages],
        "budget_shingles": shingles(budget_text),
        "embeddings": embedder.embed([text for _, text in passages])
        if embedder is not None and passages else None,
    }


def match_budget_pair(bill_text, budget_index, embedder, args):
    """Score sections of one bill against the indexed budget passages.

    Match labels/thresholds match merge_match.py, but every strong match must
    have its supporting wording in a single candidate budget passage.
    Report whole-budget wording overlap separately for comparison only.
    """
    source_sections = split_sections(bill_text)
    passages = budget_index["passages"]
    passage_shingles = budget_index["passage_shingles"]
    passage_concepts = budget_index["passage_concepts"]

    similarities = None
    if embedder is not None and source_sections and budget_index["embeddings"] is not None:
        source_embeddings = embedder.embed([text for _, text in source_sections])
        similarities = source_embeddings @ budget_index["embeddings"].T

    rows = []
    for i, (label, text) in enumerate(source_sections):
        n_words = len(clean(text).split())
        source_shingles = shingles(text)
        per_passage_word_overlap = [
            containment(source_shingles, candidate) for candidate in passage_shingles
        ]
        best_word_index = (max(range(len(per_passage_word_overlap)),
                               key=per_passage_word_overlap.__getitem__)
                           if per_passage_word_overlap else None)
        word_overlap = (per_passage_word_overlap[best_word_index]
                        if best_word_index is not None else 0.0)
        global_word_overlap = containment(source_shingles, budget_index["budget_shingles"])

        semantic_similarity = None
        if similarities is not None:
            semantic_similarity = float(similarities[i].max())
            best_index = int(similarities[i].argmax())
        else:
            best_index = best_word_index
        if word_overlap >= args.lex_threshold and best_word_index is not None:
            best_index = best_word_index

        source_concepts = concepts(text)
        best_concept_index = None
        closest_concepts = set()
        if source_concepts and passage_concepts:
            concept_overlaps = [
                len(source_concepts & candidate) / len(source_concepts)
                for candidate in passage_concepts
            ]
            best_concept_index = max(range(len(concept_overlaps)),
                                     key=concept_overlaps.__getitem__)
            closest_concepts = passage_concepts[best_concept_index]
        concept_overlap = (len(source_concepts & closest_concepts) / len(source_concepts)
                           if source_concepts else None)

        # A semantic match is only "reworded" if that same passage also shares words.
        semantic_passage_word_overlap = (per_passage_word_overlap[best_index]
                                         if best_index is not None else 0.0)
        boilerplate = n_words < MIN_SECTION_WORDS
        if boilerplate:
            match_type = "boilerplate (not scored)"
        elif word_overlap >= args.lex_threshold:
            match_type = "verbatim"
        elif (semantic_similarity is not None
              and semantic_similarity >= args.sem_threshold
              and semantic_passage_word_overlap >= args.reworded_min_words):
            match_type = "reworded"
        elif (concept_overlap is not None and concept_overlap >= args.concept_threshold
              and len(source_concepts) >= 2):
            match_type = "concepts only"
            best_index = best_concept_index
        elif semantic_similarity is not None and semantic_similarity >= args.partial_threshold:
            match_type = "partial"
        else:
            match_type = "not found"

        rows.append({
            "section": label,
            "words": n_words,
            "lexical_containment": round(word_overlap, 3),
            "lexical_containment_global": round(global_word_overlap, 3),
            "semantic_similarity": (None if semantic_similarity is None
                                    else round(semantic_similarity, 3)),
            "concept_overlap": None if concept_overlap is None else round(concept_overlap, 3),
            "concepts": "; ".join(sorted(source_concepts)),
            "concepts_missing": "; ".join(sorted(source_concepts - closest_concepts)),
            "best_target_section": passages[best_index][0] if best_index is not None else None,
            "source_text": text,
            "target_text": passages[best_index][1] if best_index is not None else None,
            "match_type": match_type,
            "incorporated": match_type in ("verbatim", "reworded"),
            "scored": not boilerplate,
            "preview": text[:160].replace("\n", " "),
        })
    return rows
