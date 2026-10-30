const NETWORK_FAILURE =
  /^(?:typeerror:\s*)?(?:failed to fetch|network error|networkerror(?: when attempting to fetch resource)?|network request failed|load failed|fetch failed|the network connection was lost)[.!]?$/i;
const SERVER_FAILURE =
  /^(?:internal server error|500\s*[:\-]?\s*internal server error|server error \(5\d{2}\)|request failed with status 5\d{2})\.?$/i;

export function formatUserFacingMessage(message) {
  const text = String(message ?? "").trim();
  if (!text) {
    return "Something went wrong. Please try again.";
  }
  if (NETWORK_FAILURE.test(text)) {
    return "We couldn't connect to The Villa. Check your internet connection and try again.";
  }
  if (SERVER_FAILURE.test(text)) {
    return "The server couldn't complete this request. Please try again. If the problem continues, contact The Villa.";
  }
  return text;
}

export function getApiErrorMessage(payload, status) {
  const detail = payload?.detail;
  let message = "";
  if (typeof detail === "string") {
    message = detail;
  } else if (Array.isArray(detail)) {
    message = detail.map(item => {
      const location = Array.isArray(item?.loc)
        ? item.loc.filter(part => !["body", "query", "path"].includes(part)).at(-1)
        : "";
      const field = String(location || "").replaceAll("_", " ");
      const label = field
        ? field.charAt(0).toUpperCase() + field.slice(1)
        : "";
      const reason = String(item?.msg || "").trim();
      if (/field required|missing/i.test(reason)) return `${label || "This field"} is required.`;
      if (/valid|pattern/i.test(reason)) return `Enter a valid ${field || "value"}.`;
      return label ? `${label}: ${reason}` : reason;
    }).filter(Boolean).join(" ");
  } else if (typeof detail?.message === "string") {
    message = detail.message;
  } else if (typeof payload?.message === "string") {
    message = payload.message;
  } else if (payload?.errors && typeof payload.errors === "object") {
    message = Object.values(payload.errors).flat().find(value => typeof value === "string") || "";
  }
  if (!message) {
    const code = Number(status);
    if (code === 401) {
      message = "Your session may have expired. Please sign in again.";
    } else if (code === 404) {
      message = "That item could not be found. Refresh and try again.";
    } else if (code === 409) {
      message = "The latest information has changed. Refresh and try again.";
    } else if (code >= 500) {
      message = `Request failed with status ${code}.`;
    } else {
      message = "Please check the information and try again.";
    }
  }
  return formatUserFacingMessage(message);
}

export function getUserFacingError(error, fallback) {
  const message =
    typeof error === "string"
      ? error
      : error?.message;
  return formatUserFacingMessage(message || fallback);
}
