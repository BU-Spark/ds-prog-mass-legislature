
import csv
import html as _html
import json
import re
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd

from crawl_related_bills import (ALL_BILLS_FILE, INPUT_FILE, bill_key, bill_url_for_reference,
                                 normalize_reference, read_jsonl, split_references)
from export_sheet_dataset import derive_stage as stage_of
from merge_match import merge_kind

BILLS_FILE = ALL_BILLS_FILE       # output/all_bills.jsonl
AGENDA_FILE = INPUT_FILE          # output/agenda_bills.jsonl 
BUDGET_FILE = Path("output/budget_scores.csv")        # written by budget_match.py
MERGE_SCORES_FILE = Path("output/merge_scores.csv")      
MERGE_SECTIONS_FILE = Path("output/merge_sections.csv")  
COMPANIONS_FILE = Path("output/companions.json")    
SESSION = 194  # the repo hardcodes 194 

esc = _html.escape



def show(bid):
    """H3591 -> H.3591 (display only). Dockets such as HD3390 are left alone."""
    return re.sub(r"^([HS])(\d+)$", r"\1.\2", bid or "")


def _date(text):
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(text or "").strip(), fmt).date()
        except ValueError:
            pass
    return None


def fmt_date(d):
    return d.strftime("%b %d, %Y") if d else "no date"


def kind_of(action):
    """How an action ties this bill to another one, using the team's merge_kind (merge_match.py).
    merge_kind now counts study orders as merges too (feature/legislative-timeline), so no special check here.
      draft     this bill was replaced by a new draft      ("Accompanied a new draft, see H5590")
      draft_of  this bill is the new draft of others       ("New draft of H78, H80")
      by        the others were merged into this bill      ("Accompanied by H3591 and H3598")
      to        this bill was merged into the lead bill    ("Accompanied H3594")
      study     this bill was merged into a study order    ("Accompanied a study order, see S2931")"""
    if re.search(r"study order", action or "", re.I):   # also right on an older merge_match.py that skips study orders
        return "study"
    return {("study order", "forward"): "study",
            ("new draft", "forward"): "draft", ("new draft", "reverse"): "draft_of",
            ("accompanied by", "reverse"): "by", ("accompanied by", "forward"): "to"}.get(merge_kind(action), "other")


# ---------- loading ----------


def load_bills(path=BILLS_FILE):
    """{bill id: bill dict} with cleaned, date-sorted actions."""
    bills = {}
    for raw in read_jsonl(Path(path)):
        bid = bill_key(raw)
        if not bid:
            continue
        acts = []
        for h in raw.get("history") or []:
            action = h.get("action") or ""
            acts.append({"date": _date(h.get("date")), "branch": h.get("branch") or "", "action": action,
                         "stage": stage_of(action), "kind": kind_of(action),
                         "refs": [r for r in split_references(h.get("related_bill")) if r != bid]})
        # actions with no date go last; sort is stable so same-day actions keep the site's order
        acts.sort(key=lambda a: (a["date"] is None, a["date"] or datetime.min.date()))
        bills[bid] = {"id": bid, "name": raw.get("title") or show(bid), "presenter": raw.get("presenter"),
                      "url": raw.get("bill_page_url") or raw.get("bill_url") or bill_url_for_reference(bid),
                      "filed": raw.get("filed_date"), "acts": acts}
    return bills


def load_agenda_ids(path=AGENDA_FILE):
    """Ids of the bills on the agenda. Empty set if the file is missing."""
    return {k for k in (bill_key(r) for r in read_jsonl(Path(path))) if k} if Path(path).exists() else set()


def load_budget(path=BUDGET_FILE):
    """{bill id: [rows]} from budget_match.py's budget_scores.csv, if it exists."""
    out = {}
    if Path(path).exists():
        with open(path, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                out.setdefault(normalize_reference(row.get("bill_number")), []).append(row)
    return out


def _title_key(name):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", "", name.lower())).strip()


def _sort_id(i):
    m = re.fullmatch(r"([HS])(\d+)", i)
    return (0 if i[0] == "H" else 1, int(m[2]) if m else 10**9, i)


def group_bills(bills):
    """Group companion bills (same title ignoring case, or listed in companions.json).
    A new draft or study order is not a companion, but it has no page of its own either: it is
    attached to the page of the bill it replaced (g["followup_ids"]) and shown there as its final status."""
    companions = []
    if COMPANIONS_FILE.exists():
        companions = [[normalize_reference(x) for x in c] for c in json.loads(COMPANIONS_FILE.read_text())]
    derived, originals = set(), {}          # originals: derived bill -> bills it replaced
    for b in bills.values():
        for a in b["acts"]:
            if a["kind"] == "draft_of":      # "New draft of H1405"
                derived.add(b["id"])
                for r in a["refs"]:
                    if r in bills:
                        originals.setdefault(b["id"], []).append(r)
            elif a["kind"] in ("draft", "study"):  # "Accompanied a new draft, see H5590" / "...a study order, see S2931"
                for r in a["refs"]:
                    if r in bills:
                        derived.add(r)
                        originals.setdefault(r, []).append(b["id"])
    by_key = {}
    for bid in sorted(bills, key=_sort_id):
        merged = next((c for c in companions if bid in c), None)
        if merged:
            key = "c:" + merged[0]
        elif bid in derived:
            key = "d:" + bid
        else:
            key = _title_key(bills[bid]["name"])
        g = by_key.setdefault(key, {"key": key, "name": bills[bid]["name"], "ids": [], "followup_ids": []})
        g["ids"].append(bid)
    all_groups = list(by_key.values())
    owner = {i: g for g in all_groups for i in g["ids"]}

    def parents(bid, seen=()):
        """Pages of the non-derived bills this one replaced (follows chains of drafts)."""
        out = []
        for o in originals.get(bid, []):
            if o in seen or o not in owner:
                continue
            if owner[o]["key"].startswith("d:"):
                out += parents(o, seen + (bid,))
            elif owner[o] not in out:
                out.append(owner[o])
        return out

    groups, hidden = [], {}
    for g in all_groups:
        ps = parents(g["ids"][0]) if g["key"].startswith("d:") else []
        if ps:
            hidden[g["ids"][0]] = ps
            for p in ps:
                p["followup_ids"].append(g["ids"][0])
        else:
            groups.append(g)
    groups.sort(key=lambda g: g["name"].lower())
    group_of = {i: g for g in groups for i in g["ids"]}
    for d, ps in hidden.items():        # searching or linking to H5590 opens the page of the bill it replaced
        group_of[d] = ps[0]
    return groups, group_of


def lanes(g, bills, cap=8):
    """Everything on one page, split by chamber: {"House": [item...], "Senate": [item...]}.
    An item is {"id", "bill" (None if not collected), "role", "member" (bool)}.
    Members come first, then what they became (new draft, study order, lead bill), then bills merged into them."""
    ids = list(g["ids"])
    items = {i: {"id": i, "bill": bills[i], "role": "Filed bill", "member": True} for i in ids}
    order = list(ids)
    queue, extra_absorbed = list(ids), 0
    while queue:                                    # follow forward links, e.g. H1405 -> H5590
        cur = queue.pop(0)
        for a in (bills[cur]["acts"] if cur in bills else []):
            if a["kind"] not in ("draft", "study", "to"):
                continue
            for n in a["refs"]:
                if n in items:
                    continue
                role = {"draft": "New draft of ", "study": "Study order merging ", "to": "Lead bill for "}[a["kind"]] + show(cur)
                items[n] = {"id": n, "bill": bills.get(n), "role": role, "member": False}
                order.append(n)
                queue.append(n)
    absorbed = []
    for i in ids:                                   # bills merged into a member: "Accompanied by H3591 and H3598"
        for a in bills[i]["acts"]:
            if a["kind"] == "by":
                absorbed += [(n, i) for n in a["refs"] if n not in items and n != i]
    for n, i in absorbed[:cap]:
        items[n] = {"id": n, "bill": bills.get(n), "role": "Merged into " + show(i), "member": False}
        order.append(n)
    extra_absorbed = max(0, len(absorbed) - cap)
    out = {"House": [], "Senate": []}
    for n in order:
        out["Senate" if n.startswith("S") else "House"].append(items[n])
    out["more"] = extra_absorbed
    return out


def chain_html(items):
    """Horizontal strip: filed bill(s) -> what they became. Plain HTML, styled by the .chain classes."""
    def node(it):
        b = it["bill"]
        label = status(b) if b else "History not collected"
        return (f'<span class="node{"" if it["member"] else " final"}"><b>{_link(it["id"])}</b>'
                f'<small>{esc(it["role"] if not it["member"] else label)}</small>'
                + (f'<small class="st">{esc(label)}</small>' if not it["member"] else "") + '</span>')
    first = [node(i) for i in items if i["member"]]
    rest = [node(i) for i in items if not i["member"]]
    parts = ['<span class="plus">+</span>'.join(first)] if first else []
    parts += [f'<span class="arr">→</span>{r}' for r in rest]
    return '<div class="chain">' + "".join(parts) + '</div>'


REL_LABEL = {"study": "Study order merging", "draft": "New draft of", "with": "Merged into",
             "into": "Carries", "draftof": "Replaced by", "rel": "Related to"}
_KIND_TO_REL = {"study": "study", "draft": "draft", "by": "with", "to": "into", "draft_of": "draftof", "other": "rel"}


def _link(n):
    url = bill_url_for_reference(n)
    return f'<a href="{url}" target="_blank" rel="noopener">{show(n)}</a>' if url else show(n)


def _and_list(items):
    return items[0] if len(items) < 2 else ", ".join(items[:-1]) + " and " + items[-1]


def _lower_first(s):
    return s[:1].lower() + s[1:]


def status(b):
    """Short plain-English status for badges and chips."""
    if not b["acts"]:
        return "No actions"
    last = b["acts"][-1]
    a = last["action"].lower()
    k = last["kind"]
    if k == "study":
        return "Merged into study order"
    if k == "draft":
        return "Replaced"
    if k == "draft_of":
        return "New draft"
    if k == "to":
        return "Merged into another bill"
    if k == "by":
        return "Absorbed other bills"
    if last["stage"] == "Accompanied":
        return "Accompanied"
    if last["stage"] == "Extension":
        return "In committee"
    if "ways and means" in a:
        return "In Ways and Means"
    if last["stage"] == "Hearing":
        return "Heard in committee"
    if last["stage"] in ("Referred", "Concurred"):
        return "In committee"
    return {"Enacted": "Enacted", "Signed into law": "Signed into law", "Reported": "Reported out of committee",
            "Second Reading": "On the floor", "Third Reading": "On the floor",
            "Orders of the Day": "On the floor"}.get(last["stage"], last["stage"])


def story(b):
    """One or two sentences for 'What happened' (HTML)."""
    acts = b["acts"]
    ev = next((a for a in reversed(acts) if a["refs"]), None)
    last_dated = next((a for a in reversed(acts) if a["date"]), None)
    if ev:
        refs = [_link(n) for n in ev["refs"]]
        on = f" on {fmt_date(ev['date'])}" if ev["date"] else ""
        k = ev["kind"]
        if k == "draft":
            s = f"A new draft, {refs[0]}, took over{on}. The language may now live there."
        elif k == "study":
            s = f"Merged into study order {refs[0]}{on}, which carries the topic forward."
        elif k == "by":
            s = f"{_and_list(refs)} {'was' if len(refs) == 1 else 'were'} merged into this bill{on}."
        elif k == "to":
            s = f"Merged into {refs[0]}{on}, which carries the topic forward."
        elif k == "draft_of":
            s = f"This is the new draft of {_and_list(refs)}{on}."
        else:
            s = f"Related to {_and_list(refs)}{on}."
        after = [a for a in acts[acts.index(ev) + 1:] if a["date"]]
        if after:
            s += f" Latest: {esc(_lower_first(after[-1]['action']))} ({fmt_date(after[-1]['date'])})."
        return s
    if last_dated:
        return f"No merger or new draft yet. Latest: {esc(_lower_first(last_dated['action']))} ({fmt_date(last_dated['date'])})."
    return ""


def related(members, group_ids):
    """Bills tied to this page's bills, outside the page's own companion bills."""
    found = {}
    for b in members:
        for a in b["acts"]:
            for n in a["refs"]:
                if n in group_ids:
                    continue
                k = _KIND_TO_REL[a["kind"]]
                item = found.setdefault((n, k), {"n": n, "k": k, "froms": []})
                if b["id"] not in item["froms"]:
                    item["froms"].append(b["id"])
    return list(found.values())


def similar_to(group, pool, cutoff=0.8, limit=2):
    """Groups in `pool` with a title very close to `group`'s. Only run for the open bill, so it stays fast."""
    scored = sorted(((SequenceMatcher(None, _title_key(group["name"]), _title_key(o["name"])).ratio(), o)
                     for o in pool if o["key"] != group["key"]), key=lambda x: -x[0])
    return [o for score, o in scored[:limit] if score >= cutoff]


def linkify(text):
    """Escape an action and turn bill numbers in it into links."""
    return re.sub(r"\b([HS])\.?\s?(\d{2,5})\b", lambda m: _link(f"{m[1].upper()}{m[2]}"), esc(text or ""))


def search(q, groups, limit=8):
    """Find bills by number or name. Returns [(score, group)], best first.
    Numbers can be typed any way: S.860, s860, S 860, or just 860."""
    t = (q or "").strip().lower()
    if not t:
        return []
    nq = re.sub(r"[^A-Z0-9]", "", q.upper())
    words = [w for w in t.split() if len(w) > 1]
    hits = []
    for g in groups:
        score = 0
        for i in g["ids"] + g.get("followup_ids", []):
            if re.fullmatch(r"[HS]D?\d+", nq):
                score = max(score, 100 if i == nq else 60 if i.startswith(nq) else 0)
            elif nq.isdigit():
                digits = re.sub(r"^[A-Z]+", "", i)
                score = max(score, 90 if digits == nq else 55 if digits.startswith(nq) else 0)
        title = g["name"].lower()
        if t in title:
            score = max(score, 80)
        elif words and all(w in title for w in words):
            score = max(score, 50)
        if score:
            hits.append((score, g))
    hits.sort(key=lambda x: (-x[0], not x[1].get("agenda", True)))
    return hits[:limit]


# ---------- text-match results (written by merge_match.py) ----------
def load_merge_scores(path=MERGE_SCORES_FILE):
    """{(original_bill, merged_into): row dict} from merge_scores.csv. Empty if the file is missing."""
    if not Path(path).exists():
        return {}
    df = pd.read_csv(path, dtype=str).fillna("")
    return {(r["original_bill"], r["merged_into"]): r for r in df.to_dict("records")}


def load_merge_sections(src, tgt, path=MERGE_SECTIONS_FILE):
    """The section-by-section rows of merge_sections.csv for one pair."""
    if not Path(path).exists():
        return pd.DataFrame()
    df = pd.read_csv(path, dtype=str).fillna("")
    df = df[(df["original_bill"] == src) & (df["merged_into"] == tgt)]
    cols = ["section", "match_type", "lexical_containment", "semantic_similarity", "best_target_section", "preview"]
    return df[[c for c in cols if c in df.columns]]


def _pct(x):
    try:
        return f"{round(float(x) * 100)}%"
    except (TypeError, ValueError):
        return None


def merge_sentence(row):
    """One plain sentence about a scored pair (HTML-safe)."""
    src, tgt = show(row["original_bill"]), show(row["merged_into"])
    if row.get("status") != "ok":
        return f"Text comparison of {src} and {tgt} isn’t available yet ({esc(row.get('status', ''))})."
    s = (f"{_pct(row.get('pct_words_incorporated')) or 'An unknown share'} of {src}’s words made it into {tgt} "
         f"({row.get('sections_incorporated')} of {row.get('sections_scored')} sections: "
         f"{row.get('verbatim')} verbatim, {row.get('reworded')} reworded).")
    partial = _pct(row.get("pct_words_partial"))
    if partial and partial != "0%":
        s += f" Another {partial} is a partial match to check by hand."
    return s


def merge_rows_for(ids, scores):
    """Scored pairs (from merge_scores.csv) where one of this page's bills is the original or the target."""
    ids = set(ids)
    return [row for (src, tgt), row in scores.items() if src in ids or tgt in ids]


def _num(row, key):
    try:
        return int(float(row.get(key, "")))
    except (TypeError, ValueError):
        return None


def score_card(row):
    """HTML for one scored pair: the numbers merge_match.py computed, as tiles."""
    src, tgt = show(row["original_bill"]), show(row["merged_into"])
    head = (f'<div class="mh">{src} → {tgt} <span class="badge">{esc(row.get("merge_type") or "merge")}</span></div>')
    if row.get("status") != "ok":
        return f'<div class="mc">{head}<p class="mt">Not scored: {esc(row.get("status") or "unknown reason")}.</p></div>'
    scored, inc = _num(row, "sections_scored"), _num(row, "sections_incorporated")
    tiles = [(_pct(row.get("pct_words_incorporated")), "of its words carried over"),
             (_pct(row.get("pct_sections_incorporated")), f"of sections ({inc} of {scored})"),
             (_pct(row.get("pct_words_partial")), "partial match, check by hand")]
    t = "".join(f'<div class="tile"><b>{v or "n/a"}</b><span>{lab}</span></div>' for v, lab in tiles)
    counts = " · ".join(f"{_num(row, k) or 0} {lab}" for k, lab in
                        (("verbatim", "verbatim"), ("reworded", "reworded"), ("concepts_only", "concepts only"),
                         ("partial", "partial"), ("not_found", "not found")))
    return f'<div class="mc">{head}<div class="tiles">{t}</div><p class="mt">{counts}</p></div>'


def budget_card(row):
    """HTML for one budget_scores.csv row: best budget section, how strong, and why (HTML-safe)."""
    num = normalize_reference(row.get("bill_number"))
    bid = (f'{"Senate" if num.startswith("S") else "House"} · {show(num)} vs budget '
       f'{show(esc(row.get("budget_id") or "budget"))}')
    src = row.get("budget_source") or ""
    link = f' <a href="{esc(src)}" target="_blank" rel="noopener">Source</a>' if src.startswith("http") else ""
    if row.get("status") != "ok":
        return f'<div class="wh"><div class="k">{bid}</div><p class="muted">Not checked: {esc(row.get("status") or "unknown")}.</p></div>'
    strong = str(row.get("policy_evidence_pass")).lower() == "true"
    badge = "Likely in the budget" if strong else "No clear match"
    sim = row.get("similarity") or ""
    sec = esc(row.get("best_target_section") or "")
    text = (row.get("target_text") or "").strip()
    text = esc(text[:320] + ("…" if len(text) > 320 else ""))
    terms = [t.strip() for t in str(row.get("policy_shared_terms") or "").split(";") if t.strip()][:10]
    phrases = [t.strip() for t in str(row.get("policy_shared_phrases") or "").split(";") if t.strip()][:5]
    why = ""
    if terms:
        why += f'<p class="muted">Shared policy words: {esc(", ".join(terms))}.</p>'
    if phrases:
        why += f'<p class="muted">Shared phrases: {esc(", ".join(phrases))}.</p>'
    note = ("" if strong else '<p class="muted">The closest budget section is shown for reference only. '
            'It does not share enough policy-specific wording to count as a match.</p>')
    return (f'<div class="wh"><div class="k">{bid}</div><div class="k">{badge} <span class="badge">similarity {esc(sim)}</span></div>'
            f'<p><b>{sec}</b>{link}</p><p>{text}</p>{why}{note}</div>')
