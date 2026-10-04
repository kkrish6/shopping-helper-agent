"""Shopping helper agent - command line interface.

    python main.py search "boat earbuds under 1500"
    python main.py watch "boat airdopes 141" --target 899
    python main.py check
    python main.py list
"""
from __future__ import annotations

import argparse
import logging
import os

import llm
from providers import PROVIDERS, Product
from ranking import best_match, deal_verdict, find_alternatives
from store import Store


def collect(query: str, sources: list[str]) -> list[Product]:
    results: list[Product] = []
    for name in sources:
        found = PROVIDERS[name]().search(query)
        logging.info("%s: %d results", name, len(found))
        results.extend(found)
    return results


def fmt(p: Product) -> str:
    off = f" ({p.discount_pct:.0f}% off MRP {p.mrp:,.0f})" if p.discount_pct else ""
    rate = f" ★{p.rating}" if p.rating else ""
    return f"₹{p.price:,.0f}{off}{rate} [{p.source}] {p.title[:70]}\n      {p.url}"


def cmd_search(args, store: Store) -> None:
    req = llm.parse_request(args.query)
    results = collect(req["query"], args.sources)
    if req["max_price"]:
        results = [p for p in results if p.price <= req["max_price"]]
    if not results:
        print("No results. Try --sources demo to test offline, or a simpler query.")
        return
    base = best_match(req["query"], results)
    print(f"\nBest match for '{req['query']}':\n  {fmt(base)}\n")
    alts = find_alternatives(base, results)
    if alts:
        print("Cheaper similar options:")
        for p, score in alts:
            print(f"  - saves ₹{base.price - p.price:,.0f}: {fmt(p)}")
    else:
        print("No cheaper similar option found.")
    advice = llm.explain(args.query, {"best_match": base.to_dict(),
                                      "cheaper": [p.to_dict() for p, _ in alts]})
    if advice:
        print(f"\nAdvice: {advice}")


def cmd_watch(args, store: Store) -> None:
    results = collect(args.query, args.sources)
    base = best_match(args.query, results)
    if not base:
        print("Could not find that product.")
        return
    wid = store.add_watch(base, args.target)
    print(f"Watching #{wid}: {fmt(base)}" + (f"\n  alert at or below ₹{args.target:,.0f}" if args.target else ""))


def cmd_check(args, store: Store) -> None:
    watches = store.watches()
    if not watches:
        print("Watchlist is empty. Use: python main.py watch \"<product>\"")
        return
    for w in watches:
        found = collect(w["title"], [w["source"]])
        current = next((p for p in found if p.url == w["url"]), None) or best_match(w["title"], found)
        if not current:
            print(f"#{w['id']} {w['title'][:50]}: could not fetch price right now")
            continue
        store.record_price(w["id"], current.price, current.mrp)
        stats = store.stats(w["id"])
        alert = "  *** TARGET HIT ***" if w["target_price"] and current.price <= w["target_price"] else ""
        print(f"#{w['id']} {w['title'][:50]}: ₹{current.price:,.0f} - "
              f"{deal_verdict(current.price, current.mrp, stats)}{alert}")


def cmd_list(args, store: Store) -> None:
    for w in store.watches():
        s = store.stats(w["id"])
        print(f"#{w['id']} {w['title'][:55]} | now ₹{s['latest']:,.0f} | low ₹{s['lowest']:,.0f} "
              f"| high ₹{s['highest']:,.0f} | {s['checks']} checks")


def cmd_remove(args, store: Store) -> None:
    print("Removed." if store.remove_watch(args.id) else "No such id.")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Shopping helper agent (India)")
    p.add_argument("--db", default=os.getenv("SHOPPER_DB", "shopper.db"))
    p.add_argument("--sources", default="flipkart,amazon",
                   help="comma separated: flipkart,amazon,demo")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search", help="find a product and cheaper alternatives")
    s.add_argument("query")
    s.set_defaults(fn=cmd_search)
    w = sub.add_parser("watch", help="track a product's price")
    w.add_argument("query")
    w.add_argument("--target", type=float, help="alert when price <= this")
    w.set_defaults(fn=cmd_watch)
    sub.add_parser("check", help="re-check all watched prices").set_defaults(fn=cmd_check)
    sub.add_parser("list", help="show watchlist").set_defaults(fn=cmd_list)
    r = sub.add_parser("remove", help="stop watching")
    r.add_argument("id", type=int)
    r.set_defaults(fn=cmd_remove)
    return p


def main() -> None:
    args = build_parser().parse_args()
    args.sources = [x for x in args.sources.split(",") if x in PROVIDERS]
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(message)s")
    args.fn(args, Store(args.db))


if __name__ == "__main__":
    main()
