"""Normalize lazy-loaded article images for ordinary HTML and RSS readers."""

from bs4 import BeautifulSoup


def hydrate_lazy_images(html: str) -> str:
    """Set img.src from HTTP(S) data-src when no usable src is present."""
    if not html or "data-src" not in html:
        return html

    soup = BeautifulSoup(html, "html.parser")
    changed = False
    for image in soup.find_all("img"):
        source = (image.get("src") or "").strip()
        lazy_source = (image.get("data-src") or "").strip()
        if not lazy_source.startswith(("https://", "http://")):
            continue
        if not source or source.startswith("data:image/"):
            image["src"] = lazy_source
            changed = True
    return str(soup) if changed else html
