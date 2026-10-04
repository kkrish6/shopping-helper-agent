"""Finding cheaper alternatives and judging whether a deal is real."""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from providers import Product

STOP = {"with", "for", "and", "the", "bluetooth", "wireless", "black", "blue", "white",
        "new", "pack", "of", "in", "ear", "hrs", "hours", "h"}


def tokens(title: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", title.lower()) if t not in STOP and len(t) > 1}


def similarity(a: str, b: str) -> float:
    """0..1 score: token overlap (Jaccard) blended with fuzzy string match."""
    ta, tb = tokens(a), tokens(b)
    jaccard = len(ta & tb) / len(ta | tb) if ta | tb else 0.0
    fuzzy = SequenceMatcher(None, a.lower(), b.lower()).ratio()
    return 0.6 * jaccard + 0.4 * fuzzy


def dedupe(products: list[Product]) -> list[Product]:
    best: dict[str, Product] = {}
    for p in products:
        key = (p.source, p.title.lower(), p.price)   # same listing shown twice
        if key not in best or p.price < best[key].price:
            best[key] = p
    return list(best.values())


def find_alternatives(base: Product, candidates: list[Product], min_rating: float = 3.5,
                      top: int = 5) -> list[tuple[Product, float]]:
    """Cheaper products of the same kind, ranked by value.

    value = similarity * saving, with a penalty for low ratings. Items without a
    rating are kept (many listings hide it) but ranked below rated ones.
    """
    scored = []
    for c in dedupe(candidates):
        if c.url == base.url or c.price >= base.price:
            continue
        if c.rating is not None and c.rating < min_rating:
            continue
        sim = similarity(base.title, c.title)
        saving = (base.price - c.price) / base.price
        score = sim * (0.5 + saving) * (1.0 if c.rating else 0.85)
        scored.append((c, round(score, 3)))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top]


def best_match(query: str, products: list[Product]) -> Product | None:
    return max(products, key=lambda p: similarity(query, p.title), default=None)


def deal_verdict(price: float, mrp: float | None, stats: dict | None) -> str:
    """Plain rules, so the verdict is explainable. Compares with our own history."""
    notes = []
    if stats and stats["checks"] > 1:
        if price <= stats["lowest"]:
            notes.append("lowest price we have seen")
        if stats["previous"] and price < stats["previous"]:
            drop = 100 * (stats["previous"] - price) / stats["previous"]
            notes.append(f"dropped {drop:.0f}% since last check")
        elif stats["previous"] and price > stats["previous"]:
            notes.append("price went up since last check")
        if price > stats["lowest"] * 1.15:
            notes.append(f"{100 * (price - stats['lowest']) / stats['lowest']:.0f}% above its lowest")
    if mrp and mrp > price:
        pct = 100 * (mrp - price) / mrp
        if pct >= 60:
            notes.append(f"{pct:.0f}% off list price (large MRP discounts are often inflated, trust history more)")
        else:
            notes.append(f"{pct:.0f}% off list price")
    if not notes:
        return "no change yet - check again later to build price history"
    return "; ".join(notes)
