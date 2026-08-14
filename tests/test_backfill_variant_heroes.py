import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from backfill_variant_heroes import (  # noqa: E402
    extract_image_url,
    pick_candidates,
    slugify,
)


class SlugifyTests(unittest.TestCase):
    def test_lowercases_and_hyphenates(self):
        self.assertEqual(slugify("Neverfull-style Monogram GM"), "neverfull-style-monogram-gm")

    def test_collapses_runs_of_punctuation(self):
        self.assertEqual(slugify("Speedy Soft 30 (Empreinte)!!"), "speedy-soft-30-empreinte")


class ExtractImageUrlTests(unittest.TestCase):
    def test_gallery_post_uses_first_item_in_gallery_order(self):
        post = {
            "is_gallery": True,
            "gallery_data": {"items": [{"media_id": "b"}, {"media_id": "a"}]},
            "media_metadata": {
                "a": {"s": {"u": "https://preview.redd.it/a.jpg", "x": 100, "y": 200}},
                "b": {"s": {"u": "https://preview.redd.it/b.jpg", "x": 300, "y": 400}},
            },
        }
        url, w, h = extract_image_url(post)
        self.assertEqual(url, "https://preview.redd.it/b.jpg")
        self.assertEqual((w, h), (300, 400))

    def test_gallery_post_falls_back_to_metadata_order_without_gallery_data(self):
        post = {
            "is_gallery": True,
            "media_metadata": {"only": {"s": {"u": "https://i.redd.it/only.jpg", "x": 1, "y": 2}}},
        }
        url, _, _ = extract_image_url(post)
        self.assertEqual(url, "https://i.redd.it/only.jpg")

    def test_direct_image_post_uses_url_field(self):
        post = {
            "post_hint": "image",
            "url": "https://i.redd.it/direct.jpg",
            "preview": {"images": [{"source": {"width": 500, "height": 600}}]},
        }
        url, w, h = extract_image_url(post)
        self.assertEqual(url, "https://i.redd.it/direct.jpg")
        self.assertEqual((w, h), (500, 600))

    def test_self_post_with_preview_uses_preview_source(self):
        post = {
            "preview": {"images": [{"source": {
                "url": "https://preview.redd.it/self-post-preview.jpg&amp;s=abc", "width": 10, "height": 20,
            }}]},
        }
        url, w, h = extract_image_url(post)
        self.assertEqual(url, "https://preview.redd.it/self-post-preview.jpg&s=abc")
        self.assertEqual((w, h), (10, 20))

    def test_self_post_with_inline_media_metadata_uses_upload_source(self):
        post = {
            "media_metadata": {
                "inline": {"s": {"u": "https://preview.redd.it/inline.jpg", "x": 1200, "y": 900}},
            },
        }
        url, w, h = extract_image_url(post)
        self.assertEqual(url, "https://preview.redd.it/inline.jpg")
        self.assertEqual((w, h), (1200, 900))

    def test_external_preview_host_is_rejected(self):
        # A third-party link (e.g. a seller catalog page) reflected through Reddit's
        # proxy, not an upload -- explicitly out of the sourcing contract.
        post = {
            "preview": {"images": [{"source": {
                "url": "https://external-preview.redd.it/not-an-upload.jpg", "width": 10, "height": 20,
            }}]},
        }
        url, w, h = extract_image_url(post)
        self.assertIsNone(url)
        self.assertIsNone(w)
        self.assertIsNone(h)

    def test_self_post_with_no_preview_finds_nothing(self):
        post = {"url": "https://www.reddit.com/r/RepTherapy/comments/abc123/title/"}
        url, w, h = extract_image_url(post)
        self.assertIsNone(url)

    def test_gallery_item_on_a_disallowed_host_is_skipped(self):
        post = {
            "is_gallery": True,
            "media_metadata": {"a": {"s": {"u": "https://some-other-cdn.example/a.jpg"}}},
        }
        url, _, _ = extract_image_url(post)
        self.assertIsNone(url)


class PickCandidatesTests(unittest.TestCase):
    def _bag(self):
        return {"id": "bag-x"}

    def _row(self, eid, lane, bag_ids=("bag-x",), paraphrase="short"):
        return {"id": eid, "evidence_type": lane, "bag_ids": list(bag_ids), "paraphrase": paraphrase}

    def test_in_hand_review_is_preferred_over_psp_qc(self):
        rows = [self._row("e1", "psp_qc"), self._row("e2", "in_hand_review")]
        picked = pick_candidates(self._bag(), rows, limit=4)
        self.assertEqual([r["id"] for r in picked], ["e2", "e1"])

    def test_unlinked_evidence_is_excluded(self):
        rows = [self._row("e1", "in_hand_review", bag_ids=("bag-other",))]
        picked = pick_candidates(self._bag(), rows, limit=4)
        self.assertEqual(picked, [])

    def test_limit_is_respected(self):
        rows = [self._row(f"e{i}", "in_hand_review") for i in range(6)]
        picked = pick_candidates(self._bag(), rows, limit=3)
        self.assertEqual(len(picked), 3)

    def test_longer_paraphrase_breaks_ties_within_the_same_lane(self):
        rows = [
            self._row("short", "in_hand_review", paraphrase="a"),
            self._row("long", "in_hand_review", paraphrase="a much longer paraphrase here"),
        ]
        picked = pick_candidates(self._bag(), rows, limit=4)
        self.assertEqual(picked[0]["id"], "long")


if __name__ == "__main__":
    unittest.main()
