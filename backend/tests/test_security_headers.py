import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from security_headers import SecurityHeadersMiddleware


class SecurityHeadersTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/ok")
        def ok():
            return {"status": "ok"}

        @app.get("/private")
        def private():
            from fastapi.responses import Response

            return Response(
                content="private",
                headers={"Referrer-Policy": "no-referrer"},
            )

        self.client = TestClient(app)
        self.https_client = TestClient(app, base_url="https://testserver")

    def test_security_headers_are_added_to_normal_and_error_responses(self):
        for path, expected_status in (("/ok", 200), ("/missing", 404)):
            with self.subTest(path=path):
                response = self.https_client.get(path)
                self.assertEqual(response.status_code, expected_status)
                self.assertEqual(
                    response.headers["X-Content-Type-Options"],
                    "nosniff",
                )
                self.assertEqual(response.headers["X-Frame-Options"], "DENY")
                self.assertEqual(
                    response.headers["Referrer-Policy"],
                    "strict-origin-when-cross-origin",
                )
                self.assertEqual(
                    response.headers["Permissions-Policy"],
                    "camera=(), microphone=(), geolocation=()",
                )
                self.assertEqual(
                    response.headers["Cross-Origin-Opener-Policy"],
                    "same-origin-allow-popups",
                )
                self.assertEqual(
                    response.headers["Strict-Transport-Security"],
                    "max-age=31536000",
                )

    def test_existing_endpoint_security_headers_are_preserved(self):
        response = self.https_client.get("/private")
        self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")

    def test_hsts_is_not_added_to_plain_http_responses(self):
        response = self.client.get("/ok")
        self.assertNotIn("Strict-Transport-Security", response.headers)


if __name__ == "__main__":
    unittest.main()
