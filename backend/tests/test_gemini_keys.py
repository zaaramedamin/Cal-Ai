"""Which Gemini key each call spends.

This is worth testing because getting it wrong is *invisible*. Both keys work,
both calls succeed, and the only symptom is that photo scanning runs out of
quota earlier than it should — weeks later, blamed on the free tier rather than
on a one-word mistake in a call site.
"""

import os

import pytest

from app.core.config import get_settings
from app.services.vision import VisionClient

PHOTO_KEY = "photo-key-aaa"
TEXT_KEY = "text-key-bbb"


class CapturingClient:
    """Records the key each request was sent with, and answers plausibly."""

    def __init__(self) -> None:
        self.keys: list[str] = []

    async def post(self, url: str, *, json=None, headers=None, **_):  # noqa: ANN001
        self.keys.append(headers.get("x-goog-api-key", "") if headers else "")

        class Response:
            status_code = 200
            # The real client checks this before parsing, so the stub has to
            # carry it — httpx.Response exposes it as a property.
            is_success = True
            text = '{"items": [], "notes": ""}'

            @staticmethod
            def json():
                return {
                    "candidates": [
                        {"content": {"parts": [{"text": '{"items": [], "notes": ""}'}]}}
                    ]
                }

        return Response()

    async def aclose(self) -> None:
        return None


@pytest.fixture
def two_keys():
    previous = {
        "GEMINI_API_KEY": os.environ.get("GEMINI_API_KEY"),
        "GEMINI_TEXT_API_KEY": os.environ.get("GEMINI_TEXT_API_KEY"),
    }
    os.environ["GEMINI_API_KEY"] = PHOTO_KEY
    os.environ["GEMINI_TEXT_API_KEY"] = TEXT_KEY
    get_settings.cache_clear()
    yield
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    get_settings.cache_clear()


async def test_photo_scanning_spends_the_photo_key(two_keys) -> None:
    http = CapturingClient()
    await VisionClient(client=http).analyse_meal("Zm9v", "image/jpeg")

    assert http.keys == [PHOTO_KEY]


async def test_describing_spends_the_text_key(two_keys) -> None:
    """The whole point of the second key: descriptions must not eat the budget
    photo scanning needs, because a description can be typed into search
    instead and a photograph cannot."""
    http = CapturingClient()
    await VisionClient(client=http).describe_meal("two boiled eggs")

    assert http.keys == [TEXT_KEY]


async def test_the_text_key_falls_back_to_the_photo_key(two_keys) -> None:
    """One key must still work. Leaving the second blank is a supported setup,
    not a broken one."""
    os.environ["GEMINI_TEXT_API_KEY"] = ""
    get_settings.cache_clear()

    http = CapturingClient()
    await VisionClient(client=http).describe_meal("two boiled eggs")

    assert http.keys == [PHOTO_KEY]


def test_the_effective_text_key_prefers_the_dedicated_one(two_keys) -> None:
    assert get_settings().gemini_key_for_text == TEXT_KEY
