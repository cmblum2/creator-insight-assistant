# PDF Agency-Report Feature — Portable Framework Spec

A self-contained spec of the one-click "Agency report (PDF)" feature, written so it can be
implemented in a different repository. It describes the architecture, data contracts, section
logic, rendering system, and the hard-won gotchas — **with no private data**. Adapt the
data-source layer to whatever the target repo has; everything else ports as-is.

This repo's implementation lives in `app/report.py` (assembly + HTML render + PDF print),
wired to `GET /report` and `GET /report.pdf` in `app/server.py`, with a button in the
dashboard top bar. It renders entirely from this repo's **synthetic** data
(`scripts/gen_data.py`).

---

## 1. What the feature delivers

One button on the dashboard → one printable document (HTML page + PDF download) that turns
a live analytics system into a weekly artifact a non-technical team can act on:

- **Level AND direction** — every KPI carries a sparkline + month-over-month delta.
- **Decisions with exact instructions** — not "this campaign is bad" but "raise the target
  to ≥ X.XX; it earns $Y per $1 now at $Z/day".
- **Problems ranked by estimated dollars at stake.**
- **Trend desk** — metric × month matrix with slope-classified trajectories.
- **Forward 30 days** — forecasts, act-by lists, watchlists, the system's own ops calendar.
- **Voice-of-customer** — weekly themes with real quotes, joined per campaign.
- **Technical appendix** — model diagnostics: skill, calibration, experiments, drift — proof
  the system learns, for readers who want to check the math.

Design goal: *quant-desk report, not status page*. Action first, economics heavy, internals
in the back, one plain-English methodology box so readers trust the numbers.

## 2. Architecture

```
app/report.py           # everything: data assembly + HTML render + PDF print
server (FastAPI):
  GET /report           # HTMLResponse — the report as a web page (also print-preview)
  GET /report.pdf       # FileResponse — same page printed via installed Chrome/Chromium
  (optional ?budget=N   # feeds the budget-allocation section)
dashboard index.html:   # one button in the top bar:
  <button onclick="window.open('/report.pdf','_blank')">⬇ Agency report (PDF)</button>
```

No new Python deps: PDF rendering shells out to **installed Chrome/Chromium**
(`--print-to-pdf`). The Dockerfile installs `chromium` so it works on the deploy too; if a
machine lacks a browser, `/report` (HTML) still works and users print from the browser.

### PDF pipeline (verbatim pattern)

```python
def build_report_pdf(budget=50000) -> Path:
    html_doc = build_report_html(budget)
    tmp = Path(tempfile.mkdtemp(prefix="report_"))
    src, out = tmp / "report.html", tmp / "report.pdf"
    src.write_text(html_doc, encoding="utf-8")
    cmd = [chrome_path(), "--headless=new", "--disable-gpu", "--no-first-run", "--no-sandbox",
           f"--user-data-dir={tmp / 'chrome-tmp'}",        # NEVER a shared/real profile
           "--no-pdf-header-footer", f"--print-to-pdf={out}", src.as_uri()]
    subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    return out
```

## 3. Data assembly — the guard pattern

One function `build_report_data()` gathers every section's input. **Each source is fetched
inside its own try/except**; on failure the section gets `{"note": "unavailable: ..."}` and
renders an honest italic line instead of killing the report:

```python
def grab(key, fn):
    try:    out[key] = fn()
    except Exception as e:  out[key] = {"note": f"unavailable: {str(e)[:140]}"}
```

Rules:
- Lazy-import each data module *inside* its grab fn — a broken module degrades one section
  instead of breaking the whole report's import.
- Prefer precomputed snapshots over live recompute for expensive views (fall back to live).
- The LLM-written narrative (if any) is just another guarded grab — the report must render
  fully without it.

### Input contract (this repo's mapping)

| Section key | Source module | Shape highlights |
|---|---|---|
| `decisions` | `app/decide.py` | `queue[]` of `{action, target, title, why[], impact, type}` |
| `scorecard` / `funnel_diag` | `app/scorecard.py` | funnel + power-law + waste diagnosis |
| `economics` / `prize` / `sensitivity` | `app/economics.py` | portfolio ROI, prize, margin×cost grid |
| `allocate` | `app/allocator.py` | paid-vs-sampling split + per-campaign return + tiers |
| `recommend` | `app/recommend.py` | `candidates[]` with cold-start + guardrail exclusions |
| `voc` / `voc_campaigns` / `intent_week` | `app/voc.py` + CSV joins | category mix, competitor board, weekly themes |
| `spark` | `app/spark.py` | ROAS by video age at first spark |
| `post` | `app/post_rate.py` | ship→post→sale funnel |
| `hetero` | `app/heterogeneity.py` | subgroup CATE |
| `theme_lift` | `app/theme_lift.py` | comment-theme → conversion (Bonferroni) |
| `holdout` | `app/holdout.py` | matched-control lift + CI + p-value |
| `drift` | `app/drift.py` | input PSI by feature + flags |
| `recommender` | `app/recommender_eval.py` | rank-IC, precision@K, calibration-by-rank |
| `ltv` / `retention` | `app/cohorts.py` | LTV + retention curve |
| `trends` | `data/monthly_trends.csv` | metric × month, last 2 months immature |

## 4. Report structure (section order matters)

1. **Header** — title; generated-at, data-as-of, corpus size; one "capability strip" line.
2. **Scoreboard** — stat tiles: value + sparkline + MoM delta + one-line sub.
3. **Three moves this week** — the biggest STOP, the best BOOST, the week's SEED sized in $.
4. **Problem areas — ranked by dollars at stake.**
5. **Action queue (full detail)** — verdict chip · target · why bullets · highlighted `→` instruction.
6. **Voice of the customer — this week** — theme cards + per-campaign quotes.
7. **Trend desk** — metric × month with maturation-aware trajectories.
8. **What's next — forward 30 days** — forecasts, act-by, watchlist, the system's own calendar.
9. **Deep dives** — budget allocation + sensitivity, timing, program P&L, next picks, corpus VoC.
10. **Technical appendix** — model diagnostics (skill, calibration, experiment, drift).
11. **Methodology box** — 5 plain-English bullets on the measurement design.

## 5. The quant mechanics

- **Sparkline** — inline SVG, single hue, last point dotted; no axes.
- **MoM delta** — arrow + %, colored by whether the *direction is good*, not merely up.
- **Trajectory** — least-squares slope over the window → flat / improving / deteriorating.
- **⚠ Outcome-maturation trimming (the one everyone gets wrong).** If outcomes lag (sales
  take ~40 days to attribute), the latest month(s) read as $0 and poison every delta and
  trajectory. Trim up to 2 trailing months with no matured outcomes **for lagged metrics
  only** (volume metrics stay untrimmed), mark those rows with †, and footnote why.
- **Problem $ estimates** — only from measured unit costs (wasted samples × unit cost, spend
  below breakeven). Label estimates as estimates; never invent figures for unquantified rows.

## 6. The "exact instruction" pattern

The decision engine computes the instruction, not the report. Convention: the last element
of each queue item's `why` list is the imperative line, prefixed `→`, with the specific
numbers in it. The report pulls it out and highlights it; the rest render as plain bullets.

## 7. Voice-of-customer views

- **Themes of the week** — filter comments scraped in the last ~10 days, aggregate theme
  counts, pick the most-liked quote per theme, render as cards.
- **Per campaign** — join comments → videos → campaigns; per campaign show verdict chip +
  comment-mix + 2 most-liked quotes. Read against the verdict (price pushback on a TUNE →
  discount test; buy-intent on a CUT → the problem is economics, not demand).

## 8. Rendering system

Plain HTML string-building with tiny helpers — no template engine: `tile / qtile / chip /
table / bar / section / spark_svg / mom / trajectory`. **Escape every dynamic value.**
Print-first light tokens: ink `#0b0b0b`, data hue blue `#2a78d6`, status chips
(good/warning/serious/critical), `tabular-nums`, `@page Letter`, `page-break-*` on sections
and tiles.

## 9. Gotchas learned the hard way

1. **Outcome lag → false zeros** (§5) — the biggest credibility killer.
2. Chrome PDF: always a **throwaway `--user-data-dir`**; `--headless=new`;
   `--no-pdf-header-footer`; build from a `file://` URI.
3. Section guards are per-source, not one big try — one dead feed costs one section.
4. Every numeric formatter returns "—" on `None`, so a missing value never crashes a row.
5. No-cache the HTML shell so the button always matches the live endpoints.
6. Truncate quotes (~170 chars) and titles; real comments contain emoji/newlines.

## 10. Porting checklist

- [ ] Map each §3 key to the target repo's modules (or `{"note": ...}` it).
- [ ] Port `report.py`: `build_report_data` → section builders → `build_report_html` → `build_report_pdf`.
- [ ] Add the two endpoints + the dashboard button.
- [ ] Wire the `→` instruction-line convention into the decision logic if absent.
- [ ] Identify which metrics are outcome-lagged; apply trimming.
- [ ] Adjust the methodology box to the target's real measurement design — never claim
      causality the system doesn't implement.
- [ ] Render, screenshot, and *look at it*; then print-preview for page-break sanity.

> **Privacy note:** this spec is sanitized by design. This repo implements it against 100%
> synthetic data (`scripts/gen_data.py`) — fabricated handles, competitor names, and figures.
