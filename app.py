"""MA Bill Tracker"""
from datetime import datetime

import streamlit as st

import bill_data as bd

st.set_page_config(page_title="MA Bill Tracker", page_icon="🏛️", layout="wide", initial_sidebar_state="collapsed")

CSS = """<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+SC:wght@600&family=Lora:ital,wght@1,500;1,600&family=Poppins:wght@400;500;600&display=swap');
:root{--ink:#1E2433;--muted:#6B7280;--line:#E3E7EE;--cardhead:#F6F8FB;--navy:#24407A;--deep:#1E2F55;--hero:#3D4454;
--c1:#E3C2E8;--c2:#DCC69A;--c3:#AED2EA;--c4:#DDE2A2;--shadow:0 1px 2px rgba(30,47,85,.06),0 4px 14px rgba(30,47,85,.06);
--sans:"Poppins",system-ui,sans-serif;--ital:"Lora",Georgia,serif;--display:"Cormorant SC",Georgia,serif}
header[data-testid="stHeader"],[data-testid="stToolbar"],[data-testid="stDecoration"],footer,#MainMenu{display:none!important}
.stApp,[data-testid="stMarkdownContainer"]{font-family:var(--sans);color:var(--ink)}
[data-testid="stMarkdownContainer"]{font-size:14.5px;line-height:1.55}
[data-testid="stMainBlockContainer"],.block-container{padding:0!important;max-width:100%!important}
[data-testid="stVerticalBlock"]{gap:0}
a{color:var(--navy)}
.wrap{max-width:1180px;margin:0 auto;padding:0 24px}
.util{background:var(--deep);color:#DCE3F1}
.util .wrap{display:flex;justify-content:space-between;gap:12px;min-height:30px;align-items:center;flex-wrap:wrap}
.util span{text-transform:uppercase;letter-spacing:.08em;font-size:10.5px}
.nav{background:#fff;border-bottom:1px solid var(--line)}
.nav .wrap{display:flex;justify-content:space-between;align-items:center;min-height:58px;gap:16px}
.logo{color:var(--navy);font-weight:600;letter-spacing:.1em;text-transform:uppercase;font-size:14px}
.links{display:flex;gap:26px}
.links a{color:var(--ink);text-decoration:none;text-transform:uppercase;letter-spacing:.08em;font-size:11.5px;font-weight:500}
.st-key-hero{background:var(--hero);color:#fff;position:relative;overflow:hidden;padding:64px 24px;text-align:center}
.st-key-hero [data-testid="stElementContainer"],.st-key-hero [data-testid="stMarkdown"],.st-key-hero [data-testid="stMarkdownContainer"]{width:100%;max-width:100%;text-align:center}
.st-key-hero [data-testid="stMarkdownContainer"] p,.st-key-hero [data-testid="stMarkdownContainer"] div{color:#fff}
.st-key-hero [data-testid="stVerticalBlock"]{align-items:center}
[data-testid="InputInstructions"]{display:none!important}
.st-key-hero .art{position:absolute;right:0;bottom:0;width:min(560px,70%);opacity:.09;pointer-events:none}
.st-key-hero .h1{font-family:var(--display);font-weight:600;font-size:clamp(40px,6.4vw,72px);line-height:1.02;letter-spacing:.06em;margin:0 auto 14px;max-width:14ch}
.st-key-hero .sub{text-transform:uppercase;letter-spacing:.22em;font-size:11px;opacity:.85;margin:0 0 22px}
.st-key-searchbox [data-testid="stFormSubmitButton"] button {
    background: #0B1F3A !important;
    color: #fff !important;
    border: 1px solid #0B1F3A !important;
    border-radius: 999px;
    padding: 5px !important;
}
.st-key-searchbox [data-testid="stFormSubmitButton"] button:hover {
    background: #222 !important;
    border-color: #222 !important;
}
.st-key-searchbox{max-width:560px;margin:0 auto;text-align:left}
.st-key-searchbox [data-testid="stForm"]{background:#fff;border:0;border-radius:999px;padding:5px;box-shadow:0 6px 24px rgba(0,0,0,.18)}
.st-key-searchbox [data-testid="stHorizontalBlock"]{align-items:center;gap:0}
.st-key-searchbox [data-baseweb="input"],.st-key-searchbox [data-baseweb="base-input"],.st-key-searchbox [data-testid="stTextInputRootElement"]{border:0!important;background:transparent!important;box-shadow:none!important}
.st-key-searchbox input{color:#1E2433;font-size:14px;padding:8px 16px}
.st-key-searchbox .stButton button{padding:9px 26px;font-size:13.5px;width:100%}
.st-key-results{max-width:536px;margin:10px auto 0;background:#fff;border-radius:14px;overflow:hidden;box-shadow:0 12px 30px rgba(0,0,0,.18);text-align:left}
.st-key-results .stButton button{width:100%;justify-content:flex-start;text-align:left;background:#fff;border-radius:0;border-bottom:1px solid var(--line);padding:12px 16px;font-size:14px;font-weight:400}
.st-key-results .stButton button:hover{background:var(--cardhead);filter:none}
.st-key-results .stButton button p{color:#1E2433 !important;}
.st-key-results [data-testid="stMarkdownContainer"],.st-key-results [data-testid="stMarkdownContainer"] *{color:#1E2433}
.st-key-results .nohit,.st-key-results .nohit *{color:#1E2433!important}
.st-key-results .nohit{padding:14px 16px 20px;font-size:13.5px}
.st-key-wrap{max-width:1180px;margin:0 auto;padding:0 24px;width:100%}
.features{display:grid;grid-template-columns:repeat(4,1fr);gap:24px;padding:40px 0 30px;text-align:center}
.feat .ic{width:66px;height:66px;border-radius:50%;display:grid;place-items:center;margin:0 auto 12px;color:#fff}
.feat .ic svg{width:28px;height:28px}
.feat h3{margin:0;padding:0;font-size:11.5px;letter-spacing:.1em;text-transform:uppercase;font-weight:600}
.feat p{margin:2px 0 0;font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.billhead{text-align:center;padding:14px 0 26px}
.eyebrow{font-family:var(--ital);font-style:italic;color:var(--navy);font-size:17px;margin:0 0 4px}
.billhead .h2{font-size:clamp(22px,2.8vw,30px);line-height:1.25;font-weight:600;margin:0 auto 12px;max-width:26ch}
.chips{display:flex;gap:8px;justify-content:center;flex-wrap:wrap}
.chip{background:var(--cardhead);border:1px solid var(--line);color:var(--navy);border-radius:999px;padding:3px 12px;text-transform:uppercase;letter-spacing:.08em;font-size:10.5px;font-weight:600}
[data-testid="stExpander"]{border:1px solid var(--line)!important;border-radius:12px!important;box-shadow:var(--shadow);overflow:hidden;margin-bottom:20px;background:#fff}
[data-testid="stExpander"] summary{background:var(--cardhead);padding:16px 20px;font-weight:600;color:var(--navy)}
.src{font-size:12px;color:var(--muted)}
.rows{list-style:none;margin:0;padding:0}
.rows li{display:grid;grid-template-columns:110px 70px 130px minmax(0,1fr);gap:12px;padding:15px 4px;border-top:1px solid var(--line);align-items:start}
.rows li:first-child{border-top:0}
.rows .dt{color:var(--muted);white-space:nowrap}
.rows .dt.nd{font-style:italic;font-size:12.5px}
.rows .br{color:var(--muted)}
.rows .empty{grid-column:1/-1;color:var(--muted);font-size:13px}
.badge{display:inline-block;text-transform:uppercase;letter-spacing:.07em;font-size:10px;font-weight:600;padding:3px 11px;border-radius:999px;background:#E7EAF0;color:#4B5363;white-space:nowrap}
.b-referred{background:#CFE3F3;color:#2D5F8A}.b-concurred{background:#E6D6AE;color:#6F5418}
.b-hearing{background:#EFCBE3;color:#83305F}.b-extension{background:#ECE2A0;color:#5E5210}
.b-accompanied,.b-new-draft{background:var(--navy);color:#fff}
.mc{border-top:1px solid var(--line);padding:12px 0 4px}.mc:first-of-type{border-top:0;padding-top:0}
.mh{font-weight:600;color:var(--navy);margin-bottom:8px}
.tiles{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
.tile{background:var(--cardhead);border:1px solid var(--line);border-radius:10px;padding:10px 8px;text-align:center}
.tile b{display:block;font-size:22px;color:var(--navy);line-height:1.1}
.tile span{font-size:10.5px;color:var(--muted);line-height:1.3;display:block;margin-top:2px}
.mt{font-size:12.5px;color:var(--muted);margin:6px 0 0}
.b-introduced{background:#D6E6F5;color:#2D5F8A}.b-merged{background:var(--navy);color:#fff}
.b-reported{background:#CDE8D2;color:#2D6A3E}.b-discharged{background:#F2D3C4;color:#8A3E1D}
.b-second-reading,.b-third-reading,.b-orders-of-the-day,.b-engrossed,.b-order-adopted{background:#D9D3F0;color:#4A3C8C}
.b-enacted,.b-signed-into-law{background:#2D6A3E;color:#fff}
[class*="st-key-acard"]{background:#fff;border:1px solid var(--line);border-radius:12px;box-shadow:var(--shadow);padding:20px 22px;margin-bottom:20px}
.h4{font-family:var(--ital);font-style:italic;font-weight:600;color:var(--navy);font-size:19px;margin:0 0 12px}
.wh{padding:10px 0;border-top:1px solid var(--line)}.wh:first-of-type{border-top:0;padding-top:0}
.wh .k{color:var(--navy);text-transform:uppercase;letter-spacing:.08em;font-size:10px;font-weight:600}
.wh p{margin:2px 0 0;font-size:13.5px}
.rb{padding:12px 0 6px;border-top:1px solid var(--line)}.rb.first{border-top:0;padding-top:0}
.rb .n{font-weight:600;font-size:15px}
.rb .k{text-transform:uppercase;letter-spacing:.07em;font-size:10.5px;color:var(--muted);margin-bottom:8px}
.dash{border:1px dashed var(--line);border-radius:8px;padding:9px 12px;font-size:12px;color:var(--muted);margin-bottom:10px}
.muted{color:var(--muted);font-size:13.5px;margin:0}
.stButton button,[data-testid="stLinkButton"] a{background:var(--navy);color:#fff!important;border:0;border-radius:999px;padding:5px 18px;font-size:12.5px;font-weight:500;min-height:0}
.stButton button:hover,[data-testid="stLinkButton"] a:hover{filter:brightness(1.15);color:#fff!important}
.stButton button p{color:#fff}
.indexh{font-family:var(--ital);font-style:italic;font-weight:600;color:var(--navy);font-size:22px;text-align:center;margin:6px 0 4px}
.lead{text-align:center;color:var(--muted);margin:0 0 24px}
[class*="st-key-bcard"]{background:#fff;border:1px solid var(--line);border-radius:12px;box-shadow:var(--shadow);padding:18px 20px;margin-bottom:16px}
.bt{font-weight:500;line-height:1.4;margin-bottom:10px;min-height:2.8em}
.bm{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:12px}
.nums{color:var(--navy);font-weight:600;font-size:13px}
.foot{background:var(--deep);color:#DCE3F1;padding:36px 0 40px;margin-top:40px}
.foot .wrap{display:grid;grid-template-columns:1fr 1fr;gap:28px}
.foot .fn{text-transform:uppercase;letter-spacing:.1em;font-size:12px;font-weight:600;color:#fff;margin:0 0 6px}
.foot p{margin:0 0 18px;font-size:13px;max-width:46ch;opacity:.9}
.foot a{color:#DCE3F1}
.st-key-acard_match [data-testid="stMarkdownContainer"]{margin-bottom:14px}
.st-key-acard_match .h4{margin-bottom:10px}
.st-key-acard_match .mh{margin:4px 0 16px}
.st-key-acard_match .tiles{margin-bottom:16px;gap:12px}
.st-key-acard_match .tile{padding:16px 10px}
.st-key-acard_match .mt{margin:0 0 6px;line-height:1.7}
.st-key-acard_match [data-testid="stExpander"]{margin:18px 0 14px}
@media (max-width:700px){.features{grid-template-columns:repeat(2,1fr)}.rows li{grid-template-columns:auto 1fr}.foot .wrap{grid-template-columns:1fr}}
</style>"""

ART = ('<svg class="art" viewBox="0 0 400 220" aria-hidden="true" fill="#fff"><rect x="20" y="150" width="360" height="70"/>'
       '<rect x="60" y="120" width="280" height="34"/><path d="M130 120a70 70 0 0 1 140 0z"/><rect x="196" y="30" width="8" height="22"/>'
       '<circle cx="200" cy="28" r="7"/><rect x="150" y="105" width="100" height="18"/></svg>')
ICONS = [("--c1", "Full history", "Every action since filing", '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>'),
         ("--c2", "Companion bills", "House and Senate together", '<rect x="8" y="8" width="11" height="12" rx="2"/><path d="M5 16V6a2 2 0 0 1 2-2h8"/>'),
         ("--c3", "Related bills", "Drafts and study orders", '<circle cx="6" cy="6" r="2.2"/><circle cx="18" cy="9" r="2.2"/><circle cx="8" cy="18" r="2.2"/><path d="M8 6h3a5 5 0 0 1 5 3M6 8.2v7.6"/>'),
         ("--c4", "Budget links", "FY26–27 matches", '<circle cx="12" cy="12" r="8.5"/><path d="M14.8 9.3c-.5-.9-1.6-1.4-2.8-1.4-1.6 0-2.8.8-2.8 2s1.2 1.7 2.8 2 2.8.8 2.8 2-1.2 2-2.8 2c-1.3 0-2.4-.6-2.9-1.5M12 6.5v11"/>')]


def md(html):
    """Streamlit's markdown breaks HTML blocks at blank lines, so send each block as one line."""
    st.markdown(" ".join(html.split()), unsafe_allow_html=True)


md(CSS)  # the stylesheet was defined but never sent to the page


@st.cache_data
def load():
    bills = bd.load_bills()
    groups, group_of = bd.group_bills(bills)
    updated = datetime.fromtimestamp(bd.BILLS_FILE.stat().st_mtime).strftime("%b %d, %Y")
    agenda = bd.load_agenda_ids()
    for g in groups:  # the crawler also saved related bills that are not on the agenda
        g["agenda"] = (not agenda) or any(i in agenda for i in g["ids"])
    return bills, groups, group_of, bd.load_budget(), bd.load_merge_scores(), updated


bills, groups, group_of, budget, scores, updated = load()
agenda_groups = [g for g in groups if g["agenda"]]
agenda_count = sum(len(g["ids"]) for g in agenda_groups)
by_key = {g["key"]: g for g in groups}


@st.cache_data
def sections_for(src, tgt):
    return bd.load_merge_sections(src, tgt)


def goto(bid):
    """Open the page for any tracked bill and clear the search box."""
    st.session_state["sel"] = group_of[bid]["key"]
    st.session_state["query"] = ""
    st.session_state["q_text"] = ""
    st.query_params["bill"] = bid


def go_home():
    st.session_state["sel"] = None
    st.session_state["query"] = ""
    st.session_state["q_text"] = ""
    st.query_params.clear()


def run_search():
   
    q = st.session_state.get("q_text", "")
    st.session_state["query"] = q
    hits = bd.search(q, groups)
    if len(hits) == 1 or (hits and hits[0][0] >= 100):  # one clear match: open it straight away
        goto(hits[0][1]["ids"][0])


if "sel" not in st.session_state:
    wanted = bd.normalize_reference(st.query_params.get("bill"))
    st.session_state["sel"] = group_of[wanted]["key"] if wanted in group_of else None


def rows_html(b, branch="All"):
    rows = [a for a in b["acts"] if branch == "All" or a["branch"] == branch]
    if not rows:
        return f'<ul class="rows"><li><span class="empty">No {branch.lower()} actions for {bd.show(b["id"])}.</span></li></ul>'
    li = "".join(
        f'<li><span class="dt{"" if a["date"] else " nd"}">{bd.fmt_date(a["date"]) if a["date"] else "Date not listed"}</span>'
        f'<span class="br">{a["branch"]}</span><span><span class="badge b-{a["stage"].lower().replace(" ", "-")}">{a["stage"]}</span></span>'
        f'<span>{bd.linkify(a["action"])}</span></li>' for a in rows)
    return f'<ul class="rows">{li}</ul>'



md(f'<div class="util"><div class="wrap"><span>Session {bd.SESSION}, 2025–2026</span><span>Progressive Massachusetts × BU Spark!</span>'
   f'<span>Last updated {updated}</span></div></div>'
   '<nav class="nav"><div class="wrap"><span class="logo">MA Bill Tracker</span>'
   '<div class="links"><a href="#bills">Bills</a><a href="#about">About</a></div></div></nav>')

with st.container(key="hero"):
    md(f'{ART}<div class="h1">What happened to this bill?</div><p class="sub">Search bills by number or name</p>')
    with st.container(key="searchbox"):
        with st.form("searchform", border=False):
            c_in, c_btn = st.columns([5, 1])
            c_in.text_input("Search by bill number or name", key="q_text", label_visibility="collapsed",
                            placeholder="Type a bill name or number, e.g. Medicare for All or S.860")
            c_btn.form_submit_button("Search", on_click=run_search)
    query = st.session_state.get("query", "")
    if query:
        hits = bd.search(query, groups)
        with st.container(key="results"):
            if not hits:
                md(f'<div class="nohit">No bill matches “{bd.esc(query)}”. Try a number like H.1405 or a word from the title.</div>')
            for j, (_, g) in enumerate(hits):
                st.button(f"{g['name']}  ·  {' · '.join(bd.show(i) for i in g['ids'])}", key=f"hit_{j}", on_click=goto, args=(g["ids"][0],))


with st.container(key="wrap"):
    md('<div class="features">' + "".join(
        f'<div class="feat"><div class="ic" style="background:var({c})"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">{p}</svg></div>'
        f'<h3>{t}</h3><p>{s}</p></div>' for c, t, s, p in ICONS) + '</div>')
    key = st.session_state.get("sel")

    if not key:  
        md(f'<div class="indexh" id="bills">Legislative agenda bills</div><p class="lead">{len(agenda_groups)} bills, {agenda_count} bill numbers across the House and Senate</p>')
        for start in range(0, len(agenda_groups), 3):
            for col, (i, g) in zip(st.columns(3, gap="medium"), enumerate(agenda_groups[start:start + 3], start)):
                with col, st.container(key=f"bcard_{i}"):
                    first = bills[g["ids"][0]]
                    md(f'<div class="bt">{bd.esc(g["name"])}</div><div class="bm"><span class="nums">{" · ".join(bd.show(i) for i in g["ids"])}</span>'
                       f'<span class="badge">{bd.status(first)}</span></div>')
                    st.button("Open bill", key=f"open_{i}", on_click=goto, args=(g["ids"][0],))

    else: 
        g = by_key[key]
        members = [bills[i] for i in g["ids"]]
        st.button("← All bills", key="back", on_click=go_home)
        md('<div class="billhead"><p class="eyebrow">' + ("Companion bills" if len(members) > 1 else "Bill") + f'</p><div class="h2">{bd.esc(g["name"])}</div>'
           '<div class="chips">' + "".join(f'<span class="chip">{bd.show(b["id"])} · {bd.status(b)}</span>' for b in members) + '</div></div>')
        left, right = st.columns([2.6, 1], gap="large")

        with left:
            for b in members:
                with st.expander(f"{bd.show(b['id'])}  ·  {len(b['acts'])} actions", expanded=True):
                    md(f'<a class="src" href="{bd.esc(b["url"])}" target="_blank" rel="noopener">Bill page on malegislature.gov</a>')
                    pick = st.pills("Branch", ["All", "House", "Senate", "Joint"], default="All",
                                    key=f"br_{b['id']}", label_visibility="collapsed") or "All"
                    md(rows_html(b, pick))
            with st.container(key="acard_match"):
                            md('<div class="h4">Text match</div>')
                            pairs = bd.merge_rows_for(g["ids"], scores)
                            if not bd.MERGE_SCORES_FILE.exists():
                                md('<p class="muted">No text-match results found. Run <code>python merge_match.py</code> to create '
                                   '<code>output/merge_scores.csv</code>, then clear the app cache.</p>')
                            elif not pairs:
                                md('<p class="muted">No text-match score for this bill. Only bills merged into, or absorbing, another bill are scored '
                                   '(study orders are not).</p>')
                            for row in pairs:
                                md(bd.score_card(row))
                                sec = sections_for(row["original_bill"], row["merged_into"]) if row.get("status") == "ok" else None
                                if sec is not None and not sec.empty:
                                    with st.expander(f"Section by section: {bd.show(row['original_bill'])} → {bd.show(row['merged_into'])}"):
                                        st.dataframe(sec, hide_index=True)
                            if pairs:
                                md('<p class="mt">Automated match. Thresholds are still being tuned, so treat the numbers as a guide.</p>')

        with right:
            with st.container(key="acard_what"):
                md('<div class="h4">What happened</div>' + "".join(
                    f'<div class="wh"><div class="k">{bd.show(b["id"])} · {bd.status(b)}</div><p>{bd.story(b)}</p></div>' for b in members))
            with st.container(key="acard_related"):
                md('<div class="h4">Related bills</div>')
                rel = bd.related(members, set(g["ids"]))
                sim = bd.similar_to(g, agenda_groups) if g["agenda"] else []
                if not rel and not sim:
                    md('<p class="muted">No drafts, study orders, or bundled bills recorded yet.</p>')
                for j, r in enumerate(rel):
                    md(f'<div class="rb{" first" if j == 0 else ""}"><div class="n"><a href="{bd.bill_url_for_reference(r["n"])}" target="_blank" rel="noopener">{bd.show(r["n"])}</a></div>'
                       f'<div class="k">{bd.REL_LABEL[r["k"]]} {" and ".join(bd.show(f) for f in r["froms"])}</div></div>')
                    if r["n"] in bills:
                        with st.expander(f"History of {bd.show(r['n'])}"):
                            md(rows_html(bills[r["n"]]))
                        st.button("Open bill", key=f"rel_{j}_{r['n']}", on_click=goto, args=(r["n"],))
                    else:
                        md('<div class="dash">Its full history lists here.</div>')
                        st.link_button("View history", f"{bd.bill_url_for_reference(r['n'])}/BillHistory")
                for j, o in enumerate(sim):
                    md(f'<div class="rb"><div class="n">{", ".join(bd.show(i) for i in o["ids"])}</div><div class="k">Similar title on the agenda</div>'
                       f'<p class="muted" style="margin-bottom:10px">{bd.esc(o["name"])}</p></div>')
                    st.button("Open bill", key=f"sim_{j}", on_click=goto, args=(o["ids"][0],))
            with st.container(key="acard_budget"):
                matches = [m for b in members for m in budget.get(b["id"], [])]
                body = "".join(f'<div class="wh"><div class="k">{bd.esc(str(m.get("fy")))} · {bd.esc(str(m.get("vehicle")))}</div>'
                               f'<p>{bd.esc(m.get("note") or "")} ' + (f'<a href="{bd.esc(m["url"])}" target="_blank">Source</a>' if m.get("url") else "") + '</p></div>'
                               for m in matches) or ('<p class="muted">No budget or omnibus match recorded yet. '
                                                      'A match will show the budget section and a source link here.</p>')
                md(f'<div class="h4">FY26–27 budget</div>{body}')

md('<div class="foot" id="about"><div class="wrap"><div><p class="fn">MA Bill Tracker</p><p>Follows what happened to the bills on Progressive '
   'Massachusetts’s legislative agenda: amendments, new drafts, study orders, and budget matches. Built by a BU Spark! DS 539 team.</p></div>'
   '<div><p class="fn">Contact</p><p>Progressive Massachusetts<br>Source: <a href="https://malegislature.gov" target="_blank" rel="noopener">malegislature.gov</a></p></div></div></div>')
