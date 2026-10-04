from providers import FlipkartProvider, Product
from ranking import deal_verdict, find_alternatives, similarity
from store import Store


def p(title, price, rating=4.0, url=None):
    return Product(title, price, url or f"https://x/{title}", "demo", None, rating)


def test_cheaper_only_and_ranked():
    base = p("boAt Airdopes 141 Earbuds", 1000)
    cands = [base, p("boAt Airdopes 131 Earbuds", 800), p("Sony Earbuds", 5000), p("Random Earbuds", 400, rating=2.0)]
    alts = find_alternatives(base, cands)
    assert [a.title for a, _ in alts] == ["boAt Airdopes 131 Earbuds"]  # pricier and low-rated dropped


def test_similarity_orders_sensibly():
    assert similarity("boat airdopes 141", "boAt Airdopes 141 Earbuds") > similarity("boat airdopes 141", "Samsung TV")


def test_verdict_uses_history(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    wid = store.add_watch(p("Thing", 1000))
    store.record_price(wid, 800)
    msg = deal_verdict(800, None, store.stats(wid))
    assert "lowest" in msg and "dropped" in msg


def test_flipkart_parser():
    html = ('<div data-id="A"><a href="/thing/p/itm1?pid=1"><img alt="Cool Earbuds" src="i.jpg"></a>'
            '₹999 ₹3,999 75% off 4.1</div>')
    items = FlipkartProvider.parse(html)
    assert items[0].price == 999 and items[0].mrp == 3999 and items[0].rating == 4.1
