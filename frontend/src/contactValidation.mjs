export function normalizePhilippinePhone(value) {
  const phone = String(value ?? "").trim();
  if (!phone || !/^[0-9+\s().-]+$/.test(phone)) return "";

  const compact = phone.replace(/[\s().-]/g, "");
  if (/^(?:\+?63)?9\d{9}$/.test(compact)) {
    return `+63${compact.replace(/^\+?63/, "")}`;
  }
  if (/^09\d{9}$/.test(compact)) {
    return `+63${compact.slice(1)}`;
  }
  return "";
}

export function isValidEmailAddress(value) {
  const email = String(value ?? "").trim();
  if (email.length > 254) return false;

  const parts = email.split("@");
  if (parts.length !== 2) return false;
  const [local, domain] = parts;
  if (
    !local ||
    local.length > 64 ||
    local.startsWith(".") ||
    local.endsWith(".") ||
    local.includes("..") ||
    !/^[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+$/i.test(local)
  ) {
    return false;
  }

  const labels = domain.split(".");
  if (labels.length < 2 || labels.some(label =>
    !label ||
    label.length > 63 ||
    !/^[A-Z0-9](?:[A-Z0-9-]*[A-Z0-9])?$/i.test(label)
  )) {
    return false;
  }

  return /^(?:[A-Z]{2,}|XN--[A-Z0-9-]{2,})$/i.test(labels.at(-1));
}
