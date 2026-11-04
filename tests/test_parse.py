import unittest
from datetime import date

from collector.common import load_config, won
from collector.hotdeals import classify, parse_arca
from collector.main import mark
from collector.nintendo import parse_list, parse_prices
from collector.playstation import clean_name, parse_product, pick_image

CFG = load_config()


class Won(unittest.TestCase):
    def test_forms(self):
        self.assertEqual(won("(16,320원/무료)"), 16320)
        self.assertEqual(won("[닌텐도스토어 공홈] 메트로이드 드레드 / 64,800"), 64800)
        self.assertEqual(won("₩34,350"), 34350)
        self.assertIsNone(won("[험블] 아랑전설 -75% / $4.99"))
        self.assertIsNone(won("가격 없음"))


class Classify(unittest.TestCase):
    def test_console(self):
        self.assertEqual(classify("[크림]PS5 고스트 오브 요테이 59,400원", False, CFG), "game")
        self.assertEqual(classify("[쿠팡] PS5 듀얼센스 무선 컨트롤러 (69,000원)", False, CFG), "device")
        self.assertEqual(classify("[PSStore] 파이널 판타지 7 리버스 9420원", False, CFG), "game")

    def test_ambiguous_switch(self):
        self.assertIsNone(classify("[지마켓] 개별 스위치 멀티탭 6구 (9,900원)", False, CFG))
        self.assertEqual(classify("[하이마트] 스위치 드래곤퀘스트7 5.2만원", True, CFG), "game")
        self.assertEqual(classify("[11번가] 닌텐도 스위치2 본체 (498,000원)", False, CFG), "device")

    def test_short_english_word_boundary(self):
        self.assertIsNone(classify("갤럭시 버즈 코어 SM-R410", False, CFG))

    def test_title_keywords_only_on_game_board(self):
        self.assertEqual(classify("[네이버] 젤다의 전설 시간의 오카리나 /88,000원", True, CFG), "game")
        self.assertIsNone(classify("[네이버] 젤다의 전설 시간의 오카리나 /88,000원", False, CFG))

    def test_not_console(self):
        self.assertIsNone(classify("[스팀] DRAGON BALL FighterZ (12,770원/무료)", True, CFG))


ARCA = '''
<span class="deal-store">하이마트</span>
&nbsp;
<a class="badge" href="/b/hotdeal?category=sw">SW/게임</a>
</span>
<a class="title hybrid-title" href="/b/hotdeal/123?p=1">
<span class="media-icon bi-images"></span>
  닌텐도 스위치2 마리오카트 월드 세트
<span class="info"><span class="comment-count">[3]</span></span></a>
</span></div>
<a class="title hybrid-bottom" href="/b/hotdeal/123?p=1">
<div class="vrow-bottom deal"><span class="deal-price">548,000원
</span>
'''


class Arca(unittest.TestCase):
    def test_row(self):
        (d,) = parse_arca(ARCA, CFG)
        self.assertEqual(d["id"], "아카라이브:123")
        self.assertEqual(d["title"], "[하이마트] 닌텐도 스위치2 마리오카트 월드 세트")
        self.assertEqual(d["price"], 548000)
        self.assertEqual(d["url"], "https://arca.live/b/hotdeal/123")


NS = '''
<div class="product-item-info" id="product-item-info_17987" data-container="product-grid">
<a href="https://store.nintendo.co.kr/70010000102606" class="product photo product-item-photo" tabindex="-1">
<p class="label_platform">Nintendo Switch 2</p>
<img class="product-image-photo"
src="https://store.nintendo.co.kr/media/catalog/product/cache/x/5/c/a.jpg"
loading="lazy"/>
<a class="product-item-link"
   href="https://store.nintendo.co.kr/70010000102606">
    Monster Hunter Wilds                            </a>
<span  id="product-price-17987"                data-price-amount="34350"
data-price-type="finalPrice"
class="price-wrapper "></span>
<span  id="old-price-17987"                data-price-amount="45800"
data-price-type="oldPrice"
class="price-wrapper "></span>
'''

PRICES = {"country": "KR", "prices": [
    {"title_id": 70010000102606, "sales_status": "onsale",
     "regular_price": {"raw_value": "45800"},
     "discount_price": {"raw_value": "34350", "end_datetime": "2027-01-07T14:59:59Z"}},
    {"title_id": 70010000000001, "sales_status": "onsale", "regular_price": {"raw_value": "10000"}},
    {"title_id": 70010000000002, "sales_status": "not_found"},
]}


class Nintendo(unittest.TestCase):
    def test_list_item(self):
        (d,) = parse_list(NS)
        self.assertEqual((d["nsuid"], d["name"], d["price"], d["regular"], d["platform"]),
                         ("70010000102606", "Monster Hunter Wilds", 34350, 45800, "Nintendo Switch 2"))
        self.assertTrue(d["img"].endswith("/a.jpg"))

    def test_prices_only_discounted(self):
        self.assertEqual(parse_prices(PRICES),
                         {"70010000102606": {"price": 34350, "regular": 45800, "ends": "2027-01-07T14:59:59Z"}})


class PlayStation(unittest.TestCase):
    def test_product(self):
        d = parse_product({"id": "X-1", "name": "사이버펑크 2077 (한국어, 영어)", "platforms": ["PS5"],
                           "storeDisplayClassification": "FULL_GAME",
                           "price": {"basePrice": "54,800원", "discountedPrice": "21,920원", "discountText": "-60%"}})
        self.assertEqual((d["name"], d["price"], d["regular"], d["discount"], d["type"]),
                         ("사이버펑크 2077", 21920, 54800, 60, "게임"))
        self.assertIsNone(parse_product({"id": "Y", "name": "a", "price": {"basePrice": "1,000원", "discountedPrice": "1,000원"}}))

    def test_image(self):
        media = [{"role": "SCREENSHOT", "type": "IMAGE", "url": "s"}, {"role": "GAMEHUB_COVER_ART", "type": "IMAGE", "url": "c"}]
        self.assertEqual(pick_image(media), "c?w=160")
        self.assertIsNone(pick_image([]))

    def test_clean_name(self):
        self.assertEqual(clean_name("Outward (중국어(간체자), 한국어, 영어)"), "Outward")
        self.assertEqual(clean_name("Spider-Man 2 (PS5)"), "Spider-Man 2 (PS5)")


class Lowest(unittest.TestCase):
    def test_new_low_and_wish(self):
        hist = {"ns:1": [30000, "2026-09-01", "2026-09-01", "2026-09-01"]}
        items = [{"id": "ns:1", "name": "젤다의 전설 티어스 오브 더 킹덤", "price": 25000},
                 {"id": "ns:2", "name": "Other", "price": 1000}]
        mark(items, hist, date(2026, 11, 4), ["티어스오브더킹덤"])
        self.assertTrue(items[0]["new_low"])
        self.assertEqual(items[0]["prev_low"], 30000)
        self.assertTrue(items[0]["wish"])
        self.assertNotIn("new_low", items[1])
        self.assertEqual(hist["ns:1"][0], 25000)
        self.assertEqual(hist["ns:2"], [1000, "2026-11-04", "2026-11-04", "2026-11-04"])


if __name__ == "__main__":
    unittest.main()
