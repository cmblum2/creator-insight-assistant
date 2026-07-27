"""Deterministic guardrail eval: recommendations must NEVER include a matched-control or
already-seeded creator, under any product filter. Runs free (no LLM) — eval the guardrails,
not just the answers."""
import pandas as pd

from app.config import CONTRACT
from app.recommend import recommend


def main():
    controls = set(pd.read_csv(CONTRACT["seeding_controls"])["control_creator_id"])
    seeded = set(pd.read_csv(CONTRACT["seeding_decisions"])
                 .query("seeded == True or seeded == 'True'")["creator_id"])
    for product in ["", "Detangler", "IonGlow", "SilkWave", "HeatShield"]:
        r = recommend(product=product, n=50)
        ids = {c["creator_id"] for c in r["candidates"]}
        leak, reseed = ids & controls, ids & seeded
        assert not leak, f"CONTROL LEAK (filter={product!r}): {leak}"
        assert not reseed, f"RESEED (filter={product!r}): {reseed}"
    print("guardrail eval PASS: no control or seeded creators recommended under any filter")


if __name__ == "__main__":
    main()
