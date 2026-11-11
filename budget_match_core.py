"""Budget-only matching rules; never modifies the bill-to-bill matcher.

A high five-word overlap or embedding score is insufficient on its own: generic
Massachusetts bill-drafting language can look almost identical across unrelated
policies. A STRONG budget candidate must also share policy-specific words in
one concrete budget passage (or a window of two adjacent passages).
"""

import re

from merge_match import (
    MIN_SECTION_WORDS,
    clean,
    concepts,
    containment,
    shingles,
    split_sections,
)

# Intentionally transparent and conservative. These terms describe legislative
# drafting or general English grammar, not the underlying policy being changed.
# Do not exclude policy areas (e.g., housing, tuition, voting, climate, tax).
_ENGLISH_STOPWORDS = set("""
    a about above across after again against all almost also although always an
    and another any are as at be because been before being below between both
    but by can cannot could did do does doing down during each either else even
    ever every few for from further had has have having he her here hers herself
    him himself his how however i if in into is it its itself just less many may
    me might more most much must my myself neither no nor not of off on once
    one only or other our ours ourselves out over own per perhaps rather same
    she should since so some such than that the their theirs them themselves
    then there these they this those though through throughout thus to too
    toward towards under unless until up upon us very via was we were what
    whatever when where whereas whether which while who whom whose why will
    with within without would yet you your yours yourself yourselves
""".split())

_LEGISLATIVE_STOPWORDS = set("""
    act acts add adding addition additional amend amended amending amendment
    amendments appearing article articles bill bills chapter chapters clause
    clauses code commonwealth commissioner commission committee department
    edition effective existing executive following fiscal fund funds general
    hereby herein hereinafter hereof hereinbefore hereto hereunder thereof
    therein thereto thereunder notwithstanding inserted inserting insertion
    insert law laws legislative legislature line lines massachusetts member
    members new office official paragraph paragraphs place provided provision
    provisions pursuant said section sections sentence sentences shall state
    states statute statutes strike strikes striking struck subsection
    subsections substitute substituted substituting substitution subclause
    subclauses thereof year years
""".split())

_POLICY_STOPWORDS = _ENGLISH_STOPWORDS | _LEGISLATIVE_STOPWORDS
MIN_SHARED_POLICY_TERMS = 3
MIN_SOURCE_POLICY_COVERAGE = 0.35
MIN_REORDERED_SHARED_TERMS = 5


def _policy_words(text):
    """Keep substantive alphabetic words, excluding drafting templates.

    Numbers and legal citations are not sufficient evidence of a shared policy.
    A light exact-word approach is intentional: it errs on the side of manual
    review rather than claiming a reform was included in a budget.
    """
    return [word for word in re.findall(r"[a-z]{3,}", clean(text))
            if word not in _POLICY_STOPWORDS]


def _policy_signals(text):
    words = _policy_words(text)
    return frozenset(words), frozenset(zip(words, words[1:]))


def _policy_evidence(source_terms, source_pairs, target_terms, target_pairs,
                     min_terms=MIN_SHARED_POLICY_TERMS,
                     min_coverage=MIN_SOURCE_POLICY_COVERAGE):
    shared = source_terms & target_terms
    coverage = len(shared) / len(source_terms) if source_terms else 0.0
    shared_pairs = source_pairs & target_pairs
    # Require a pair of substantive words in the same order, OR at least five
    # distinctive shared terms to allow genuinely reworded/reordered provisions.
    passed = (len(shared) >= min_terms and coverage >= min_coverage
              and (bool(shared_pairs) or len(shared) >= MIN_REORDERED_SHARED_TERMS))
    return passed, shared, coverage, shared_pairs


def prepare_budget_target(budget_text, budget_sections, embedder=None):
    """Index the budget once for every agenda bill; preserve local passages."""
    passages = list(budget_sections)
    passages += [
        (f"{passages[k][0]} + {passages[k + 1][0]}",
         passages[k][1] + " " + passages[k + 1][1])
        for k in range(len(passages) - 1)
    ]
    policy_signals = [_policy_signals(text) for _, text in passages]
    return {
        "passages": passages,
        "passage_shingles": [shingles(text) for _, text in passages],
        "passage_concepts": [concepts(text) for _, text in passages],
        "passage_policy_signals": policy_signals,
        "budget_shingles": shingles(budget_text),
        "embeddings": embedder.embed([text for _, text in passages])
        if embedder is not None and passages else None,
    }


def match_budget_pair(bill_text, budget_index, embedder, args):
    """Match bill sections; strong labels need local *substantive* wording."""
    source_sections = split_sections(bill_text)
    passages = budget_index["passages"]
    passage_shingles = budget_index["passage_shingles"]
    passage_concepts = budget_index["passage_concepts"]
    passage_policy = budget_index["passage_policy_signals"]

    similarities = None
    if embedder is not None and source_sections and budget_index["embeddings"] is not None:
        source_embeddings = embedder.embed([text for _, text in source_sections])
        similarities = source_embeddings @ budget_index["embeddings"].T

    min_terms = getattr(args, "policy_min_terms", MIN_SHARED_POLICY_TERMS)
    min_coverage = getattr(args, "policy_min_coverage", MIN_SOURCE_POLICY_COVERAGE)
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
        max_word_overlap = (per_passage_word_overlap[best_word_index]
                            if best_word_index is not None else 0.0)
        global_word_overlap = containment(source_shingles, budget_index["budget_shingles"])

        sims_row = similarities[i] if similarities is not None else None
        best_semantic_index = int(sims_row.argmax()) if sims_row is not None else None
        max_semantic_similarity = (float(sims_row[best_semantic_index])
                                   if best_semantic_index is not None else None)

        source_terms, source_pairs = _policy_signals(text)
        # Compute the substantive filter *for the same passage* that would be
        # credited as the match. Don't aggregate scattered policy words across
        # the whole budget, and don't use a high semantic score as a substitute.
        qualifying = []
        for j, (target_terms, target_pairs) in enumerate(passage_policy):
            passed, _, _, _ = _policy_evidence(
                source_terms, source_pairs, target_terms, target_pairs,
                min_terms, min_coverage)
            if passed:
                qualifying.append(j)

        boilerplate = n_words < MIN_SECTION_WORDS
        best_index = best_semantic_index if best_semantic_index is not None else best_word_index
        match_type = "not found"
        if boilerplate:
            match_type = "boilerplate (not scored)"
        else:
            # A strong label is assigned only when one *eligible* passage also
            # passes the original lexical/semantic threshold.
            good_lex = [j for j in qualifying
                        if per_passage_word_overlap[j] >= args.lex_threshold]
            good_sem = [j for j in qualifying
                        if sims_row is not None
                        and float(sims_row[j]) >= args.sem_threshold
                        and per_passage_word_overlap[j] >= args.reworded_min_words]
            if good_lex:
                best_index = max(good_lex, key=lambda j: per_passage_word_overlap[j])
                match_type = "verbatim"
            elif good_sem:
                best_index = max(good_sem, key=lambda j: float(sims_row[j]))
                match_type = "reworded"

        source_concepts = concepts(text)
        best_concept_index = None
        closest_concepts = set()
        if source_concepts and passage_concepts:
            concept_overlaps = [len(source_concepts & candidate) / len(source_concepts)
                                for candidate in passage_concepts]
            best_concept_index = max(range(len(concept_overlaps)),
                                     key=concept_overlaps.__getitem__)
            closest_concepts = passage_concepts[best_concept_index]
        concept_overlap = (len(source_concepts & closest_concepts) / len(source_concepts)
                           if source_concepts else None)

        if not boilerplate and match_type == "not found":
            if (concept_overlap is not None and concept_overlap >= args.concept_threshold
                    and len(source_concepts) >= 2):
                match_type = "concepts only"
                best_index = best_concept_index
            elif max_semantic_similarity is not None and max_semantic_similarity >= args.partial_threshold:
                match_type = "partial"

        # A diagnostic flag explains cases that the original lexical / semantic
        # rule would have called strong despite lacking policy-specific evidence.
        drafting_only_overlap = (not boilerplate
                                 and match_type not in ("verbatim", "reworded")
                                 and (max_word_overlap >= args.lex_threshold
                                      or (best_semantic_index is not None
                                          and max_semantic_similarity >= args.sem_threshold
                                          and per_passage_word_overlap[best_semantic_index]
                                          >= args.reworded_min_words)))

        selected_lex = (per_passage_word_overlap[best_index]
                        if best_index is not None else 0.0)
        selected_sem = (float(sims_row[best_index])
                        if sims_row is not None and best_index is not None else None)
        if best_index is not None:
            policy_pass, shared_terms, policy_coverage, shared_pairs = _policy_evidence(
                source_terms, source_pairs, *passage_policy[best_index],
                min_terms, min_coverage)
        else:
            policy_pass, shared_terms, policy_coverage, shared_pairs = False, set(), 0.0, set()

        rows.append({
            "section": label,
            "words": n_words,
            "lexical_containment": round(selected_lex, 3),
            "lexical_containment_global": round(global_word_overlap, 3),
            "semantic_similarity": None if selected_sem is None else round(selected_sem, 3),
            "concept_overlap": None if concept_overlap is None else round(concept_overlap, 3),
            "concepts": "; ".join(sorted(source_concepts)),
            "concepts_missing": "; ".join(sorted(source_concepts - closest_concepts)),
            "policy_shared_terms": "; ".join(sorted(shared_terms)),
            "policy_shared_term_count": len(shared_terms),
            "policy_source_coverage": round(policy_coverage, 3),
            "policy_shared_phrases": "; ".join(" ".join(pair) for pair in sorted(shared_pairs)),
            "policy_evidence_pass": policy_pass,
            "drafting_only_overlap": drafting_only_overlap,
            "best_target_section": passages[best_index][0] if best_index is not None else None,
            "source_text": text,
            "target_text": passages[best_index][1] if best_index is not None else None,
            "match_type": match_type,
            # Kept for CSV compatibility: this is a text-match *candidate*,
            # NOT proof of legislative incorporation.
            "incorporated": match_type in ("verbatim", "reworded"),
            "scored": not boilerplate,
            "preview": text[:160].replace("\n", " "),
        })
    return rows
