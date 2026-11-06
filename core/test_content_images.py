import unittest

from bs4 import BeautifulSoup

from core.content_images import hydrate_lazy_images


class HydrateLazyImagesTests(unittest.TestCase):
    def test_uses_data_src_when_src_missing(self):
        content = '<p><img data-src="https://example.com/a.png?x=1&amp;y=2"></p>'
        img = BeautifulSoup(hydrate_lazy_images(content), "html.parser").img
        self.assertEqual(img["src"], "https://example.com/a.png?x=1&y=2")

    def test_replaces_empty_or_data_placeholder_source(self):
        for src in ('src=""', 'src="data:image/gif;base64,R0lGOD"'):
            img = BeautifulSoup(
                hydrate_lazy_images(f'<img {src} data-src="https://example.com/a.jpg">'),
                "html.parser",
            ).img
            self.assertEqual(img["src"], "https://example.com/a.jpg")

    def test_preserves_valid_source(self):
        html = '<img src="https://example.com/old.jpg" data-src="https://example.com/new.jpg">'
        self.assertEqual(hydrate_lazy_images(html), html)

    def test_rejects_non_http_lazy_source(self):
        html = '<img data-src="javascript:alert(1)">'
        self.assertEqual(hydrate_lazy_images(html), html)

    def test_no_lazy_images_leaves_markup_untouched(self):
        html = '<section><p>正文 &amp; 配图</p></section>'
        self.assertEqual(hydrate_lazy_images(html), html)


if __name__ == "__main__":
    unittest.main()
