"""Generate synthetic, public-safe creator + comment data for the RAG demo.
Shaped so queries like 'which creators mention dry hair?' and 'comments with buy-intent'
return real results. 100% fake — safe to publish."""
import csv, random, os
from faker import Faker

fake = Faker(); Faker.seed(7); random.seed(7)
os.makedirs("data", exist_ok=True)

CATS = ["hair care", "beauty", "lifestyle", "fitness"]
HAIR = ["dry damaged hair", "frizzy hair", "curly routine", "heat damage",
        "split ends", "thinning hair", "detangling thick hair"]
INTENT = ["where can i buy this", "drop the link please", "just ordered mine",
          "need this asap", "adding to cart now", "how much is it", "restock when??"]
NEUTRAL = ["love this", "so pretty", "great video", "obsessed", "tutorial please",
           "what's the song", "you're glowing"]
PRICE = ["kinda pricey ngl", "$40 is steep", "wish it was cheaper", "worth the price??",
         "too expensive for me rn"]
COMPETITORS = ["WaveLux", "SleekPro", "CurlCraft"]           # synthetic competitor brands (100% fake)
COMPARE = ["is this better than my {c}?", "how's it vs the {c}?", "i have the {c}, should i switch?",
           "{c} does the same for way less", "my {c} left me frizzy, does this?"]
PRAISE = ["my curls last all day now", "detangled my thick hair so fast", "no more heat damage",
          "so shiny after one use", "cut my routine in half"]
BOUGHT = ["just got mine!", "received it today obsessed", "been using it a week love it"]

creators = []
for i in range(200):
    creators.append({
        "creator_id": f"cr{i:04d}",
        "handle": "@" + fake.user_name(),
        "category": random.choice(CATS),
        "followers": random.randint(1000, 500000),
        "bio": fake.sentence(),
    })

# comments carry a CATEGORY (purchase / confirmed_purchase / price / comparison / praise) so Voice-of-
# Customer + theme-lift have real signal; some praise still names a hair concern for the RAG queries.
comments = []
for i in range(3000):
    cr = random.choice(creators)
    r = random.random()
    if r < 0.20:
        text, cat = random.choice(INTENT), "purchase"
    elif r < 0.28:
        text, cat = random.choice(BOUGHT), "confirmed_purchase"
    elif r < 0.36:
        text, cat = random.choice(PRICE), "price"
    elif r < 0.45:
        text, cat = random.choice(COMPARE).format(c=random.choice(COMPETITORS)), "comparison"
    elif r < 0.68:
        text = (random.choice(HAIR) + " — " + random.choice(PRAISE)) if random.random() < 0.5 \
            else random.choice(PRAISE)
        cat = "praise"
    else:
        text, cat = random.choice(NEUTRAL), "praise"
    comments.append({
        "comment_id": f"cm{i:05d}",
        "creator_id": cr["creator_id"],
        "handle": cr["handle"],
        "video_id": f"v{random.randint(1, 600):04d}",
        "comment_text": text,
        "category": cat,
        "like_count": random.randint(0, 500),
    })

# ── v2: the sampling-engine contract tables ─────────────────────────────────────────────
# Synthetic twin of a production creator-sampling engine: per-creator scoring insights
# (the RAG corpus), an affiliate roster, seeding decisions, and matched controls that the
# recommendation guardrails must protect.
import json

PRODUCTS = ["Detangler Pro Brush", "IonGlow Dryer", "SilkWave Curler", "HeatShield Spray"]

# per-creator buy-intent share from the comments actually generated above — the insight
# text stays consistent with the corpus, so grounded answers cross-check
from collections import defaultdict
c_total, c_intent = defaultdict(int), defaultdict(int)
for cm in comments:
    c_total[cm["creator_id"]] += 1
    if any(p in cm["comment_text"] for p in INTENT):
        c_intent[cm["creator_id"]] += 1

quality = {c["creator_id"]: random.random() * (0.5 + 0.5 * (c["category"] == "hair care"))
           for c in creators}
by_rank = sorted(creators, key=lambda c: -quality[c["creator_id"]])

insights, roster, decisions, controls = [], [], [], []
for pos, c in enumerate(by_rank, start=1):
    cid = c["creator_id"]
    share = c_intent[cid] / c_total[cid] if c_total[cid] else 0.0
    trust = round(random.uniform(0.55, 1.0), 3)
    refund_pct = round(random.uniform(0.5, 6.0), 1)
    videos_n = random.randint(1, 9)
    j = {"handle": c["handle"], "niche": c["category"], "followerCount": c["followers"],
         "engagementRate": round(random.uniform(0.5, 9.0), 2), "trustAdjScore": trust,
         "coldStart": videos_n <= 2,
         "signals": [f"buy-intent share {share:.0%} of recent comments",
                     f"converts reach to sales better than {random.randint(5, 99)}% of ranked creators"],
         "reasons": [f"{c['category']} content matches the line",
                     f"{videos_n} tracked videos, engagement holding"],
         "watchouts": ([f"refund rate {refund_pct}% worse than peers"] if refund_pct > 3 else [])
                      + ([f"only {videos_n} tracked videos — thin evidence"] if videos_n <= 2 else []),
         "videoTotals": {"videos": videos_n, "views": random.randint(2_000, 400_000)}}
    for prod in random.sample(PRODUCTS, k=random.randint(1, 2)):
        insights.append({"score_date": "2026-07-20", "creator_id": cid,
                         "model_version": "ordinal-rank-v1", "rank_position": pos,
                         "suggested_product": prod, "insight_json": json.dumps(j)})
    roster.append({"creator_id": cid, "handle": c["handle"], "as_of_date": "2026-07-20",
                   "tier": f"L{min(4, c['followers'] // 100_000)}",
                   "total_gmv_30d": round(quality[cid] * random.uniform(0, 8_000), 2),
                   "sample_status": random.choice(["", "", "", "Delivered", "Canceled", "To Review"])})

seeded_ids = [c["creator_id"] for c in by_rank[5:35]]
for cid in seeded_ids:
    decisions.append({"cycle_id": "cycle:2026-07-15", "decided_utc": "2026-07-15 19:00:00",
                      "creator_id": cid, "alpha": round(random.uniform(0.2, 3), 3),
                      "beta": round(random.uniform(0.2, 3), 3),
                      "draw": round(random.random(), 3), "seeded": True, "batch_size": 30})
control_ids = [c["creator_id"] for c in by_rank[35:50]]
for s, ctl in zip(seeded_ids, control_ids):
    controls.append({"cycle_id": "cycle:2026-07-15", "seeded_creator_id": s,
                     "control_creator_id": ctl, "score_band": "p80-100",
                     "category": "hair care", "follower_band": "3"})

# ── v3: synthetic sampling OUTCOMES + order timeline ────────────────────────────────────────
# Past sampling history with a causal-style incremental-GMV label per sample, shaped like the real
# thing: POWER-LAW (a few big winners carry the portfolio), RANK-CORRELATED (better rank -> more
# lift, so the scorer shows negative Spearman skill), and REFUND-ADJUSTED. Plus a per-creator order
# timeline so LTV + retention cohorts have data. 100% synthetic.
rank_of = {c["creator_id"]: pos for pos, c in enumerate(by_rank, start=1)}
outcomes, orders = [], []
for c in by_rank:                                   # every creator has a past-sample outcome
    cid = c["creator_id"]
    rf = 1 - (rank_of[cid] - 1) / len(by_rank)       # rank fraction, 1.0 = best-ranked
    win = random.random() < (0.04 + 0.52 * rf)       # steep in rank (~4-56%) -> ~30% overall, strong skill
    if win:
        lift = (70 + 360 * rf) * (0.3 + random.expovariate(1.0))   # rank-scaled base x power-law noise
    else:
        lift = -random.uniform(2, 45) * (1.6 - rf)        # small loss, bigger for worse rank
    refund = round(random.uniform(0.03, 0.15), 3) if random.random() < 0.22 else 0.0  # most 0
    lift_refadj = round(lift * (1 - refund), 2) if lift > 0 else round(lift, 2)
    outcomes.append({"creator_id": cid, "handle": c["handle"], "rank_position": rank_of[cid],
                     "did_lift": round(lift, 2), "did_lift_refadj": lift_refadj, "refund_rate": refund})
    # order timeline (relative months, 0 = first order): winners sell; retention decays -> ~64% one-and-done
    if lift > 0:
        month, cont = 0, 1.0
        while month <= 5 and random.random() < cont:
            gmv = max(5.0, random.expovariate(1 / (60 + 220 * rf)))
            orders.append({"creator_id": cid, "handle": c["handle"], "month_idx": month,
                           "net_gmv": round(gmv * (1 - refund), 2)})
            cont = 0.36 if month == 0 else 0.6        # ~36% survive past month 0, then flatter
            month += 1

# ── v4: warehouse-feature twins (campaigns / videos / sample-requests / creator-videos / categories) ──
# Synthetic equivalents of the marts/staging tables the decision-queue, allocator, spark, post-funnel,
# VoC, theme-lift, scorecard, and product-fit features read in production. Internally consistent with
# the creators/products/comments above. 100% fake.
from collections import Counter

PRODUCT_ID = {p: f"172938{i:012d}" for i, p in enumerate(PRODUCTS)}   # synthetic TikTok product ids
LEAF = {"Detangler Pro Brush": "Hair Brushes & Combs", "IonGlow Dryer": "Hair Dryers",
        "SilkWave Curler": "Curlers & Straighteners", "HeatShield Spray": "Hair Care"}
product_categories = [{"product_id": PRODUCT_ID[p], "product_name": p,
                       "top_category": "Beauty & Personal Care", "leaf_category": LEAF[p]}
                      for p in PRODUCTS]

# per-video comment theme shares — competitor-comparison share drives conversion DOWN (mirrors the real
# Bonferroni finding), so theme_lift shows a genuine negative association on synthetic data.
vid_cat = defaultdict(Counter)
for cm in comments:
    vid_cat[cm["video_id"]][cm["category"]] += 1

NCAMP = 14
videos = []
for vn in range(1, 601):                              # v0001..v0600 (comments reference these)
    vid = f"v{vn:04d}"
    cr = random.choice(creators)
    prod = random.choice(PRODUCTS)
    cc = vid_cat.get(vid, Counter()); tot = sum(cc.values()) or 1
    comp_share = cc.get("comparison", 0) / tot
    conv = max(0.002, 0.06 * (1 - 1.2 * comp_share) * random.uniform(0.5, 1.5))
    views = random.randint(2000, 400000)
    n_ord = int(views * conv)                         # NOT `orders` — that's the order-timeline list
    age = random.randint(1, 120)
    sparked = random.random() < 0.6
    camp = f"camp{random.randint(1, NCAMP):02d}" if sparked else ""
    ad_spend = round(random.uniform(50, 3000), 0) if sparked else 0.0
    # sparking in the 8-14 day window pays off best (mirrors the real finding) — bump ROAS there
    roas = random.uniform(1.2, 3.6) + (1.0 if 8 <= age <= 14 else 0.0)
    gmv = round(n_ord * random.uniform(12, 30), 2)
    videos.append({
        "video_id": vid, "creator_id": cr["creator_id"], "username": cr["handle"],
        "title": fake.sentence(nb_words=6), "age_days": age, "campaign_id": camp,
        "canonical_name": prod, "views14": views, "gmv14": gmv,
        "views_per_day": round(views / max(age, 1), 1), "gmv_per_day": round(random.uniform(0, 400), 2),
        "ctr": round(random.uniform(0.004, 0.03), 4),
        "ad_spend": ad_spend, "ad_gross_revenue": round(ad_spend * roas, 2),
        "organic_gmv": gmv, "organic_views": views, "organic_sku_orders": n_ord,
    })

# campaigns — a demo-worthy verdict spread (the port derives SCALE/TUNE/CUT/RETARGET/GATE from these).
# (name, product, target_roas, actual_roas, breakeven_roas|None=launch, daily_budget)
CAMP_SPECS = [
    ("AM - Detangler 3X",  "Detangler Pro Brush", 3.5, 3.9, 2.10, 3000),  # SCALE
    ("AM - Detangler OG",  "Detangler Pro Brush", 4.0, 2.9, 2.10, 2000),  # TUNE
    ("AM - IonGlow Flex",  "IonGlow Dryer",       3.2, 1.9, 2.70, 5000),  # CUT
    ("AM - IonGlow Promo", "IonGlow Dryer",       2.0, 1.8, 2.74, 1500),  # RETARGET (target<be)
    ("AM - SilkWave",      "SilkWave Curler",     2.3, 0.9, 4.48, 2000),  # RETARGET
    ("AM - SilkWave Halo", "SilkWave Curler",     3.0, 3.1, 2.56, 2500),  # SCALE
    ("AM - HeatShield",    "HeatShield Spray",    2.5, 2.2, 2.09, 1200),  # TUNE
    ("AM - Spring Promo",  "Detangler Pro Brush", 3.0, 1.8, 8.50, 1500),  # GATE (be>8 not retargetable)
    ("AM - Neon Launch",   "IonGlow Dryer",       2.5, 1.1, None, 1000),  # GATE (launch)
    ("AM - Chrome",        "Detangler Pro Brush", 2.9, 3.3, 2.87, 3000),  # SCALE
    ("AM - MegaCurl",      "SilkWave Curler",     2.5, 0.8, None,  800),  # GATE
    ("AM - Smooth 3X",     "HeatShield Spray",    2.1, 1.9, 2.09, 1000),  # CUT
    ("AM - Sparkle",       "Detangler Pro Brush", 3.0, 2.7, 3.03,  900),  # CUT
    ("AM - Holiday Duo",   "IonGlow Dryer",       2.5, 2.6, 1.94, 2000),  # SCALE
]
campaigns = []
for i, (name, prod, tgt, roas, be, bud) in enumerate(CAMP_SPECS, 1):
    spend = round(random.uniform(3, 8) * bud, 0)
    nvid = sum(1 for v in videos if v["campaign_id"] == f"camp{i:02d}")
    campaigns.append({
        "campaign_id": f"camp{i:02d}", "campaign_name": name, "status": "ENABLE", "product": prod,
        "budget_amount": bud, "budget_mode": "BUDGET_MODE_DAY", "target_roas": tgt,
        "spend_30d": spend, "rev_30d": round(spend * roas, 0), "roas": round(roas, 2),
        "videos": max(nvid, random.randint(40, 300)),
        "breakeven_roas": (be if be is not None else ""),
        "contribution_rate": (round(1 / be, 3) if be else ""),
    })

# sample-requests — mirror the real ship->post funnel (~94% Completed, ~5% no-content)
SR_STATUS = (["Completed"] * 90 + ["Content Unfulfilled"] * 4 + ["Content Pending"] * 2
             + ["Shipped"] * 2 + ["Ready to Ship"] * 1)
sample_requests = []
for c in by_rank[3:120]:                              # ~117 sampled creators
    for _ in range(random.randint(1, 5)):             # multiple ships -> post_rate has >=3
        prod = random.choice(PRODUCTS)
        sample_requests.append({
            "sample_id": f"sr{len(sample_requests):05d}", "creator_handle": c["handle"],
            "product_id": PRODUCT_ID[prod], "status": random.choice(SR_STATUS),
            "shipped_time": f"2026-{random.randint(2, 7):02d}-{random.randint(1, 28):02d} 10:00:00",
            "l_tier": f"L{random.randint(1, 4)}",
            "creator_last_30d_gmv": round(random.uniform(0, 8000), 2)})

# creator-videos — products each creator POSTS (drives post->sale + leaf product-fit)
creator_videos = []
for c in creators:
    for _ in range(random.randint(0, 4)):
        prod = random.choice(PRODUCTS)
        creator_videos.append({
            "creator_handle": c["handle"], "product_id": PRODUCT_ID[prod], "product_name": prod,
            "revenue": (round(random.uniform(0, 2000), 2) if random.random() < 0.5 else 0.0),
            "posted_date": f"2026-{random.randint(1, 7):02d}-{random.randint(1, 28):02d}"})

for name, rows in [("creators", creators), ("comments", comments),
                   ("creator_insights", insights), ("roster", roster),
                   ("seeding_decisions", decisions), ("seeding_controls", controls),
                   ("outcomes", outcomes), ("orders", orders),
                   ("campaigns", campaigns), ("videos", videos),
                   ("sample_requests", sample_requests), ("creator_videos", creator_videos),
                   ("product_categories", product_categories)]:
    with open(f"data/{name}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)

print(f"wrote creators({len(creators)}) comments({len(comments)}) insights({len(insights)}) "
      f"roster({len(roster)}) decisions({len(decisions)}) controls({len(controls)}) "
      f"outcomes({len(outcomes)}) orders({len(orders)}) | campaigns({len(campaigns)}) "
      f"videos({len(videos)}) sample_requests({len(sample_requests)}) "
      f"creator_videos({len(creator_videos)}) product_categories({len(product_categories)})")
