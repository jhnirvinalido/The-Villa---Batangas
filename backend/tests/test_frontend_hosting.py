import sys
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parents[1]))
from frontend_hosting import mount_frontend


class FrontendHostingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        build = Path(self.directory.name)
        (build / "index.html").write_text("<html>The Villa portal</html>")
        app = FastAPI()

        @app.get("/front-desk/payments")
        def payments():
            return {"data": []}

        mount_frontend(app, self.directory.name)
        self.client = TestClient(app)

    def test_front_desk_direct_visits_and_refreshes_serve_the_app(self):
        for path in ("/login", "/admin-dashboard", "/staff", "/maintenance", "/front-desk-login", "/front-desk", "/front-desk/", "/front-desk/bookings", "/front-desk?section=staff"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn("The Villa portal", response.text)

    def test_existing_api_routes_take_priority_over_browser_routes(self):
        response = self.client.get("/front-desk/payments")
        self.assertEqual(response.json(), {"data": []})

    def test_missing_apis_and_assets_remain_404(self):
        for path in ("/staff/missing", "/front-desk/bookings/missing/status", "/front-desk/payments/missing/status", "/assets/missing.js", "/front-desk/missing.js"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 404)
                self.assertNotIn("The Villa portal", response.text)
