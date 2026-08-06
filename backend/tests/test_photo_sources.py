"""Sourcing catalogue photographs from Wikimedia Commons.

The licence filter is the part worth testing hardest. Everything else here is a
convenience; that function is the one standing between this project and shipping
somebody's photograph without the right to do so.

Nothing in this file touches the network. `search` is exercised against captured
API shapes, because a test that depends on what Commons returns today is a test
that fails on a Tuesday for reasons nobody can reproduce.
"""

from typing import Any

import pytest

from app.services import photo_sources
from app.services.photo_sources import (
    Candidate,
    _plain_text,
    _to_candidate,
    licence_is_usable,
    search_broadening,
)


class TestLicenceFilter:
    @pytest.mark.parametrize(
        "licence",
        [
            "CC0",
            "CC BY 2.0",
            "CC BY-SA 4.0",
            "cc by-sa 3.0",
            "Public domain",
            "PD-USGov",
            "No restrictions",
        ],
    )
    def test_permissive_licences_are_usable(self, licence: str) -> None:
        assert licence_is_usable(licence)

    @pytest.mark.parametrize(
        "licence",
        [
            "CC BY-NC 4.0",
            "CC BY-ND 4.0",
            "CC BY-NC-SA 3.0",
            "GFDL 1.2",
            "Fair use",
            "All rights reserved",
            "",
        ],
    )
    def test_restrictive_licences_are_refused(self, licence: str) -> None:
        assert not licence_is_usable(licence)

    def test_gfdl_is_refused_even_though_it_is_technically_free(self) -> None:
        """Free, but it requires shipping the whole licence text with the image.

        Excluded rather than half-honoured. Half-honouring a licence is a
        violation that merely looks like compliance.
        """
        assert not licence_is_usable("GFDL 1.2")

    def test_a_gfdl_and_cc_dual_licence_is_usable(self) -> None:
        """The CC terms are the ones taken, so the GFDL text is beside the point."""
        assert licence_is_usable("GFDL 1.2, CC BY-SA 3.0")

    def test_an_unrecognised_licence_is_refused_rather_than_assumed(self) -> None:
        """The conservative direction.

        A false negative costs one candidate. A false positive puts an image in a
        commercial app without permission.
        """
        assert not licence_is_usable("Some Local Museum Licence v2")

    def test_nc_is_matched_on_a_token_not_a_substring(self) -> None:
        """`nc` appears inside plenty of innocent words.

        Without the token split, "No restrictions" survives but a licence reading
        "Public domain, no copyright noticed" would be rejected for containing the
        letters n-c. The forbidden markers must be whole tokens.
        """
        assert licence_is_usable("Public domain, no copyright noticed")
        assert not licence_is_usable("CC BY-NC 4.0")


class TestCandidateParsing:
    def _page(self, **overrides: Any) -> dict:
        info: dict[str, Any] = {
            "mime": "image/jpeg",
            "width": 2000,
            "height": 1500,
            "thumburl": "https://upload.example/thumb.jpg",
            "url": "https://upload.example/full.jpg",
            "descriptionurl": "https://commons.wikimedia.org/wiki/File:Egg.jpg",
            "extmetadata": {
                "LicenseShortName": {"value": "CC BY-SA 4.0"},
                "Artist": {"value": '<a href="/wiki/User:Someone">Someone</a>'},
            },
        }
        info.update(overrides)
        return {"title": "File:Egg.jpg", "imageinfo": [info]}

    def test_a_usable_page_becomes_a_candidate(self) -> None:
        candidate = _to_candidate(self._page())
        assert candidate is not None
        assert candidate.license == "CC BY-SA 4.0"
        assert candidate.artist == "Someone"
        assert candidate.thumb_url == "https://upload.example/thumb.jpg"

    def test_the_credit_line_names_the_photographer_and_the_licence(self) -> None:
        candidate = _to_candidate(self._page())
        assert candidate is not None
        assert candidate.credit == "Someone / Wikimedia Commons (CC BY-SA 4.0)"

    def test_a_small_image_is_rejected(self) -> None:
        """Below 600px the 512px square crop would be an upscale."""
        assert _to_candidate(self._page(width=400, height=300)) is None

    def test_a_non_image_is_rejected(self) -> None:
        assert _to_candidate(self._page(mime="application/pdf")) is None

    def test_a_restrictively_licensed_image_is_rejected(self) -> None:
        page = self._page()
        page["imageinfo"][0]["extmetadata"]["LicenseShortName"]["value"] = "CC BY-NC 2.0"
        assert _to_candidate(page) is None

    def test_the_original_is_used_when_no_thumbnail_was_rendered(self) -> None:
        """Commons omits `thumburl` when the file is already smaller than asked."""
        page = self._page()
        del page["imageinfo"][0]["thumburl"]
        candidate = _to_candidate(page)
        assert candidate is not None
        assert candidate.thumb_url == "https://upload.example/full.jpg"

    def test_a_missing_artist_becomes_unknown_rather_than_empty(self) -> None:
        page = self._page()
        page["imageinfo"][0]["extmetadata"].pop("Artist")
        candidate = _to_candidate(page)
        assert candidate is not None
        assert candidate.artist == "Unknown"

    def test_artist_html_is_reduced_to_a_name(self) -> None:
        assert _plain_text('<a href="/x" class="y">Jane   Doe</a>') == "Jane Doe"
        assert _plain_text("Tom &amp; Jerry") == "Tom & Jerry"


class TestBroadening:
    def test_a_query_that_finds_nothing_is_shortened_from_the_right(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The failure this exists for.

        Commons ANDs every term, so `avocado halved fruit` returns zero results —
        indistinguishable from Commons having no avocados. Dropping words from the
        right keeps the noun and loses the qualifier.
        """
        tried: list[str] = []
        hit = Candidate("File:A.jpg", "u", "d", "CC0", "A", 1000, 1000)

        def fake_search(query: str, limit: int = 10, timeout: float = 30.0) -> list[Candidate]:
            tried.append(query)
            return [hit] if query == "avocado" else []

        monkeypatch.setattr(photo_sources, "search", fake_search)

        assert search_broadening("avocado halved fruit") == [hit]
        assert tried == ["avocado halved fruit", "avocado halved", "avocado"]

    def test_a_query_that_works_is_not_broadened(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        hit = Candidate("File:A.jpg", "u", "d", "CC0", "A", 1000, 1000)
        tried: list[str] = []

        def fake_search(query: str, limit: int = 10, timeout: float = 30.0) -> list[Candidate]:
            tried.append(query)
            return [hit]

        monkeypatch.setattr(photo_sources, "search", fake_search)

        assert search_broadening("boiled egg") == [hit]
        assert tried == ["boiled egg"]

    def test_nothing_at_any_width_returns_empty_rather_than_raising(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            photo_sources, "search", lambda *a, **k: []  # noqa: ARG005
        )
        assert search_broadening("nonsense zzqx") == []
