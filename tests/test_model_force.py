import os
import unittest
from unittest.mock import AsyncMock, patch

from app.api.models import Model
from app.core.model_manager import (
    MODEL_ALIASES,
    get_force_model,
    resolve_backend_model,
)


def _mock_models():
    return [
        Model(id="gemini-3.7-flash-high", created=1),
        Model(id="claude-sonnet-4-6", created=1),
        Model(id="max-gem", created=1),
    ]


class TestModelForce(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("AGY_FORCE_MODEL", None)

    def test_get_force_model_empty(self):
        os.environ.pop("AGY_FORCE_MODEL", None)
        self.assertIsNone(get_force_model())

    def test_get_force_model_set(self):
        os.environ["AGY_FORCE_MODEL"] = "max-gem"
        self.assertEqual(get_force_model(), "max-gem")

    def test_resolve_without_force_sonnet(self):
        async def _run():
            with patch(
                "app.core.model_manager.get_available_models",
                new=AsyncMock(return_value=_mock_models()),
            ):
                backend = await resolve_backend_model("claude-sonnet-5")
                self.assertEqual(backend, "claude-sonnet-4-6")

        import asyncio
        asyncio.run(_run())

    def test_resolve_with_force_max_gem(self):
        async def _run():
            os.environ["AGY_FORCE_MODEL"] = "max-gem"
            with patch(
                "app.core.model_manager.get_available_models",
                new=AsyncMock(return_value=_mock_models()),
            ):
                for requested in ("claude-sonnet-5", "max-gem", "claude-opus-4"):
                    backend = await resolve_backend_model(requested)
                    self.assertEqual(backend, MODEL_ALIASES["max-gem"])

        import asyncio
        asyncio.run(_run())

    def test_resolve_with_force_direct_backend(self):
        async def _run():
            os.environ["AGY_FORCE_MODEL"] = "gemini-3.7-flash-high"
            with patch(
                "app.core.model_manager.get_available_models",
                new=AsyncMock(return_value=_mock_models()),
            ):
                backend = await resolve_backend_model("claude-sonnet-5")
                self.assertEqual(backend, "gemini-3.7-flash-high")

        import asyncio
        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
