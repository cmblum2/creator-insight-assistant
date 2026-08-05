"""Generate synthetic, public-safe creator + comment data for the RAG demo.
Shaped so queries like 'which creators mention dry hair?' and 'comments with buy-intent'
return real results. 100% fake — safe to publish.

Multi-shop: generates THREE independent synthetic shops (aurora / lumen / verde), each in
its own data/shops/<slug>/ directory, plus a data/shops/index.json registry. Every shop
preserves the same careful structure (verdict spread, rank-correlated power-law outcomes,
8-14 day spark bump, comment category/like/scraped_at mix, ship->post funnel, leaf/product-fit
bridge, immature trailing months) — only the brand/niche/product surface words change per cfg.
"""
import csv, random, os, json
from datetime import date, timedelta
from collections import defaultdict, Counter
from faker import Faker

fake = Faker()

TODAY = date(2026, 7, 30)   # fixed "as of" so the weekly report is reproducible

# ── shared, brand-neutral word lists (name no competitor or product) ─────────────────────────
INTENT = ["where can i buy this", "drop the link please", "just ordered mine",
          "need this asap", "adding to cart now", "how much is it", "restock when??"]
NEUTRAL = ["love this", "so pretty", "great video", "obsessed", "tutorial please",
           "what's the song", "you're glowing"]
PRICE = ["kinda pricey ngl", "$40 is steep", "wish it was cheaper", "worth the price??",
         "too expensive for me rn"]
COMPARE = ["is this better than my {c}?", "how's it vs the {c}?", "i have the {c}, should i switch?",
           "{c} does the same for way less", "my {c} left me disappointed, does this?"]
BOUGHT = ["just got mine!", "received it today obsessed", "been using it a week love it"]

# campaign spec template: (product_index, name_tag, target_roas, actual_roas, breakeven|None=launch,
# daily_budget). Preserves the SCALE/TUNE/CUT/RETARGET/GATE verdict SHAPE; product & name come from cfg.
CAMP_TEMPLATE = [
    (0, "3X",      3.5, 3.9, 2.10, 3000),  # SCALE
    (0, "OG",      4.0, 2.9, 2.10, 2000),  # TUNE
    (1, "Flex",    3.2, 1.9, 2.70, 5000),  # CUT
    (1, "Promo",   2.0, 1.8, 2.74, 1500),  # RETARGET (target<be)
    (2, "",        2.3, 0.9, 4.48, 2000),  # RETARGET
    (2, "Halo",    3.0, 3.1, 2.56, 2500),  # SCALE
    (3, "",        2.5, 2.2, 2.09, 1200),  # TUNE
    (0, "Spring",  3.0, 1.8, 8.50, 1500),  # GATE (be>8 not retargetable)
    (1, "Launch",  2.5, 1.1, None, 1000),  # GATE (launch)
    (0, "Chrome",  2.9, 3.3, 2.87, 3000),  # SCALE
    (2, "Mega",    2.5, 0.8, None,  800),  # GATE
    (3, "Smooth",  2.1, 1.9, 2.09, 1000),  # CUT
    (0, "Sparkle", 3.0, 2.7, 3.03,  900),  # CUT
    (1, "Duo",     2.5, 2.6, 1.94, 2000),  # SCALE
]

# base monthly cohort series (last 2 months immature -> blank for lagged metrics); scaled per shop.
TREND_BASE = [
    ("2026-01", 38, 4200, 1260, 0.24),
    ("2026-02", 41, 5100, 1580, 0.27),
    ("2026-03", 44, 6350, 2010, 0.29),
    ("2026-04", 47, 7200, 2360, 0.31),
    ("2026-05", 52, 8600, 2890, 0.33),
    ("2026-06", 49, None, None, None),   # immature (gmv/profit/win lag ~40d)
    ("2026-07", 55, None, None, None),   # immature
]


def write_csv(path, rows):
    """CSV writer helper — one table to one file."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)


def generate_shop(slug, cfg, seed):
    """Generate one synthetic shop's full table set under data/shops/<slug>/. Reproducible per seed."""
    Faker.seed(seed)
    random.seed(seed)
    outdir = os.path.join("data", "shops", slug)
    os.makedirs(outdir, exist_ok=True)

    brand      = cfg["brand"]
    niche      = cfg["niche"]                        # also the primary creator category
    COMPETITORS = cfg["competitors"]                 # 3 fake competitor brands
    PRODUCTS   = cfg["products"]                      # 4 product names
    LEAF       = cfg["leaf"]                          # product -> leaf category
    TOP_CAT    = cfg["top_category"]
    CONCERNS   = cfg["concerns"]                      # niche pain-points (the RAG query surface)
    PRAISE     = cfg["praise"]                        # niche-outcome praise
    n_creators = cfg["n_creators"]
    camp_prefix = cfg["camp_prefix"]
    budget_scale = cfg["budget_scale"]
    trend_scale  = cfg["trend_scale"]
    sample_scale = cfg["sample_scale"]
    win_offset   = cfg["win_offset"]

    n_comments = n_creators * 15
    n_videos   = n_creators * 3
    CATS = [niche, "beauty", "lifestyle", "fitness"]

    # ── creators ─────────────────────────────────────────────────────────────────────────────
    creators = []
    for i in range(n_creators):
        creators.append({
            "creator_id": f"cr{i:04d}",
            "handle": "@" + fake.user_name(),
            "category": random.choice(CATS),
            "followers": random.randint(1000, 500000),
            "bio": fake.sentence(),
        })

    # ── comments — carry a CATEGORY (purchase/confirmed_purchase/price/comparison/praise) so
    # VoC + theme-lift have real signal; some praise still names a niche concern for RAG queries.
    comments = []
    for i in range(n_comments):
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
            text = (random.choice(CONCERNS) + " — " + random.choice(PRAISE)) if random.random() < 0.5 \
                else random.choice(PRAISE)
            cat = "praise"
        else:
            text, cat = random.choice(NEUTRAL), "praise"
        comments.append({
            "comment_id": f"cm{i:05d}",
            "creator_id": cr["creator_id"],
            "handle": cr["handle"],
            "video_id": f"v{random.randint(1, n_videos):04d}",
            "comment_text": text,
            "category": cat,
            "like_count": random.randint(0, 500),
            # scrape date, weighted recent (triangular, mode ~3d ago) so "themes of last N days" filters.
            "scraped_at": (TODAY - timedelta(days=int(random.triangular(0, 27, 3)))).isoformat(),
        })

    # ── v2: sampling-engine contract tables (insights = RAG corpus, roster, decisions, controls) ──
    c_total, c_intent = defaultdict(int), defaultdict(int)
    for cm in comments:
        c_total[cm["creator_id"]] += 1
        if any(p in cm["comment_text"] for p in INTENT):
            c_intent[cm["creator_id"]] += 1

    quality = {c["creator_id"]: random.random() * (0.5 + 0.5 * (c["category"] == niche))
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
                         "category": niche, "follower_band": "3"})

    # ── v3: sampling OUTCOMES + order timeline (power-law, rank-correlated, refund-adjusted) ──
    rank_of = {c["creator_id"]: pos for pos, c in enumerate(by_rank, start=1)}
    outcomes, orders = [], []
    for c in by_rank:
        cid = c["creator_id"]
        rf = 1 - (rank_of[cid] - 1) / len(by_rank)       # rank fraction, 1.0 = best-ranked
        win = random.random() < (0.04 + 0.52 * rf)       # steep in rank -> ~30% overall, strong skill
        if win:
            lift = (70 + 360 * rf) * (0.3 + random.expovariate(1.0))   # rank-scaled base x power-law noise
        else:
            lift = -random.uniform(2, 45) * (1.6 - rf)   # small loss, bigger for worse rank
        refund = round(random.uniform(0.03, 0.15), 3) if random.random() < 0.22 else 0.0
        lift_refadj = round(lift * (1 - refund), 2) if lift > 0 else round(lift, 2)
        outcomes.append({"creator_id": cid, "handle": c["handle"], "rank_position": rank_of[cid],
                         "did_lift": round(lift, 2), "did_lift_refadj": lift_refadj, "refund_rate": refund})
        # order timeline: winners sell; retention decays -> ~64% one-and-done
        if lift > 0:
            month, cont = 0, 1.0
            while month <= 5 and random.random() < cont:
                gmv = max(5.0, random.expovariate(1 / (60 + 220 * rf)))
                orders.append({"creator_id": cid, "handle": c["handle"], "month_idx": month,
                               "net_gmv": round(gmv * (1 - refund), 2)})
                cont = 0.36 if month == 0 else 0.6
                month += 1

    # ── v4: warehouse-feature twins (categories / videos / campaigns / sample-requests / creator-videos) ──
    PRODUCT_ID = {p: f"172938{i:012d}" for i, p in enumerate(PRODUCTS)}   # synthetic TikTok product ids
    product_categories = [{"product_id": PRODUCT_ID[p], "product_name": p,
                           "top_category": TOP_CAT, "leaf_category": LEAF[p]}
                          for p in PRODUCTS]

    vid_cat = defaultdict(Counter)
    for cm in comments:
        vid_cat[cm["video_id"]][cm["category"]] += 1

    NCAMP = len(CAMP_TEMPLATE)
    videos = []
    for vn in range(1, n_videos + 1):                    # comments reference these ids
        vid = f"v{vn:04d}"
        cr = random.choice(creators)
        prod = random.choice(PRODUCTS)
        cc = vid_cat.get(vid, Counter()); tot = sum(cc.values()) or 1
        comp_share = cc.get("comparison", 0) / tot       # more comparison chatter -> lower conversion
        conv = max(0.002, 0.06 * (1 - 1.2 * comp_share) * random.uniform(0.5, 1.5))
        views = random.randint(2000, 400000)
        n_ord = int(views * conv)                        # NOT `orders` — that's the order-timeline list
        age = random.randint(1, 120)
        sparked = random.random() < 0.6
        camp = f"camp{random.randint(1, NCAMP):02d}" if sparked else ""
        ad_spend = round(random.uniform(50, 3000), 0) if sparked else 0.0
        roas = random.uniform(1.2, 3.6) + (1.0 if 8 <= age <= 14 else 0.0)   # 8-14d spark bump
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

    # campaigns — demo-worthy verdict spread; product/name from cfg, budgets scaled per shop.
    campaigns = []
    for i, (pidx, tag, tgt, roas, be, bud) in enumerate(CAMP_TEMPLATE, 1):
        prod = PRODUCTS[pidx]
        name = f"{camp_prefix} - {prod.split()[0]} {tag}".rstrip()
        bud = int(round(bud * budget_scale))
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

    # sample-requests — ship->post funnel (~94% Completed, ~5% no-content)
    SR_STATUS = (["Completed"] * 90 + ["Content Unfulfilled"] * 4 + ["Content Pending"] * 2
                 + ["Shipped"] * 2 + ["Ready to Ship"] * 1)
    sample_requests = []
    for c in by_rank[3:120]:
        for _ in range(random.randint(1, 5)):            # multiple ships -> post_rate has >=3
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

    # ── v5: monthly trend series (immature trailing 2 months blank for lagged metrics), scaled ──
    monthly_trends = []
    for month, samples, gmv, profit, win in TREND_BASE:
        row = {"month": month, "samples": int(round(samples * sample_scale))}
        if gmv is None:
            row.update({"gmv": "", "profit": "", "win_rate": ""})
        else:
            row.update({"gmv": int(round(gmv * trend_scale)),
                        "profit": int(round(profit * trend_scale)),
                        "win_rate": round(min(0.95, max(0.05, win + win_offset)), 2)})
        monthly_trends.append(row)

    tables = [("creators", creators), ("comments", comments),
              ("creator_insights", insights), ("roster", roster),
              ("seeding_decisions", decisions), ("seeding_controls", controls),
              ("outcomes", outcomes), ("orders", orders),
              ("campaigns", campaigns), ("videos", videos),
              ("sample_requests", sample_requests), ("creator_videos", creator_videos),
              ("product_categories", product_categories), ("monthly_trends", monthly_trends)]
    counts = {}
    for name, rows in tables:
        write_csv(os.path.join(outdir, f"{name}.csv"), rows)
        counts[name] = len(rows)

    print(f"[{slug}] {brand} ({niche}): creators({counts['creators']}) comments({counts['comments']}) "
          f"insights({counts['creator_insights']}) outcomes({counts['outcomes']}) "
          f"orders({counts['orders']}) campaigns({counts['campaigns']}) videos({counts['videos']}) "
          f"sample_requests({counts['sample_requests']}) creator_videos({counts['creator_videos']}) "
          f"monthly_trends({counts['monthly_trends']})")
    return counts


# ── shop registry (aurora first = default) ──────────────────────────────────────────────────
SHOPS = [
    ("aurora", {
        "brand": "Aurora Hair Co", "niche": "hair care", "camp_prefix": "AH",
        "competitors": ["WaveLux", "SleekPro", "CurlCraft"],
        "products": ["Detangler Pro Brush", "IonGlow Dryer", "SilkWave Curler", "HeatShield Spray"],
        "leaf": {"Detangler Pro Brush": "Hair Brushes & Combs", "IonGlow Dryer": "Hair Dryers",
                 "SilkWave Curler": "Curlers & Straighteners", "HeatShield Spray": "Hair Care"},
        "top_category": "Beauty & Personal Care",
        "concerns": ["dry damaged hair", "frizzy hair", "curly routine", "heat damage",
                     "split ends", "thinning hair", "detangling thick hair"],
        "praise": ["my curls last all day now", "detangled my thick hair so fast", "no more heat damage",
                   "so shiny after one use", "cut my routine in half"],
        "n_creators": 200, "budget_scale": 1.0, "trend_scale": 1.0, "sample_scale": 1.0, "win_offset": 0.0,
    }, 7),
    ("lumen", {
        "brand": "Lumen Beauty", "niche": "makeup", "camp_prefix": "LB",
        "competitors": ["GlowPop", "VelvetLab", "Prisma"],
        "products": ["LuminEye Palette", "SilkLip Tint", "DewSet Spray", "ContourPro Stick"],
        "leaf": {"LuminEye Palette": "Eyeshadow Palettes", "SilkLip Tint": "Lip Tints",
                 "DewSet Spray": "Setting Sprays", "ContourPro Stick": "Contour & Bronzer"},
        "top_category": "Makeup",
        "concerns": ["oily lids", "crease-proof wear", "shade match", "cakey foundation",
                     "patchy blush", "fallout under eyes", "long wear"],
        "praise": ["no crease all day", "the shade matched perfectly", "blends like a dream",
                   "stayed put through my shift", "zero fallout finally"],
        "n_creators": 150, "budget_scale": 0.6, "trend_scale": 0.65, "sample_scale": 0.75, "win_offset": -0.05,
    }, 21),
    ("verde", {
        "brand": "Verde Skincare", "niche": "skincare", "camp_prefix": "VS",
        "competitors": ["PureRoot", "HydraCove", "CalmLeaf"],
        "products": ["BarrierBalm Cream", "GlassGlow Serum", "CalmDew Toner", "SunVeil SPF"],
        "leaf": {"BarrierBalm Cream": "Moisturizers", "GlassGlow Serum": "Face Serums",
                 "CalmDew Toner": "Toners", "SunVeil SPF": "Sunscreens"},
        "top_category": "Skincare",
        "concerns": ["dry patches", "barrier repair", "texture", "clogged pores",
                     "dull skin", "tight after cleansing", "fine lines"],
        "praise": ["my barrier finally healed", "dry patches gone in days", "skin looks glassy now",
                   "texture smoothed out", "no more tightness"],
        "n_creators": 240, "budget_scale": 1.4, "trend_scale": 1.5, "sample_scale": 1.3, "win_offset": 0.04,
    }, 34),
]


def main():
    os.makedirs(os.path.join("data", "shops"), exist_ok=True)
    registry = []
    for slug, cfg, seed in SHOPS:
        generate_shop(slug, cfg, seed)
        registry.append({"slug": slug, "name": cfg["brand"], "niche": cfg["niche"],
                         "competitors": cfg["competitors"], "products": cfg["products"],
                         "n_creators": cfg["n_creators"]})
    with open(os.path.join("data", "shops", "index.json"), "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2)
    print("wrote index.json")


if __name__ == "__main__":
    main()
