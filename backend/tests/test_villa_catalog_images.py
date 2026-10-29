import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from villa_catalog import (  # noqa: E402
    DEFAULT_VILLA_CATALOG,
    VillaCatalogUpdate,
    VillaImageRemoval,
    _normalize_row,
    _villa_image_object_path,
    _villa_image_storage_filename,
)


class VillaCatalogImageTests(unittest.TestCase):
    def test_catalog_update_allows_omitted_short_description(self):
        update = VillaCatalogUpdate(
            title="Villa 1",
            landing_title="Villa 1",
            price=7500,
            capacity=8,
            details="A comfortable villa.",
        )
        self.assertEqual(update.short_description, "")

    def test_legacy_catalog_image_becomes_single_image_gallery(self):
        row = _normalize_row({
            "id": "villa-1",
            "image_url": "https://images.example/villa.jpg",
        })
        self.assertEqual(
            row["image_urls"],
            ["https://images.example/villa.jpg"],
        )
        self.assertEqual(row["image_url"], row["image_urls"][0])

    def test_empty_gallery_is_not_replaced_by_default_image(self):
        row = _normalize_row({
            "id": "villa-1",
            "image_url": "",
            "image_urls": [],
        })
        self.assertEqual(row["image_urls"], [])
        self.assertEqual(row["image_url"], "")

    def test_upload_image_urls_keep_first_photo_as_legacy_cover(self):
        row = _normalize_row({
            **DEFAULT_VILLA_CATALOG[0],
            "image_urls": ["/first.jpg", "/second.jpg"],
        })
        self.assertEqual(row["image_url"], "/first.jpg")
        self.assertEqual(row["image_urls"], ["/first.jpg", "/second.jpg"])

    def test_delete_only_accepts_own_villa_image_bucket_paths(self):
        base = "https://project.example/storage/v1/object/public/villa-images"
        self.assertEqual(
            _villa_image_object_path(
                f"{base}/villa-1/abc.jpg",
                "villa-1",
            ),
            "villa-1/abc.jpg",
        )
        self.assertIsNone(
            _villa_image_object_path(
                f"{base}/villa-2/abc.jpg",
                "villa-1",
            )
        )
        self.assertIsNone(
            _villa_image_object_path(
                "https://other.example/photo.jpg",
                "villa-1",
            )
        )

    def test_upload_storage_filename_preserves_recognizable_original_name(self):
        filename = _villa_image_storage_filename(
            "Family Villa - Bedroom 1.jpg",
            ".jpg",
        )
        self.assertTrue(filename.endswith("-Family-Villa-Bedroom-1.jpg"))
        self.assertRegex(filename, r"^[a-f0-9]{32}-")

    def test_gallery_removal_requires_at_least_one_image(self):
        with self.assertRaises(ValueError):
            VillaImageRemoval(image_urls=[])


if __name__ == "__main__":
    unittest.main()
