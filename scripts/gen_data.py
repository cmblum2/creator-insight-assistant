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

for name, rows in [("creators", creators), ("comments", comments)]:
    with open(f"data/{name}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)

print(f"wrote data/creators.csv ({len(creators)}) and data/comments.csv ({len(comments)})")
