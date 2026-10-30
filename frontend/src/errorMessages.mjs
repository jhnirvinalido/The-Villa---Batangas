const NETWORK_FAILURE =
  /^(?:typeerror:\s*)?(?:failed to fetch|network error|networkerror(?: when attempting to fetch resource)?|network request failed|load failed|fetch failed|the network connection was lost)[.!]?$/i;
const TECHNICAL_DETAIL =
  /\b(?:method not allowed|traceback|stack trace|exception|internal server|server error|database|postgres(?:ql)?|supabase|rpc|sql|migration|render|smtp|resend|api key|environment variable|hosting setup|backend terminal|recorded error|provider|service role|secret|typeerror|referenceerror|syntaxerror|keyerror|attributeerror|indexerror|nullreferenceexception|uncaught|unhandled rejection|cannot read properties|is not a function|undefined is not|noneType|object has no attribute|relation .* does not exist|column .* does not exist)\b/i;
const GENERIC_ERROR =
  "We couldn't complete that request. Please try again. If the problem continues, contact The Villa.";

export function formatUserFacingMessage(message) {
  const text = String(message ?? "").trim();
  if (!text) {
    return "Something went wrong. Please try again.";
  }
  if (NETWORK_FAILURE.test(text)) {
    return "We couldn't connect to The Villa. Check your internet connection and try again.";
  }
  if (TECHNICAL_DETAIL.test(text)) {
    return GENERIC_ERROR;
  }
  return text;
}

export function getApiErrorMessage(payload, status) {
  const code = Number(status);
  if (code === 405 || code >= 500) {
    return GENERIC_ERROR;
  }
  if (code === 429) {
    return "Too many attempts. Please wait a moment and try again.";
  }

  const detail = payload?.detail;
  let message = "";
  if (typeof detail === "string") {
    message = detail;
  } else if (Array.isArray(detail)) {
    message = "Please check the information you entered and try again.";
  } else if (typeof detail?.message === "string") {
    message = detail.message;
  } else if (typeof payload?.message === "string") {
    message = payload.message;
  } else if (payload?.errors && typeof payload.errors === "object") {
    message = Object.values(payload.errors).flat().find(value => typeof value === "string") || "";
  }
  if (!message) {
    if (code === 401) {
      message = "Your session may have expired. Please sign in again.";
    } else if (code === 403) {
      message = "You don't have permission to complete that action.";
    } else if (code === 404) {
      message = "That item could not be found. Refresh and try again.";
    } else if (code === 409) {
      message = "The latest information has changed. Refresh and try again.";
    } else {
      message = "Please check the information and try again.";
    }
  }
  return formatUserFacingMessage(message);
}

export function getUserFacingError(error, fallback) {
  const status = Number(error?.status || error?.statusCode);
  if (status === 405 || status >= 500) {
    return GENERIC_ERROR;
  }
  const message =
    typeof error === "string"
      ? error
      : error?.message;
  return formatUserFacingMessage(message || fallback);
}
