import unittest
import asyncio
import time
import httpx
from app.main import app
from app.core.model_manager import get_available_models, FALLBACK_MODELS
from app.core.security import API_KEY

class TestModelManager(unittest.TestCase):
    def test_get_available_models_and_cache(self):
        async def _run():
            # 1. Fetch models (CLI or fallback)
            models = await get_available_models(force_refresh=True)
            self.assertTrue(len(models) > 0)
            
            # Check model object structure
            first_model = models[0]
            self.assertTrue(hasattr(first_model, "id"))
            self.assertTrue(hasattr(first_model, "created"))
            self.assertEqual(first_model.object, "model")
            self.assertEqual(first_model.owned_by, "google")

            # 2. Second call should hit cache instantly (< 50ms)
            t0 = time.time()
            cached_models = await get_available_models()
            t1 = time.time()
            self.assertEqual(len(models), len(cached_models))
            self.assertLess((t1 - t0) * 1000, 50)
            
        asyncio.run(_run())

    def test_api_models_endpoint(self):
        async def _run():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                headers = {"Authorization": f"Bearer {API_KEY}"} if API_KEY else {}
                resp = await client.get("/v1/models", headers=headers)
                self.assertEqual(resp.status_code, 200)
                data = resp.json()
                self.assertEqual(data.get("object"), "list")
                self.assertIsInstance(data.get("data"), list)
                self.assertGreater(len(data.get("data")), 0)
                
                # Check that Gemini 3.7 or 3.6 is present
                model_ids = [m["id"] for m in data["data"]]
                has_gemini = any("gemini" in m.lower() for m in model_ids)
                self.assertTrue(has_gemini)

        asyncio.run(_run())

if __name__ == "__main__":
    unittest.main()
