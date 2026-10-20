"""Score unscored headlines in data/news/articles.jsonl with FinBERT (free, runs on CPU).

score = P(positive) - P(negative), in [-1, 1]; label = most likely class; conf = its probability.
Event type comes from simple keyword rules. The model name is recorded so results can be reproduced.
"""
from __future__ import annotations

import json
import os
import re

ARTICLES = "data/news/articles.jsonl"
MODEL = os.environ.get("FINBERT_MODEL", "ProsusAI/finbert")

EVENTS = [
    ("Earnings", r"\b(results|earnings|profit|revenue|sales|quarter|q[1-4]|half-year|interim|eps)\b"),
    ("Guidance", r"\b(guidance|outlook|forecast|targets?|upgrade[sd]?|downgrade[sd]?)\b"),
    ("M&A", r"\b(acquir\w*|acquisition|merger|takeover|bid|offer for|buyout|deal to buy|stake)\b"),
    ("Legal / regulatory", r"\b(regulator\w*|probe|investigation|lawsuit|fine[sd]?|court|sec|fca|cma|approval|antitrust)\b"),
    ("Management", r"\b(ceo|chief executive|cfo|chair(man|woman)?|resign\w*|appoint\w*|steps? down)\b"),
    ("Capital", r"\b(dividend|buyback|share repurchase|rights issue|placing|bond|debt)\b"),
]


def event_type(text: str) -> str:
    t = text.lower()
    for name, pat in EVENTS:
        if re.search(pat, t):
            return name
    return "Other"


def main() -> None:
    if not os.path.exists(ARTICLES):
        print("no articles yet")
        return
    with open(ARTICLES) as fh:
        rows = [json.loads(l) for l in fh if l.strip()]
    todo = [a for a in rows if a.get("score") is None]
    print(f"{len(todo)} headlines to score with {MODEL}")
    if todo:
        from transformers import pipeline  # imported lazily: heavy

        clf = pipeline("text-classification", model=MODEL, top_k=None, truncation=True)
        for i in range(0, len(todo), 64):
            batch = todo[i : i + 64]
            preds = clf([a["headline"][:512] for a in batch], batch_size=32)
            for a, p in zip(batch, preds):
                probs = {d["label"].lower(): d["score"] for d in p}
                best = max(probs, key=probs.get)
                a["score"] = round(probs.get("positive", 0) - probs.get("negative", 0), 4)
                a["label"] = best.capitalize()
                a["conf"] = round(probs[best], 4)
                a["event"] = event_type(a["headline"])
                a["model"] = MODEL
    with open(ARTICLES, "w") as fh:
        for a in rows:
            fh.write(json.dumps(a, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
