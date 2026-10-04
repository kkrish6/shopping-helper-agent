"""Web UI for the shopping helper agent (Streamlit). Run: streamlit run streamlit_app.py

Reuses the same providers, ranking and store as the CLI. On free hosting the
SQLite watchlist lives on the server's temporary disk, so it can reset when
the app restarts. Locally it behaves like the CLI database.
"""
import os

import streamlit as st

import llm
from providers import PROVIDERS
from ranking import best_match, deal_verdict, find_alternatives
from store import Store

st.set_page_config(page_title="Shopping Helper", page_icon="🛒", layout="centered")
st.title("🛒 Shopping Helper")
st.caption("Find cheaper similar products and track price drops (India).")


@st.cache_resource
def get_store() -> Store:
    path = os.getenv("SHOPPER_DB", "shopper.db")
    s = Store(path)
    s.db = __import__("sqlite3").connect(path, check_same_thread=False)
    s.db.row_factory = __import__("sqlite3").Row
    s.db.execute("PRAGMA foreign_keys = ON")
    return s


store = get_store()


def collect(query, sources):
    out = []
    for name in sources:
        out.extend(PROVIDERS[name]().search(query))
    return out


def card(p, extra=""):
    off = f" · {p.discount_pct:.0f}% off MRP ₹{p.mrp:,.0f}" if p.discount_pct else ""
    rate = f" · ★{p.rating}" if p.rating else ""
    st.markdown(f"**₹{p.price:,.0f}**{off}{rate} · _{p.source}_  {extra}\n\n[{p.title[:90]}]({p.url})")


tab_search, tab_watch = st.tabs(["Search", "Watchlist"])

with tab_search:
    query = st.text_input("What are you looking for?", placeholder="boat airdopes under 1500")
    src = st.multiselect("Sources", ["flipkart", "amazon", "demo"], default=["flipkart"],
                         help="Amazon often blocks cloud servers. 'demo' is offline sample data.")
    if st.button("Search", type="primary", use_container_width=True) and query:
        with st.spinner("Searching politely, this can take a few seconds..."):
            req = llm.parse_request(query)
            results = collect(req["query"], src)
            if req["max_price"]:
                results = [p for p in results if p.price <= req["max_price"]]
        st.session_state["results"] = (req, results)
    if "results" in st.session_state:
        req, results = st.session_state["results"]
        if not results:
            st.warning("No results. The site may be blocking this server. Try 'demo' or a simpler query.")
        else:
            base = best_match(req["query"], results)
            st.subheader("Best match")
            card(base)
            if st.button("👀 Watch this price", key="watch_base"):
                target = st.session_state.get("target_in") or None
                store.add_watch(base, target)
                st.success("Added to watchlist")
            st.number_input("Alert target price (optional, ₹)", min_value=0.0, step=50.0, key="target_in")
            alts = find_alternatives(base, results)
            st.subheader("Cheaper similar options")
            if not alts:
                st.info("No cheaper similar option found.")
            for p, score in alts:
                card(p, f"· saves ₹{base.price - p.price:,.0f}")
            advice = llm.explain(query, {"best_match": base.to_dict(),
                                         "cheaper": [p.to_dict() for p, _ in alts]})
            if advice:
                st.markdown(f"**Advice:** {advice}")

with tab_watch:
    watches = store.watches()
    if st.button("🔄 Check prices now", use_container_width=True) and watches:
        with st.spinner("Checking..."):
            for w in watches:
                found = collect(w["title"], [w["source"]])
                cur = next((p for p in found if p.url == w["url"]), None) or best_match(w["title"], found)
                if cur:
                    store.record_price(w["id"], cur.price, cur.mrp)
        st.success("Done")
    if not watches:
        st.info("Nothing watched yet. Search a product and tap 'Watch this price'.")
    for w in store.watches():
        s = store.stats(w["id"])
        with st.container(border=True):
            st.markdown(f"**{w['title'][:70]}**")
            st.write(f"Now ₹{s['latest']:,.0f} · low ₹{s['lowest']:,.0f} · high ₹{s['highest']:,.0f} · {s['checks']} checks")
            st.caption(deal_verdict(s["latest"], None, s))
            if w["target_price"] and s["latest"] <= w["target_price"]:
                st.success("🎯 Target price hit!")
            if st.button("Remove", key=f"rm{w['id']}"):
                store.remove_watch(w["id"])
                st.rerun()
    st.caption("On free hosting this list may reset when the app restarts.")
