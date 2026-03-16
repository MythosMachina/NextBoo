import unittest

from app.core.constants import Rating
from app.services.search import parse_media_type_filter, parse_rating_filter


class BackendSmokeTests(unittest.TestCase):
    def test_rating_filter_aliases(self) -> None:
        self.assertEqual(parse_rating_filter("g"), Rating.GENERAL)
        self.assertEqual(parse_rating_filter("s"), Rating.SENSITIVE)
        self.assertEqual(parse_rating_filter("q"), Rating.QUESTIONABLE)
        self.assertEqual(parse_rating_filter("x"), Rating.EXPLICIT)

    def test_media_type_filter_aliases(self) -> None:
        self.assertEqual(parse_media_type_filter("image"), "image")
        self.assertEqual(parse_media_type_filter("animated"), "animated")
        self.assertEqual(parse_media_type_filter("video"), "video")


if __name__ == "__main__":
    unittest.main()
