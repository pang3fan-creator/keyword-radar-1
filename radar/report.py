"""Leads merged from every signal, and the two reports in Markdown."""
from __future__ import annotations

import re
from collections import Counter

from . import opportunity, config, judge, review, select, usecases
from .i18n import T, t

SHOWN = 20
OTHER_TERMS = 15
POSTS_SHOWN = 3   # posts quoted in full per term
# signal key -> label key, in the order of how early the signal comes
KINDS = select.EARLY
# Signals with a line of their own in the data-status section. Everything else in the
# run's blocks gets the generic line, so a source added without one cannot stay silent.
DRAWN = {"x", "hf", "breakout", "sitemap", "revenue", "ask"}


def leads(cfg: dict, blocks: dict[str, dict]) -> tuple[list[dict], dict]:
    """Terms from every discovery signal, merged; a term in several is the strongest lead.
    Returns (rows, the judge's status)."""
    out: dict[str, dict] = {}
    for kind, block in blocks.items():
        for r in block.get("terms", []):
            row = out.setdefault(r["term"], {"term": r["term"], "kinds": [], "signals": [], "examples": [], "variants": [], "posts": []})
            row["kinds"].append(kind)
            row["signals"].append(r.get("note") or t("note_surge", label=t(f"kind_{kind}"), n=r["recent"], lift=r["lift"]))
            row["examples"] += r.get("examples", [])
            row["posts"] += r.get("posts", [])
            row["variants"] += [v for v in r.get("variants", []) if v not in row["variants"]]
            if r.get("repo"):
                row["repo"] = r["repo"]
            if r.get("about"):
                row["about"] = r["about"]
    rows = list(out.values())
    for r in rows:
        r["known"] = config.known(cfg, r["term"])
        opportunity.tag(r)
    status = judge.score(rows, cfg["judge"]["model"]) if rows else {"judged": 0}
    # Deal the visible slots across signals: a name only Hugging Face found still gets read
    # when X is loud (docs/05 §4.2b). The judge's score orders the rows inside a signal.
    rows = select.order(rows, SHOWN)
    return rows, status


def named(cfg: dict, lead: list[dict]) -> list[dict]:
    """Without the judge's score (no key, a failed call) every term counts; with it, only names."""
    cut = cfg["judge"]["min_score"]
    return [r for r in lead if r.get("named", 1.0) >= cut]


def to_record(cfg: dict, lead: list[dict]) -> list[dict]:
    return [r for r in named(cfg, lead)[:SHOWN] if not r["known"]]


MARK = {"video": " 🎬", "voice": " 🎙", "image": " 🖼", "text": ""}


def _marks(r: dict) -> str:
    """What the thing makes, and ⚡ when a widely shared tutorial or trend shows a manual workflow."""
    return MARK.get(r.get("format", "text"), "") + (" ⚡" if r.get("one_click") else "")


def _signals_cell(r: dict) -> str:
    """The signal cell. A lead only URL listings found is an echo of a name, not a new one."""
    kinds = set(r.get("kinds") or [])
    return "; ".join(r.get("signals") or []) + (t("echo_tag") if kinds and kinds <= select.URL_KINDS else "")


def _cell(text: str) -> str:
    return text.replace("|", "/").replace("\n", " ")


def _score(r: dict) -> str:
    return f"{r['named']:.2f}" if "named" in r else t("dash")


def _state(block: dict, ok: str) -> str:
    return block.get("error") or (t("skipped") if block.get("skipped") else ok)


def cost_micros(*blocks: dict) -> int:
    return sum(int(b.get("cost_micros") or 0) for b in blocks if isinstance(b, dict))


def _cost(*blocks: dict) -> str:
    return f"${cost_micros(*blocks) / 1e6:.3f}"


def topic_lines(cfg: dict, lead: list[dict], b: dict[str, dict], gsc: dict) -> list[str]:
    """Per topic in config.json: the leads, breakout repos and new queries that match it."""
    lines = []
    for name, pattern in cfg["topics"].items():
        pat = re.compile(pattern, re.I)
        hits = [r for r in named(cfg, lead) if pat.search(r["term"] + " " + " ".join(r["examples"][:2]))]
        repos = [r for r in b["breakout"].get("repos") or [] if pat.search(r["repo"] + " " + r["description"])]
        queries = [q for q in gsc.get("queries") or [] if pat.search(q["query"])]
        lines += ["", t("topic_h", name=name), ""]
        if not (hits or repos or queries):
            lines.append(t("topic_none"))
            continue
        lines += [t("topic_lead", term=r["term"], signals="; ".join(r["signals"])) for r in hits[:10]]
        lines += [t("topic_repo", repo=r["repo"], stars=r["stars"], velocity=r["velocity"], desc=r["description"][:60]) for r in repos[:8]]
        lines += [t("topic_query", query=q["query"], impressions=q["impressions"], page=q["page"]) for q in queries[:8]]
    return lines


def _breakout_lines(bo: dict, cfg: dict) -> list[str]:
    lines = ["", t("breakout_h", days=cfg["breakout"]["window_days"]), ""]
    repos = bo.get("repos") or []
    if not repos:
        return lines + [t("recent_none", why=_state(bo, t("no_breakouts")))]
    lines += [t("breakout_cols"), "|---|---|---|---|---|---|"]
    return lines + [f"| {'🆕 ' if r.get('new') else ''}[{r['repo']}](https://github.com/{r['repo']}) | {r['stars']} | {r['velocity']} | "
                    f"{'+' + str(r['delta']) if r['delta'] is not None else t('dash')} | {r['age_days']} | "
                    f"{_cell(r['description'][:60])} |" for r in repos]


def _new_site_lines(ns: dict, cfg: dict) -> list[str]:
    if ns.get("skipped"):
        return []
    c = cfg["new_sites"]
    lines = ["", t("newsite_h", days=c["window_days"], etv=c["min_etv"], kw=c["min_keywords"]), ""]
    sites = ns.get("sites") or []
    if not sites:
        return lines + [t("recent_none", why=ns.get("error") or t("newsite_none"))]
    lines += [t("newsite_cols"), "|---|---|---|---|---|"]
    return lines + [f"| {'🆕 ' if r['new'] else ''}[{r['domain']}](https://{r['domain']}) | {r['created']} | {r['first_seen']} | "
                    f"{r['etv']} | {r['keywords']} |" for r in sites]


def _revenue_lines(rv: dict, cfg: dict) -> list[str]:
    if rv.get("skipped") and not rv.get("no_key"):
        return []
    lines = ["", t("revenue_h", usd=cfg["revenue"]["min_revenue_usd"]), ""]
    if rv.get("no_key"):
        return lines + [t("revenue_nokey")]
    rows = rv.get("products") or []
    if not rows:
        return lines + [t("recent_none", why=rv.get("error") or t("revenue_none"))]
    lines += [t("revenue_cols"), "|---|---|---|---|---|"]
    for p in rows:
        came = t("revenue_zero") if p["from_zero"] else ", ".join(t("revenue_" + c.split("-")[0]) for c in p["came"])
        site = f"[{p['name']}]({p['website']})" if p["website"] else p["name"]
        lines.append(f"| {site} | {_cell(p['about'][:110]) or t('dash')} | ${p['usd']:,} | {p['growth_text']} | {came} |")
    return lines + ["", t("revenue_tos")]


def _asks_lines(ak: dict, cfg: dict) -> list[str]:
    if ak.get("skipped"):
        return []
    lines = ["", t("asks_h"), ""]
    rows, quiet = ak.get("rows") or [], ak.get("quiet") or []
    if not rows and not quiet:
        return lines + [t("recent_none", why=ak.get("error") or t("asks_none", read=ak.get("read", 0), asks=ak.get("asks", 0)))]
    lines += [t("asks_intro", read=ak["read"], asks=ak["asks"], unsized=ak["unsized"], min=cfg["asks"]["min_volume"])]
    if rows:
        lines += ["", t("asks_cols"), "|---|---|---|---|---|---|"]
    for row in rows:
        p = max(row["posts"], key=lambda x: x["score"])
        lines.append(f"| **{row['phrase']}**{t('asks_again') if row.get('again') else ''} | {len(row['posts'])} ({row['score']}) | "
                     f"{', '.join('r/' + s for s in row['subreddits'][:3])} | {row['volume']:,} | {_page_one(row.get('competition'))} | "
                     f"[{_cell(p['title'][:70])}]({p['url']}) |")
    if quiet:
        lines += ["", t("asks_quiet_h", min=cfg["asks"]["min_volume"]), "", t("asks_quiet_cols"), "|---|---|---|---|"]
        for row in quiet:
            p = max(row["posts"], key=lambda x: x["score"])
            lines.append(f"| {row['phrase']} | {len(row['posts'])} ({row['score']}) | {', '.join('r/' + s for s in row['subreddits'][:3])} | "
                         f"[{_cell(p['title'][:80])}]({p['url']}) |")
    if ak.get("errors"):
        lines.append(t("asks_err", why="; ".join(ak["errors"][:3])))
    return lines + ["", t("asks_note")]


def _tutorial_lines(tu: dict) -> list[str]:
    if tu.get("skipped") or not (tu.get("leads") or tu.get("errors")):
        return []
    lines = ["", t("tut_h"), ""]
    for lead in tu.get("leads") or []:
        lines.append(t("tut_lead", term=lead["term"], n=lead["comments"]))
        lines += [f"  - {g['gap']} ({t('gap_' + g['kind'].replace(' ', '_'))}, {g['count']}){' → ' + g['phrase'] if g['phrase'] else ''}"
                  for g in lead["gaps"]]
    if tu.get("errors"):
        lines.append(t("tut_err", why="; ".join(tu["errors"][:3])))
    return lines


def pains(result: dict) -> str:
    """The `pains` command: the gaps people point at for a kind of tool."""
    by = result["by_source"]
    lines = [t("pains_h", keyword=result["keyword"]), "",
             t("pains_src", chrome=by["chrome"], reddit=by["reddit"], youtube=by["youtube"]), ""]
    if result["gaps"]:
        lines += [t("pains_cols"), "|---|---|---|---|---|"]
        for g in result["gaps"]:
            q = g["quotes"][0]
            lines.append(f"| {_cell(g['gap'])} | {t('gap_' + g['kind'].replace(' ', '_'))} | {g['count']} | {g['phrase'] or t('dash')} | "
                         f"[{_cell(q['text'][:90])}]({q['url']}) |")
    else:
        lines.append(t("pains_none"))
    if result["errors"]:
        lines += ["", t("pains_err", why="; ".join(result["errors"][:4]))]
    lines += ["", t("pains_note"), t("cost", cost=_cost(result))]
    return "\n".join(lines) + "\n"


def _gsc_lines(gsc: dict) -> list[str]:
    if gsc.get("off"):
        return []
    lines = ["", t("gsc_h"), ""]
    if not gsc.get("queries"):
        return lines + [t("recent_none", why=_state(gsc, t("gsc_none")))]
    lines += [t("gsc_intro", window=gsc["window"], total=gsc["total_new"], min=gsc["min_impressions"]), "",
              t("gsc_cols"), "|---|---|---|---|"]
    return lines + [f"| {_cell(q['query'])} | {q['impressions']} | {q['clicks']} | {q['page']} |" for q in gsc["queries"]]


def _kind_label(kind: str) -> str:
    return t(f"kind_{kind}") if f"kind_{kind}" in T else kind


def _kind_order(kind: str) -> int:
    return KINDS.index(kind) if kind in KINDS else len(KINDS)


def _ratio(s: dict, key: str) -> str:
    """real / scored, or again / seen: a slow word has no name score, so it shows a dash."""
    seen = s.get("scored" if key == "real" else "seen", 0)
    return f"{s.get(key, 0)}/{seen}" if seen else t("dash")


def _yesno(value: int | None) -> str:
    return t("dash") if value is None else (t("uc_yes") if value else t("uc_no"))


def _review_lines(cfg: dict, rev: dict, summ: dict) -> list[str]:
    """Every window, honestly: the free 1d/3d names, the Trends rise per lane, today's paid
    rows, the queues, and the terms Trends did not answer for."""
    lines = ["", t("review_h"), ""]
    if rev.get("skipped"):
        return lines + [t("review_none", why=t("skipped"))]
    if rev.get("error"):
        return lines + [t("review_failed", why=rev["error"])]
    if summ.get("error"):
        return lines + [t("review_failed", why=summ["error"])]
    nexts = rev.get("next_paid") or {}
    checked = rev.get("checked") or []
    groups: dict[int, list[int]] = {}
    for r in checked:
        if r["days"] < review.TRENDS_FROM:
            groups.setdefault(r["days"], []).append(r.get("age_days", r["days"]))
    parts = []
    for d, ages in sorted(groups.items()):
        txt = t("review_free_n", days=d, n=len(ages))
        if max(ages) > d:                       # a window read late says so: as-of-check, not as-of-day
            span = str(min(ages)) if min(ages) == max(ages) else f"{min(ages)}-{max(ages)}"
            txt += " " + t("review_age", span=span)
        parts.append(txt)
    free_txt = ", ".join(parts) or t("review_free_none")
    paid = [r for r in checked if r["days"] >= review.TRENDS_FROM]
    if paid:
        paid_txt = ", ".join(t("review_free_n", days=d, n=n) for d, n in sorted(Counter(r["days"] for r in paid).items()))
    elif rev.get("errors"):
        paid_txt = t("review_paid_failed")
    else:
        paid_txt = t("review_paid_none", next=t("review_next", day=nexts.get("fast") or t("dash")))
    lines.append(t("review_today", free=free_txt, paid=paid_txt))

    windows = summ.get("windows") or {}
    fast = windows.get("fast") or {}
    slow = windows.get("slow") or {}
    first, third = fast.get("1") or {}, fast.get("3") or {}
    if first or third:
        lines += ["", t("review_names_intro", days=summ.get("window_days", 60)), "",
                  t("review_names_cols"), "|---|---|---|---|---|"]
        for kind in sorted(set(first) | set(third), key=_kind_order):
            a, b = first.get(kind) or {}, third.get(kind) or {}
            lines.append(f"| {_kind_label(kind)} | {a.get('checked', 0)} | {_ratio(a, 'real')} | "
                         f"{b.get('checked', 0)} | {_ratio(b, 'again')} |")
    for lane, table, d1, d2 in (("fast", fast, 7, 14), ("slow", slow, 14, 30)):
        a, b = table.get(str(d1)) or {}, table.get(str(d2)) or {}
        if not a and not b:
            continue
        lines += ["", t("review_rise_intro", lane=t("lane_" + lane), days=summ.get("window_days", 60)), "",
                  t("review_rise_cols", d1=d1, d2=d2), "|---|---|---|---|---|---|"]
        for kind in sorted(set(a) | set(b), key=_kind_order):
            x, y = a.get(kind) or {}, b.get(kind) or {}
            lead = y.get("median_lead")
            lines.append(f"| {_kind_label(kind)} | {x.get('checked', 0)} | {x.get('hit', 0)} | "
                         f"{y.get('checked', 0)} | {y.get('hit', 0)} | "
                         f"{lead if lead is not None else t('dash')} |")
    if paid:
        lines += ["", t("review_term_h"), "", t("review_term_cols"), "|---|---|---|---|---|"]
        for r in paid:
            lines.append(f"| {_cell(r['term'])} | {t('lane_' + r['lane'])} {r['days']}d | "
                         f"{_yesno(r['name_real'])} | {_yesno(r['search_rise'])} | "
                         f"{r['lead_days'] if r['lead_days'] is not None else t('dash')} |")
    pending = summ.get("pending_windows") or {}
    due = summ.get("due_windows") or {}
    lines.append("")
    for lane in ("fast", "slow"):
        lines.append(t("review_wait", lane=t("lane_" + lane),
                       n=sum((pending.get(lane) or {}).values()),
                       due=sum((due.get(lane) or {}).values()), day=nexts.get(lane) or t("dash")))
    lines += ["", t("review_legend", cut=cfg["review"]["name_real_score"])]
    for err in rev.get("errors") or []:
        lines.append(t("review_err", why=err))
    return lines


def _precision_lines(cfg: dict, summ: dict) -> list[str]:
    """The sitemap/new-site sample: echo candidates labeled by whether they already had demand."""
    lines = ["", t("precision_h"), ""]
    if summ.get("error"):
        return []                               # the review section already names the failure
    samples = summ.get("samples") or {}
    if not samples:
        return lines + [t("precision_none", n=cfg["review"]["sampling"]["per_run"])]
    totals = {k: sum(s.get(k, 0) for s in samples.values())
              for k in ("sampled", "new", "searched", "unknown")}
    lines.append(t("precision_intro", days=summ.get("sample_days", 90),
                   cut=cfg["review"]["sampling"]["existing_volume"], **totals))
    lines += ["", t("precision_cols"), "|---|---|---|---|---|"]
    for source, s in sorted(samples.items()):
        lines.append(f"| {source} | {s['sampled']} | {s['new']} | {s['searched']} | {s['unknown']} |")
    return lines


def precision_sample(cfg: dict, result: dict) -> str:
    """The `radar precision` output: ten candidates, their searches a month, the label."""
    lines = [t("precision_h"), ""]
    if not result.get("sampled"):
        lines.append(t("precision_no_candidates") if not result.get("errors")
                     else t("precision_none", n=cfg["review"]["sampling"]["per_run"]))
    else:
        lines += [t("precision_term_cols"), "|---|---|---|---|"]
        for r in result["sampled"]:
            volume = r["volume"] if r["volume"] is not None else t("dash")
            lines.append(f"| {_cell(r['term'])} | {r['source']} | {volume} | {t('sample_' + r['label'])} |")
    for err in result.get("errors") or []:
        lines.append(t("precision_err", why=err))
    lines.append(t("cost", cost=_cost(result)))
    return "\n".join(lines) + "\n"


def _source_line(kind: str, block: dict) -> str:
    """One line for a source without a bespoke one: how much it read, how many names it
    found, and the feeds that failed. An unlabelled kind still shows up -- a source that
    ran and says nothing is the bug this line exists to prevent."""
    if block.get("skipped"):
        no_key = block.get("no_key")
        state = t("st_nokey", name=no_key) if isinstance(no_key, str) else t("skipped")
    elif block.get("error"):
        state = block["error"]
    elif block.get("read") is None:
        state = t("st_ran")
    else:
        state = t("st_source_ok", n=block["read"], found=block.get("found", 0))
    if block.get("failed"):
        state += t("st_failed", names=", ".join(block["failed"]))
    if block.get("capped"):
        state += t("st_capped")
    label = t(f"kind_{kind}") if f"kind_{kind}" in T else kind
    return t("st_source", label=label, state=state)


def _status_lines(b: dict[str, dict], extra: dict[str, dict], lead: list[dict]) -> list[str]:
    x, hf, bo, sm = b["x"], b["hf"], b["breakout"], b["sitemap"]
    lines = ["", t("status_h"), ""]
    if not x.get("skipped"):
        ok = "" if x.get("error") else t("st_x_ok", answered=x["answered"], accounts=x["accounts"], posts=x["posts"]) + \
            (t("st_x_first") if x.get("first_run") else "")
        lines.append(t("st_x", state=_state(x, ok)))
    if not hf.get("skipped"):
        ok = "" if hf.get("error") else t("st_hf_ok", models=hf["models"], spaces=hf.get("spaces", 0)) + (t("st_first") if hf.get("first_run") else "")
        lines.append(t("st_hf", state=_state(hf, ok)))
    ok = "" if bo.get("error") or bo.get("skipped") else t("st_breakout_ok", n=bo["searched"]) + \
        (t("st_breakout_first") if bo.get("first_run") else "")
    lines.append(t("st_breakout", state=_state(bo, ok)))
    rv = b.get("revenue", {"skipped": True})
    if rv.get("skipped") and not rv.get("no_key"):
        lines.append(t("st_revenue", state=t("skipped_weekly")))
    else:
        ok = t("revenue_nokey_short") if rv.get("no_key") else "" if rv.get("error") else t("st_revenue_ok", n=rv["read"]) + \
            (t("st_first") if rv.get("first_run") else "")
        lines.append(t("st_revenue", state=_state(rv, ok) if not rv.get("no_key") else ok))
    ak = b.get("ask", {"skipped": True})
    if ak.get("skipped"):
        lines.append(t("st_asks", state=t("skipped_weekly")))
    else:
        lines.append(t("st_asks", state=_state(ak, "" if ak.get("error") else t("st_asks_ok", read=ak["read"], asks=ak["asks"]))))
    for site, s in sm.get("sites", {}).items():
        state = s.get("error") or (t("st_site_first") if s.get("first_run") else t("st_site_ok", urls=s["urls"], new=s["new"]))
        lines.append(t("st_site", site=site, state=state))
    if sm.get("error"):
        lines.append(t("st_sitemaps", state=sm["error"]))
    elif sm.get("skipped"):
        lines.append(t("st_sitemaps", state=t("skipped")))
    for kind, block in b.items():
        if kind not in DRAWN:
            lines.append(_source_line(kind, block))
    for key, label in (("judge", "st_judge"), ("record", "st_record")):
        if extra.get(key, {}).get("error"):
            lines.append(t(label, state=extra[key]["error"]))
    note = select.quota_note(lead, SHOWN)
    if note:
        lines.append(t("st_quota", n=note[1], total=note[2], signal=t("kind_" + note[0])))
    return lines


def daily(cfg: dict, lead: list[dict], b: dict[str, dict], gsc: dict, rev: dict, summ: dict, extra: dict[str, dict]) -> str:
    lines = [t("title"), *keyword_table(cfg, extra.get("usecases", {"skipped": True})), "", t("leads_h"), "", t("leads_cols"), "|---|---|---|---|---|---|"]
    names_ = named(cfg, lead)
    for r in names_[:SHOWN]:
        ex = _cell(" / ".join(e[:50] for e in r["examples"][:2]))
        lines.append(f"| **{r['term']}**{_marks(r)} | {_signals_cell(r)} | {_score(r)} | {r['known'] or t('none')} | "
                     f"{', '.join(r['variants'][1:]) or t('dash')} | {ex} |")
    if any(_marks(r) for r in names_[:SHOWN]):
        lines += ["", t("tags_note")]
    rest = [r["term"] for r in lead if r not in names_][:OTHER_TERMS]
    if rest:
        lines += ["", t("other_terms") + ", ".join(rest)]
    lines += topic_lines(cfg, lead, b, gsc)
    recent = extra.get("recent_sources", {"skipped": True})
    if not recent.get("skipped"):
        lines += ["", t("recent_h"), ""]
        rows = recent.get("rows") or []
        lines += [f"- **{r['term']}**: {r['note']}" for r in rows] if rows \
            else [t("recent_none", why=recent.get("error") or t("no_new_names"))]
    lines += _breakout_lines(b["breakout"], cfg)
    lines += _new_site_lines(b.get("newsite", {"skipped": True}), cfg)
    lines += _revenue_lines(b.get("revenue", {"skipped": True}), cfg)
    lines += _asks_lines(b.get("ask", {"skipped": True}), cfg)
    lines += _tutorial_lines(extra.get("tutorials", {"skipped": True}))
    lines += _gsc_lines(gsc)
    lines += _review_lines(cfg, rev, summ)
    lines += _precision_lines(cfg, summ)
    lines += _status_lines(b, extra, lead)
    lines.append(t("cost", cost=_cost(b["x"], rev, b.get("newsite", {}), b.get("ask", {}), extra.get("usecases", {}),
                                      extra.get("tutorials", {}))))
    return "\n".join(lines) + "\n"


def _page_one(comp: dict | None) -> str:
    """The page-one cell: verdict, weak results, difficulty, ads."""
    if not comp:
        return t("dash")
    bits = [t("pc_" + comp["verdict"])]
    if comp.get("weak") is not None:
        bits.append(t("pc_weak", n=comp["weak"]))
    if comp.get("kd") is not None:
        bits.append(t("pc_kd", kd=comp["kd"]))
    if comp.get("ads"):
        bits.append(t("pc_ads"))
    if comp.get("built") is not None:
        bits.append(t("pc_built", n=f"{comp['built']:,}"))
    if comp.get("paid"):
        bits.append(t("pc_paid", n=len(comp["paid"])))
    return " · ".join(bits)


def _page_one_lines(cfg: dict, uc: dict) -> list[str]:
    rows = [r for r in uc["rows"] if r.get("competition")]
    if not rows and not uc.get("competition_errors"):
        return []
    lines = [t("pc_note", dr=cfg["competition"]["weak_dr"])]
    if rows and all(r["competition"].get("weak") is None for r in rows):
        lines.append(t("pc_no_dr"))
    weakest = [r for r in rows if r["competition"].get("weakest")]
    if weakest:
        lines += ["", t("pc_weakest_h")]
        for r in weakest:
            w, kinds = r["competition"]["weakest"], r["competition"]["kinds"]
            key = "pc_weakest" if w["dr"] < cfg["competition"]["weak_dr"] else "pc_weakest_strong"
            lines.append(t(key, phrase=r["phrase"], domain=w["domain"], dr=w["dr"], pos=w["position"],
                           kinds=", ".join(f"{t('pk_' + k)} {n}" for k, n in sorted(kinds.items(), key=lambda x: -x[1])))
                         + (t("pc_paid_who", who=", ".join(r["competition"]["paid"][:3])) if r["competition"].get("paid") else ""))
    if uc.get("competition_errors"):
        lines.append(t("pc_err", names="; ".join(uc["competition_errors"])))
    return lines


def keyword_table(cfg: dict, uc: dict) -> list[str]:
    """One table for the day: the names read and the generic terms behind them, each with a decision."""
    if uc.get("skipped"):
        return []
    lines = ["", t("uc_h"), ""]
    if uc.get("error"):
        return lines + [uc["error"]]
    if not uc.get("names"):
        return lines + [t("uc_none")]
    c = cfg["usecases"]
    if usecases.degraded(uc):
        lines += [t("uc_degraded"), ""]
    counts = uc.get("counts") or {}
    lines += [t("uc_intro", names=", ".join(uc["names"]), proposed=uc["proposed"], relevant=uc["relevant"], kept=uc["kept"],
                known=counts.get("known", 0), below=counts.get("below_threshold", 0), unknown=counts.get("unknown", 0),
                min=c["min_volume"], month=uc["volume_month"] or "?"),
              t("uc_bench", bench=", ".join(uc.get("bench_usable") or [uc["benchmark"]]), bench_daily=uc["bench_daily"])
              if uc.get("bench_daily") else t("uc_bench_none", bench=uc["benchmark"])]
    if uc.get("bench_dropped"):
        lines.append(t("uc_bench_dropped",
                       names=", ".join(f"{k} ({v['reason']})" for k, v in uc["bench_dropped"].items())))
    lines += ["", t("uc_cols"), "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in uc["rows"]:
        generic = r["kind"] == "generic"
        none = r.get("no_data")
        peak = f"{r['peak_vs']} vs {r['bench_level']}" if "peak_vs" in r else t("dash")
        lines.append(
            f"| **{r['phrase']}**{MARK[opportunity.fmt({'term': r['phrase']})]}{' 🔎' if r.get('source') == 'searched' else ''}"
            f"{' ⚠' if generic and r['brand'] else ''} | "
            f"{t('uc_type_generic' if generic else 'uc_type_name')} | "
            f"{', '.join(r['names']) or t('dash')} | {t('dash') if none else t('uc_yes' if r['new'] else 'uc_no')} | "
            f"{r['per_day'] if 'per_day' in r else t('dash')} | {t('uc_size_' + r.get('size_status', 'unknown'))} | "
            f"{r.get('leading') or t('dash')} | "
            f"{r.get('started') or t('dash')} | {peak} | "
            f"{t('dash') if none else r['peak_day']} | {'×' + str(r['momentum']) if r.get('momentum') is not None else t('dash')} | "
            f"{t('uc_now_none') if none else t('uc_now_' + r['now'])}{' (' + uc['geo'] + ')' if r.get('trend_geo') else ''} | "
            f"{_page_one(r.get('competition'))} | {t('uc_' + r['decision'])}{' ↓' if r.get('demoted') else ''} |")
    lines += ["", t("uc_rules", min_daily=c["min_daily"])]
    lines += _page_one_lines(cfg, uc)
    if any(r["kind"] == "generic" and r["brand"] for r in uc["rows"]):
        lines.append(t("uc_brand_note"))
    if any(r.get("trend_geo") for r in uc["rows"]):
        lines.append(t("uc_geo_note", geo=uc["geo"]))
    if uc.get("country_errors"):
        lines.append(t("uc_geo_err", names="; ".join(uc["country_errors"])))
    if any(r.get("source") == "searched" for r in uc["rows"]):
        lines.append(t("uc_searched_note"))
    said = [f"- **{r['phrase']}** ({', '.join(r['names'])}): “{_cell(r['evidence'])}”" for r in uc["rows"]
            if r["kind"] == "generic" and r["evidence"] and r.get("source") != "searched"]
    if said:
        lines += ["", t("uc_said_h"), *said]
    if uc.get("tails"):
        lines += ["", t("uc_tails_h"), *[f"- **{n}**: {', '.join(v[:10])}" for n, v in uc["tails"].items()]]
    if uc.get("cosearch"):
        lines += ["", t("uc_cosearch_h") + " " + ", ".join(t("uc_cosearch_item", term=x["term"], name=x["with"]) for x in uc["cosearch"])]
    if uc.get("no_evidence"):
        lines += ["", t("uc_no_evidence", names=", ".join(uc["no_evidence"]))]
    if uc.get("posts_error"):
        lines += ["", t("uc_posts_err", why=uc["posts_error"])]
    if uc.get("related_errors"):
        lines += ["", t("uc_related_err", names="; ".join(uc["related_errors"]))]
    elif not uc.get("related"):
        lines += ["", t("uc_related_off")]
    return lines


def usecase_leads(uc: dict) -> list[dict]:
    """The generic terms as leads, for the 14-day review."""
    return [{"term": r["phrase"], "kinds": ["usecase"], "variants": [r["phrase"]],
             "signals": [t("note_usecase", names=", ".join(r["names"]), volume=r.get("volume", 0))]}
            for r in uc.get("rows", []) if r["kind"] == "generic" and r.get("volume_status") != "unknown"] + \
        [{"term": x["term"], "kinds": ["cosearch"], "variants": [x["term"]], "signals": [t("note_cosearch", name=x["with"])]}
         for x in uc.get("cosearch", [])]


def _clip(text: str, n: int) -> str:
    """Cut at a word boundary with an ellipsis, not mid-word."""
    if len(text) <= n:
        return text
    cut = text[:n].rsplit(" ", 1)[0]
    return (cut if len(cut) > n // 2 else text[:n]) + "…"


def posts_lines(rows: list[dict]) -> list[str]:
    """Each term's posts in full, with a link: what was said and where, without opening X."""
    lines = []
    for r in rows:
        for p in r.get("posts", [])[:POSTS_SHOWN]:
            if not lines:
                lines += ["", t("posts_h"), ""]
            link = t("post_link", url=p["url"]) if p.get("url") else ""
            lines.append(f"- **{r['term']}** · @{p['account']} ♥{p['likes']}{link}  \n  {p['text']}")
    return lines


def slow(cfg: dict, result: dict) -> str:
    """The weekly combo-word list: the candidates that were measured, never a name slot."""
    cost = f"${result.get('cost_micros', 0) / 1e6:.3f}"
    lines = [t("slow_title"), "", t("slow_intro", seeds=result["seeds"], candidates=result["candidates"],
                                    rows=len(result["rows"]), cost=cost)]
    if not result.get("paid"):
        lines += ["", t("slow_free")]
    rows = result["rows"]
    if not rows:
        why = "; ".join(result.get("errors", [])[:2]) or t("no_new_names")
        return "\n".join(lines + ["", t("slow_none", why=why), "", t("cost", cost=cost)]) + "\n"
    lines += ["", t("slow_cols"), "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        now = r.get("now")
        decision = r.get("decision")
        lines.append(f"| **{r['term']}** | {', '.join(r.get('objects') or []) or t('dash')} | "
                     f"{t('uc_yes') if r.get('fresh') else t('uc_no')} | {r.get('volume') or 0:,} | "
                     f"{r.get('per_day') if r.get('per_day') is not None else t('dash')} | "
                     f"{t('uc_now_' + now) if now else t('dash')} | {_page_one(r.get('competition'))} | "
                     f"{t('uc_' + decision) if decision else t('dash')} |")
    lines += ["", t("slow_rules", min=f"{cfg['slow']['min_daily']:,}")]
    status = []
    for err in result.get("errors", [])[:5]:
        status.append(t("slow_failed", what=err))
    for err in result.get("paid_errors", [])[:5]:
        status.append(t("slow_failed", what=err))
    asked, trends = result.get("asked_volumes", 0), result.get("asked_trends", 0)
    if result.get("candidates") and asked and result["candidates"] > asked:
        status.append(t("slow_caps", n=asked, m=result["candidates"]))
    if asked and trends and trends < asked:
        status.append(t("slow_caps_trends", n=trends, m=asked))
    spend = result.get("spend") or {}
    if spend:
        status.append(t("slow_spend", volumes=f"${spend.get('volumes', 0) / 1e6:.3f}",
                        trends=f"${spend.get('trends', 0) / 1e6:.3f}",
                        page_one=f"${spend.get('page_one', 0) / 1e6:.3f}"))
    if status:
        lines += ["", t("slow_status_h"), ""] + status
    lines.append(t("cost", cost=cost))
    return "\n".join(lines) + "\n"


def sources(cfg: dict, lead: list[dict], b: dict[str, dict], extra: dict[str, dict]) -> str:
    lines = [t("sources_title"), "", t("sources_cols"), "|---|---|---|---|---|"]
    top = named(cfg, lead)[:SHOWN]
    for r in top:
        ex = _cell("<br>".join(_clip(e, 60) for e in r["examples"][:2]))
        lines.append(f"| **{r['term']}** | {'; '.join(r['signals'])} | {_score(r)} | {r['known'] or t('none')} | {ex} |")
    lines += posts_lines(top)
    lines.append("")
    for key, label in (("x", "st_x"), ("hf", "st_hf")):
        if b[key].get("error"):
            lines.append(t(label, state=b[key]["error"]))
    for key, label in (("judge", "st_judge"), ("record", "st_record")):
        if extra.get(key, {}).get("error"):
            lines.append(t(label, state=extra[key]["error"]))
    lines.append(t("cost", cost=_cost(b["x"])))
    return "\n".join(lines) + "\n"
