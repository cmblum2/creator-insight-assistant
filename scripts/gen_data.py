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

creators = []
for i in range(200):
    creators.append({
        "creator_id": f"cr{i:04d}",
        "handle": "@" + fake.user_name(),
        "category": random.choice(CATS),
        "followers": random.randint(1000, 500000),
        "bio": fake.sentence(),
    })

comments = []
for i in range(3000):
    cr = random.choice(creators)
    r = random.random()
    if r < 0.30:
        text = random.choice(INTENT)
    elif r < 0.60:
        text = random.choice(HAIR) + " — " + random.choice(NEUTRAL)
    else:
        text = random.choice(NEUTRAL)
    comments.append({
        "comment_id": f"cm{i:05d}",
        "creator_id": cr["creator_id"],
        "handle": cr["handle"],
        "video_id": f"v{random.randint(1, 600):04d}",
        "comment_text": text,
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

for name, rows in [("creators", creators), ("comments", comments),
                   ("creator_insights", insights), ("roster", roster),
                   ("seeding_decisions", decisions), ("seeding_controls", controls)]:
    with open(f"data/{name}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)

print(f"wrote creators({len(creators)}) comments({len(comments)}) insights({len(insights)}) "
      f"roster({len(roster)}) decisions({len(decisions)}) controls({len(controls)})")
