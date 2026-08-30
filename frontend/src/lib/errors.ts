import { ApiError } from "@/api/client";

// Central place mapping an error (ApiError from the backend, or a raw
// network/rendering failure) to what a page should actually show the user.
// Before this existed, every page hand-rolled its own flat error string —
// same generic wording for a 404, a 500, and "the network is down", with no
// way to offer a "Retry" action or read `retry_after_seconds` off a 429.

export interface ErrorPresentation {
  title: string;
  description: string;
  // Whether showing a "Retry" affordance makes sense (a 403 permission
  // error retrying with the same request won't ever succeed; a 500/network
  // blip might).
  retryable: boolean;
  // Present only for rate-limit lockouts (429, or 403 login lockouts that
  // reuse the same shape) — seconds until the caller may try again.
  retryAfterSeconds?: number;
}

interface StructuredDetail {
  error_code?: string;
  message?: string;
  retry_after_seconds?: number;
}

function structuredDetail(body: unknown): StructuredDetail | undefined {
  if (!body || typeof body !== "object") return undefined;
  const detail = (body as { detail?: unknown }).detail;
  if (!detail || typeof detail !== "object") return undefined;
  return detail as StructuredDetail;
}

export function describeError(error: unknown): ErrorPresentation {
  if (error instanceof ApiError) {
    const detail = structuredDetail(error.body);

    if (error.status === 429 || detail?.error_code === "too_many_attempts") {
      return {
        title: "Too many attempts",
        description: detail?.message ?? error.message,
        retryable: false,
        retryAfterSeconds: detail?.retry_after_seconds,
      };
    }
    if (error.status === 403) {
      return {
        title: "Access denied",
        description:
          detail?.message ?? error.message ?? "You don't have permission to do this.",
        retryable: false,
      };
    }
    if (error.status === 404) {
      return {
        title: "Not found",
        description: error.message || "The requested resource doesn't exist (or was removed).",
        retryable: false,
      };
    }
    if (error.status >= 500) {
      return {
        title: "Server error",
        description: "Something went wrong on the server. Please try again in a moment.",
        retryable: true,
      };
    }
    // 400/401/409/422/... — no dedicated case, but still a real message
    // from the API worth showing verbatim rather than a generic fallback.
    return { title: "Request failed", description: error.message || "Please try again.", retryable: true };
  }

  // fetch() throws a plain TypeError (not an ApiError) when the network is
  // unreachable entirely — CORS failure, DNS failure, server not running.
  if (error instanceof TypeError) {
    return {
      title: "Network error",
      description: "Couldn't reach the server. Check your connection and try again.",
      retryable: true,
    };
  }

  return {
    title: "Unexpected error",
    description: error instanceof Error ? error.message : "Something went wrong.",
    retryable: true,
  };
}
