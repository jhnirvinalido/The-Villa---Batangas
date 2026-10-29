// Accept both API rows and already-normalized editor data. Explicit empty galleries stay empty.
export function normalizeVillaCatalogRow(
  row
) {
  const legacyImageUrl = String(
    row?.image_url ?? row?.imageUrl ?? row?.image ?? ""
  ).trim();
  const gallery = row?.image_urls ?? row?.imageUrls;
  const imageUrls = Array.isArray(gallery)
    ? gallery.map((url) => String(url || "").trim()).filter(Boolean)
    : legacyImageUrl ? [legacyImageUrl] : [];

  return {
    id:
      String(
        row?.id || ""
      ).trim(),
    title:
      String(
        row?.title || "Villa"
      ).trim(),
    landingTitle:
      String(
        row?.landing_title ||
        row?.landingTitle ||
        row?.title ||
        "Villa"
      ).trim(),
    price:
      Number(
        row?.price || 0
      ),
    capacity:
      Math.max(
        1,
        Number(
          row?.capacity || 1
        )
      ),
    guestLabel:
      String(
        row?.guest_label ||
        row?.guestLabel ||
        ""
      ).trim(),
    beds:
      String(
        row?.beds || ""
      ).trim(),
    duration:
      String(
        row?.duration || ""
      ).trim(),
    stayHours:
      String(
        row?.stay_hours ||
        row?.stayHours || ""
      ).trim(),
    imageUrl: imageUrls[0] || "",
    imageUrls,
    status:
      String(
        row?.status ||
        "Available"
      ).trim(),
    underMaintenance:
      String(row?.status || "").trim() === "Under Maintenance",
    manualStatus: row?.manual_status || row?.manualStatus || row?.status || 'Available',
    operations: row?.operations || { open: 0, blocking: 0, inspections: 0, forVerification: 0 },
    shortDescription:
      String(
        row?.short_description ||
        row?.shortDescription ||
        row?.description ||
        ""
      ).trim(),
    details:
      String(
        row?.details ||
        row?.short_description ||
        row?.shortDescription ||
        ""
      ).trim(),
    amenities:
      Array.isArray(
        row?.amenities
      )
        ? row.amenities
        : [],
    updatedAt:
      row?.updated_at ||
        row?.updatedAt ||
      "",
  };
}

