from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from supabase import Client


load_dotenv()

logger = logging.getLogger(
    "thevilla.villa_catalog"
)

SUPABASE_URL = os.getenv(
    "SUPABASE_URL",
    "",
).strip()

SUPABASE_ANON_KEY = os.getenv(
    "SUPABASE_ANON_KEY",
    "",
).strip()

SUPABASE_SERVICE_ROLE_KEY = os.getenv(
    "SUPABASE_SERVICE_ROLE_KEY",
    "",
).strip()

VILLA_IMAGE_BUCKET = "villa-images"
MAX_VILLA_IMAGE_BYTES = 8 * 1024 * 1024
MAX_VILLA_IMAGES = 30

router = APIRouter(
    prefix="/villa-catalog",
    tags=["Villa Catalog"],
)

DEFAULT_VILLA_CATALOG: list[dict[str, Any]] = [
    {
        "id": "villa-1",
        "title": "Villa 1",
        "landing_title": "Family Villa",
        "price": 4500.0,
        "capacity": 8,
        "guest_label": "Up to 8 guests",
        "beds": "4 double-sized beds",
        "duration": "20-hour overnight stay",
        "stay_hours": "3:00 PM – 11:00 AM",
        "image_url": "/family.jpg",
        "image_urls": ["/family.jpg"],
        "status": "Available",
        "short_description": (
            "A spacious private villa for families and groups "
            "of up to eight guests."
        ),
        "details": (
            "Best for family reunions, birthdays, and peaceful "
            "weekend stays. Includes private villa access, "
            "air-conditioned spaces, a kitchen, lounge area, "
            "plunge pool, garden, and complete guest essentials."
        ),
        "amenities": [
            {
                "title": "Plunge Pool",
                "icon": "villa",
                "items": [
                    "Heated pool",
                    "2 hours use of bubbles",
                ],
            },
            {
                "title": "Kitchen",
                "icon": "card",
                "items": [
                    "Induction stove",
                    "Stainless pan",
                    "Microwave",
                    "Refrigerator",
                    "Rice cooker",
                    "Electric kettle",
                    "Dishes and silverware",
                ],
            },
            {
                "title": "Lounge Area",
                "icon": "play",
                "items": [
                    "Smart projector",
                    "Ice cooler",
                    (
                        "JBL PartyBox Encore 2 Plus with "
                        "2 wireless microphones — available "
                        "for rent at ₱500/day"
                    ),
                ],
            },
            {
                "title": "Rooms",
                "icon": "users",
                "items": [
                    "4 double-sized beds",
                    "2 split-type air-conditioning units",
                    (
                        "2 bathrooms with hot and cold "
                        "shower"
                    ),
                    "Smart TV",
                ],
            },
            {
                "title": "Garden Area",
                "icon": "heart",
                "items": [
                    "Sauna — free for 30 minutes",
                    "Smoking area",
                    "BBQ grill",
                    "Charcoal available at ₱100/pack",
                ],
            },
            {
                "title": "Complimentary",
                "icon": "check",
                "items": [
                    "300 Mbps Wi-Fi",
                    "Mineral water",
                    "Bath towels and toilet paper",
                    (
                        "Guest kit: toothbrush, toothpaste, "
                        "soap, and shampoo"
                    ),
                ],
            },
        ],
    },
    {
        "id": "villa-2",
        "title": "Villa 2",
        "landing_title": "Couple Villa",
        "price": 5500.0,
        "capacity": 8,
        "guest_label": "Up to 8 guests",
        "beds": "4 double-sized beds",
        "duration": "20-hour overnight stay",
        "stay_hours": "3:00 PM – 11:00 AM",
        "image_url": "/couple.jpg",
        "image_urls": ["/couple.jpg"],
        "status": "Booked",
        "short_description": (
            "A comfortable private villa with complete "
            "amenities for up to eight guests."
        ),
        "details": (
            "A cozy and private stay suited for couples, "
            "families, anniversaries, and relaxing overnight "
            "escapes with complete Villa amenities."
        ),
        "amenities": [],
    },
    {
        "id": "villa-3",
        "title": "Villa 3",
        "landing_title": "Barkada Villa",
        "price": 6500.0,
        "capacity": 8,
        "guest_label": "Up to 8 guests",
        "beds": "4 double-sized beds",
        "duration": "20-hour overnight stay",
        "stay_hours": "3:00 PM – 11:00 AM",
        "image_url": "/barkada.jpg",
        "image_urls": ["/barkada.jpg"],
        "status": "Under Maintenance",
        "short_description": (
            "A roomy group villa with four beds, two "
            "bathrooms, and complete resort amenities."
        ),
        "details": (
            "Best for barkada bonding, birthdays, and small "
            "celebrations. It provides a group-friendly private "
            "space for a comfortable overnight stay."
        ),
        "amenities": [],
    },
    {
        "id": "villa-4",
        "title": "Villa 4",
        "landing_title": "Premium Villa",
        "price": 7500.0,
        "capacity": 4,
        "guest_label": "Up to 4 guests",
        "beds": "2 double-sized beds",
        "duration": "20-hour overnight stay",
        "stay_hours": "3:00 PM – 11:00 AM",
        "image_url": "/image1.jpg",
        "image_urls": ["/image1.jpg"],
        "status": "Available",
        "short_description": (
            "An intimate private villa designed for couples, "
            "small families, and groups of four."
        ),
        "details": (
            "A refined private stay for couples and small "
            "families who want comfort, privacy, and a complete "
            "Villa experience."
        ),
        "amenities": [],
    },
]

DEFAULT_BY_ID = {
    villa["id"]: villa
    for villa in DEFAULT_VILLA_CATALOG
}


class VillaAmenityGroup(BaseModel):
    title: str = Field(
        min_length=1,
        max_length=100,
    )
    icon: str = Field(
        default="check",
        max_length=50,
    )
    items: list[str] = Field(
        default_factory=list,
        max_length=100,
    )


class VillaCatalogUpdate(BaseModel):
    title: str = Field(
        min_length=1,
        max_length=120,
    )
    landing_title: str = Field(
        min_length=1,
        max_length=120,
    )
    price: float = Field(
        ge=0,
        le=10_000_000,
    )
    capacity: int = Field(
        ge=1,
        le=8,
    )
    guest_label: str = Field(
        default="",
        max_length=120,
    )
    beds: str = Field(
        default="",
        max_length=200,
    )
    duration: str = Field(
        default="",
        max_length=200,
    )
    stay_hours: str = Field(
        default="",
        max_length=120,
    )
    image_url: str = Field(
        default="",
        max_length=2000,
    )
    image_urls: list[str] | None = Field(
        default=None,
        max_length=MAX_VILLA_IMAGES,
    )
    status: str | None = Field(
        default=None,
        max_length=60,
    )
    short_description: str = Field(
        default="",
        max_length=1000,
    )
    details: str = Field(
        min_length=1,
        max_length=5000,
    )
    amenities: list[VillaAmenityGroup] = Field(
        default_factory=list,
        max_length=50,
    )


class VillaImageRemoval(BaseModel):
    image_urls: list[str] = Field(
        min_length=1,
        max_length=MAX_VILLA_IMAGES,
    )


def _service() -> Client:
    if (
        not SUPABASE_URL
        or not SUPABASE_SERVICE_ROLE_KEY
    ):
        raise HTTPException(
            status_code=500,
            detail=(
                "The Villa catalog database "
                "configuration is incomplete."
            ),
        )

    from supabase import create_client

    return create_client(
        SUPABASE_URL,
        SUPABASE_SERVICE_ROLE_KEY,
    )


def _attribute(
    value: Any,
    name: str,
    default: Any = None,
) -> Any:
    if isinstance(value, dict):
        return value.get(
            name,
            default,
        )

    return getattr(
        value,
        name,
        default,
    )


def _clean_status(
    value: Any,
) -> str:
    normalized = str(
        value or "Available"
    ).strip()

    allowed = {
        "Available",
        "Booked",
        "Under Maintenance",
    }

    return (
        normalized
        if normalized in allowed
        else "Available"
    )


def _normalize_amenities(
    value: Any,
) -> list[dict[str, Any]]:
    if not isinstance(
        value,
        list,
    ):
        return []

    normalized: list[
        dict[str, Any]
    ] = []

    for group in value:
        if isinstance(
            group,
            str,
        ):
            text = group.strip()

            if text:
                normalized.append(
                    {
                        "title": "Amenities",
                        "icon": "check",
                        "items": [text],
                    }
                )

            continue

        if not isinstance(
            group,
            dict,
        ):
            continue

        items = [
            str(item).strip()
            for item in (
                group.get("items")
                or []
            )
            if str(item).strip()
        ]

        if not items:
            continue

        normalized.append(
            {
                "title": str(
                    group.get("title")
                    or "Amenities"
                ).strip(),
                "icon": str(
                    group.get("icon")
                    or "check"
                ).strip(),
                "items": items,
            }
        )

    return normalized


def _normalize_row(
    row: dict[str, Any],
) -> dict[str, Any]:
    villa_id = str(
        row.get("id")
        or ""
    ).strip()

    fallback = (
        DEFAULT_BY_ID.get(
            villa_id
        )
        or DEFAULT_VILLA_CATALOG[0]
    )

    price_value = (
        row.get("price")
        if row.get("price")
        is not None
        else fallback["price"]
    )

    try:
        price = float(
            Decimal(
                str(price_value)
            )
        )
    except Exception:
        price = float(
            fallback["price"]
        )

    amenities = (
        _normalize_amenities(
            row.get("amenities")
        )
    )

    if not amenities:
        amenities = (
            _normalize_amenities(
                fallback.get(
                    "amenities"
                )
            )
        )

    raw_image_urls = row.get("image_urls")
    if isinstance(raw_image_urls, list):
        image_urls = [
            str(image_url).strip()
            for image_url in raw_image_urls
            if str(image_url).strip()
        ][:MAX_VILLA_IMAGES]
    else:
        legacy_image_url = str(
            row.get("image_url")
            or fallback.get("image_url")
            or ""
        ).strip()
        image_urls = [legacy_image_url] if legacy_image_url else []
    primary_image_url = image_urls[0] if image_urls else ""

    return {
        "id": villa_id
        or fallback["id"],
        "title": str(
            row.get("title")
            or fallback["title"]
        ).strip(),
        "landing_title": str(
            row.get(
                "landing_title"
            )
            or fallback[
                "landing_title"
            ]
        ).strip(),
        "price": price,
        "capacity": max(
            1,
            int(
                row.get("capacity")
                or fallback[
                    "capacity"
                ]
            ),
        ),
        "guest_label": str(
            row.get(
                "guest_label"
            )
            or fallback[
                "guest_label"
            ]
        ).strip(),
        "beds": str(
            row.get("beds")
            or fallback["beds"]
        ).strip(),
        "duration": str(
            row.get("duration")
            or fallback[
                "duration"
            ]
        ).strip(),
        "stay_hours": str(
            row.get(
                "stay_hours"
            )
            or fallback[
                "stay_hours"
            ]
        ).strip(),
        "image_url": primary_image_url,
        "image_urls": image_urls,
        "status": _clean_status(
            row.get("status")
            or fallback["status"]
        ),
        "short_description": str(
            row.get(
                "short_description"
            )
            or fallback[
                "short_description"
            ]
        ).strip(),
        "details": str(
            row.get("details")
            or fallback["details"]
        ).strip(),
        "amenities": amenities,
        "updated_at": row.get(
            "updated_at"
        ),
        "updated_by": row.get(
            "updated_by"
        ),
    }


def _read_catalog_rows(
    client: Client,
) -> list[dict[str, Any]]:
    try:
        response = (
            client.table(
                "villa_catalog"
            )
            .select("*")
            .order("id")
            .execute()
        )

        rows = _attribute(
            response,
            "data",
            [],
        ) or []

    except Exception as error:
        logger.warning(
            "Could not read public.villa_catalog: %s",
            error,
        )

        return [
            _normalize_row(
                villa
            )
            for villa in DEFAULT_VILLA_CATALOG
        ]

    if not isinstance(
        rows,
        list,
    ) or not rows:
        return [
            _normalize_row(
                villa
            )
            for villa in DEFAULT_VILLA_CATALOG
        ]

    normalized_by_id = {
        row["id"]: row
        for row in (
            _normalize_row(
                item
            )
            for item in rows
            if isinstance(
                item,
                dict,
            )
        )
    }

    return [
        normalized_by_id.get(
            villa["id"],
            _normalize_row(
                villa
            ),
        )
        for villa in DEFAULT_VILLA_CATALOG
    ]


def _read_rows(client: Client) -> list[dict[str, Any]]:
    from villa_operations import apply_operational_status
    return apply_operational_status(_read_catalog_rows(client), client)


def get_villa_catalog_map(
    client: Client | None = None,
) -> dict[str, dict[str, Any]]:
    active_client = (
        client
        or _service()
    )

    rows = _read_rows(
        active_client
    )

    result: dict[
        str,
        dict[str, Any]
    ] = {}

    for row in rows:
        status = _clean_status(
            row.get("status")
        )

        result[row["id"]] = {
            "name": row["title"],
            "price": Decimal(
                str(
                    row["price"]
                )
            ),
            "capacity": int(
                row["capacity"]
            ),
            "image": row[
                "image_url"
            ],
            "operational_status": (
                "under_maintenance"
                if status ==
                "Under Maintenance"
                else "available"
            ),
            "manual_operational_status": (
                "under_maintenance" if _clean_status(row.get("manual_status", row.get("status"))) == "Under Maintenance" else "available"
            ),
            "maintenance_dates": row.get("operations", {}).get("blockingDates", []),
            "undated_maintenance": row.get("operations", {}).get("undatedBlocking", False),
        }

    return result


def _get_auth_user(
    request: Request,
) -> dict[str, Any]:
    authorization = (
        request.headers.get(
            "Authorization",
            "",
        )
    )

    if not authorization.startswith(
        "Bearer "
    ):
        raise HTTPException(
            status_code=401,
            detail=(
                "Administrator login is required."
            ),
        )

    token = authorization[
        len("Bearer "):
    ].strip()

    if not token:
        raise HTTPException(
            status_code=401,
            detail=(
                "Administrator login is required."
            ),
        )

    response = requests.get(
        f"{SUPABASE_URL}/auth/v1/user",
        headers={
            "apikey":
                SUPABASE_ANON_KEY,
            "Authorization":
                f"Bearer {token}",
            "Accept":
                "application/json",
        },
        timeout=(5, 20),
    )

    if response.status_code != 200:
        raise HTTPException(
            status_code=401,
            detail=(
                "Your administrator session "
                "has expired."
            ),
        )

    payload = response.json()

    if not isinstance(
        payload,
        dict,
    ):
        raise HTTPException(
            status_code=401,
            detail=(
                "Your administrator session "
                "is invalid."
            ),
        )

    return payload


def _require_admin(
    request: Request,
) -> dict[str, Any]:
    user = _get_auth_user(
        request
    )

    user_metadata = (
        user.get(
            "user_metadata"
        )
        or {}
    )

    app_metadata = (
        user.get(
            "app_metadata"
        )
        or {}
    )

    candidate_roles = {
        str(
            user_metadata.get(
                "role"
            )
            or ""
        )
        .strip()
        .lower(),
        str(
            user_metadata.get(
                "position"
            )
            or ""
        )
        .strip()
        .lower(),
        str(
            app_metadata.get(
                "role"
            )
            or ""
        )
        .strip()
        .lower(),
    }

    user_id = str(
        user.get("id")
        or ""
    ).strip()

    if user_id:
        try:
            profile_response = (
                _service()
                .table("profiles")
                .select("*")
                .eq("id", user_id)
                .limit(1)
                .execute()
            )

            profile_rows = _attribute(
                profile_response,
                "data",
                [],
            ) or []

            if (
                isinstance(
                    profile_rows,
                    list,
                )
                and profile_rows
                and isinstance(
                    profile_rows[0],
                    dict,
                )
            ):
                profile = (
                    profile_rows[0]
                )

                candidate_roles.update(
                    {
                        str(
                            profile.get(
                                "role"
                            )
                            or ""
                        )
                        .strip()
                        .lower(),
                        str(
                            profile.get(
                                "position"
                            )
                            or ""
                        )
                        .strip()
                        .lower(),
                        str(
                            profile.get(
                                "user_type"
                            )
                            or ""
                        )
                        .strip()
                        .lower(),
                    }
                )
        except Exception:
            logger.debug(
                "Admin profile role lookup failed.",
                exc_info=True,
            )

    allowed = {
        "admin",
        "administrator",
        "villa administrator",
    }

    if not (
        candidate_roles
        & allowed
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "Only an administrator can edit "
                "Villa prices and details."
            ),
        )

    return user


@router.get("/public")
def public_villa_catalog():
    rows = _read_rows(
        _service()
    )

    return {
        "data": rows,
        "updated_at":
            datetime.now(
                timezone.utc
            ).isoformat(),
    }


@router.get("/admin")
def admin_villa_catalog(
    request: Request,
):
    _require_admin(
        request
    )

    return {
        "data": _read_rows(
            _service()
        )
    }


@router.put("/{villa_id}")
def update_villa_catalog(
    villa_id: str,
    data: VillaCatalogUpdate,
    request: Request,
):
    user = _require_admin(
        request
    )

    normalized_id = str(
        villa_id
    ).strip()

    if normalized_id not in DEFAULT_BY_ID:
        raise HTTPException(
            status_code=404,
            detail=(
                "The selected Villa does not exist."
            ),
        )

    now = datetime.now(
        timezone.utc
    ).isoformat()

    try:
        service = _service()
        existing_response = (
            service
            .table("villa_catalog")
            .select("*")
            .eq("id", normalized_id)
            .limit(1)
            .execute()
        )
        existing_rows = _attribute(
            existing_response,
            "data",
            [],
        ) or []
        existing_short_description = (
            str(existing_rows[0].get("short_description") or "").strip()
            if existing_rows and isinstance(existing_rows[0], dict)
            else ""
        )

        from villa_operations import operation_summary, apply_operational_status
        summaries = operation_summary(service)
        blocking = summaries.get(normalized_id, {}).get("blocking", 0)
        previous_villa = _normalize_row(existing_rows[0] if existing_rows else DEFAULT_BY_ID[normalized_id])
        effective_status = apply_operational_status([dict(previous_villa)], service, summaries)[0]["status"]
        if (blocking and data.status is not None
                and _clean_status(data.status) != previous_villa["status"]):
            raise HTTPException(status_code=409, detail="Verify or cancel the active blocking maintenance request before changing this villa's manual status.")
        saved_status = (
            previous_villa["status"]
            if blocking
            else _clean_status(data.status) if data.status is not None else effective_status
        )

        payload = {
            "id": normalized_id,
            "title": data.title.strip(),
            "landing_title":
                data.landing_title.strip(),
            "price": float(
                data.price
            ),
            "capacity":
                int(data.capacity),
            "guest_label":
                data.guest_label.strip()
                or (
                    f"Up to "
                    f"{data.capacity} guests"
                ),
            "beds":
                data.beds.strip(),
            "duration":
                data.duration.strip(),
            "stay_hours":
                data.stay_hours.strip(),
            "image_url": (
                data.image_urls[0].strip()
                if data.image_urls is not None and data.image_urls
                else (
                    ""
                    if data.image_urls is not None
                    else data.image_url.strip()
                )
            ),
            "status": saved_status,
            "short_description":
                data.short_description.strip()
                or existing_short_description
                or str(
                    DEFAULT_BY_ID[normalized_id].get(
                        "short_description",
                        "",
                    )
                ).strip(),
            "details":
                data.details.strip(),
            "amenities": [
                {
                    "title":
                        group.title.strip(),
                    "icon":
                        group.icon.strip()
                        or "check",
                    "items": [
                        item.strip()
                        for item in
                        group.items
                        if item.strip()
                    ],
                }
                for group in
                data.amenities
                if any(
                    item.strip()
                    for item in
                    group.items
                )
            ],
            "updated_at": now,
            "updated_by":
                str(
                    user.get("id")
                    or ""
                ).strip()
                or None,
        }

        if data.image_urls is not None:
            payload["image_urls"] = [
                image_url.strip()
                for image_url in data.image_urls
                if image_url.strip()
            ]

        response = (
            service
            .table(
                "villa_catalog"
            )
            .upsert(
                payload,
                on_conflict="id",
            )
            .execute()
        )

        rows = _attribute(
            response,
            "data",
            [],
        ) or []

    except HTTPException:
        raise
    except Exception as error:
        logger.exception("Could not update Villa catalog.")

        raise HTTPException(
            status_code=500,
            detail=(
                "The Villa could not be saved. "
                "Run the provided Supabase migration "
                "and try again."
            ),
        ) from error

    saved = (
        rows[0]
        if (
            isinstance(rows, list)
            and rows
            and isinstance(
                rows[0],
                dict,
            )
        )
        else payload
    )

    return {
        "message":
            "Villa catalog updated.",
        "data": apply_operational_status([_normalize_row(saved)], service)[0],
    }


def _villa_image_object_path(
    image_url: str,
    villa_id: str,
) -> str | None:
    parsed = urlparse(image_url)
    marker = (
        f"/storage/v1/object/public/"
        f"{VILLA_IMAGE_BUCKET}/"
    )
    if marker not in parsed.path:
        return None

    object_path = parsed.path.split(marker, 1)[1]
    expected_prefix = f"{villa_id}/"
    if not object_path.startswith(expected_prefix):
        return None

    filename = object_path[len(expected_prefix):]
    if not filename or "/" in filename:
        return None
    return object_path


def _villa_image_storage_filename(
    original_filename: str | None,
    extension: str,
) -> str:
    filename = str(
        original_filename or ""
    ).replace("\\", "/").rsplit("/", 1)[-1]
    stem = os.path.splitext(filename)[0]
    safe_stem = re.sub(
        r"[^A-Za-z0-9_-]+",
        "-",
        stem,
    ).strip("-_")[:80]
    safe_stem = re.sub(r"-{2,}", "-", safe_stem).strip("-_")
    return (
        f"{uuid.uuid4().hex}-"
        f"{safe_stem or 'villa-photo'}"
        f"{extension}"
    )


@router.post("/{villa_id}/images")
async def upload_villa_images(
    villa_id: str,
    request: Request,
    files: list[UploadFile] = File(...),
):
    _require_admin(request)
    normalized_id = str(villa_id).strip()
    if normalized_id not in DEFAULT_BY_ID:
        raise HTTPException(
            status_code=404,
            detail="The selected Villa does not exist.",
        )
    if not files or len(files) > MAX_VILLA_IMAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Choose between 1 and {MAX_VILLA_IMAGES} images.",
        )

    allowed_types = {
        "image/jpeg": (".jpg", lambda data: data.startswith(b"\xff\xd8\xff")),
        "image/png": (".png", lambda data: data.startswith(b"\x89PNG\r\n\x1a\n")),
        "image/webp": (
            ".webp",
            lambda data: data.startswith(b"RIFF") and data[8:12] == b"WEBP",
        ),
    }
    client = _service()
    uploaded_paths: list[str] = []
    uploaded_urls: list[str] = []

    try:
        for image in files:
            image_type = (image.content_type or "").lower()
            image_format = allowed_types.get(image_type)
            if image_format is None:
                raise HTTPException(
                    status_code=415,
                    detail="Use JPG, PNG, or WebP image files.",
                )

            image_data = await image.read(MAX_VILLA_IMAGE_BYTES + 1)
            if not image_data or len(image_data) > MAX_VILLA_IMAGE_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail="Each image must be smaller than 8 MB.",
                )
            extension, signature_check = image_format
            if not signature_check(image_data):
                raise HTTPException(
                    status_code=415,
                    detail="The selected file is not a valid image.",
                )

            storage_filename = _villa_image_storage_filename(
                image.filename,
                extension,
            )
            object_path = f"{normalized_id}/{storage_filename}"
            client.storage.from_(VILLA_IMAGE_BUCKET).upload(
                path=object_path,
                file=image_data,
                file_options={
                    "cache-control": "31536000",
                    "content-type": image_type,
                    "upsert": "false",
                },
            )
            uploaded_paths.append(object_path)
            uploaded_urls.append(
                f"{SUPABASE_URL}/storage/v1/object/public/"
                f"{VILLA_IMAGE_BUCKET}/{object_path}"
            )
    except HTTPException:
        if uploaded_paths:
            try:
                client.storage.from_(VILLA_IMAGE_BUCKET).remove(uploaded_paths)
            except Exception:
                logger.exception("Could not roll back partial Villa image upload.")
        raise
    except Exception as error:
        if uploaded_paths:
            try:
                client.storage.from_(VILLA_IMAGE_BUCKET).remove(uploaded_paths)
            except Exception:
                logger.exception("Could not roll back partial Villa image upload.")
        logger.exception("Could not upload Villa images.")
        raise HTTPException(
            status_code=500,
            detail="The images could not be uploaded. Check Supabase Storage configuration and try again.",
        ) from error
    finally:
        for image in files:
            await image.close()

    return {"data": {"image_urls": uploaded_urls}}


@router.delete("/{villa_id}/images")
def delete_villa_images(
    villa_id: str,
    data: VillaImageRemoval,
    request: Request,
):
    _require_admin(request)
    normalized_id = str(villa_id).strip()
    if normalized_id not in DEFAULT_BY_ID:
        raise HTTPException(
            status_code=404,
            detail="The selected Villa does not exist.",
        )

    object_paths = list(dict.fromkeys(
        object_path
        for image_url in data.image_urls
        if (
            object_path := _villa_image_object_path(
                image_url,
                normalized_id,
            )
        )
    ))
    if not object_paths:
        return {"message": "No uploaded Villa images needed removal.", "removed": 0}

    try:
        _service().storage.from_(VILLA_IMAGE_BUCKET).remove(object_paths)
    except Exception as error:
        logger.exception("Could not remove Villa image files.")
        raise HTTPException(
            status_code=500,
            detail="The Villa changes were saved, but some image files could not be deleted.",
        ) from error

    return {"message": "Villa images removed.", "removed": len(object_paths)}
