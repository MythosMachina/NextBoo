function trimTrailingSlash(value: string): string {
  return value.endsWith("/") ? value.slice(0, -1) : value;
}

function isLocalhostUrl(value: string): boolean {
  try {
    const parsed = new URL(value);
    return parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1";
  } catch {
    return false;
  }
}

export function getBrowserApiBaseUrl(): string {
  const configuredBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (typeof window !== "undefined") {
    if (configuredBaseUrl && !isLocalhostUrl(configuredBaseUrl)) {
      return trimTrailingSlash(configuredBaseUrl);
    }

    const protocol = window.location.protocol || "http:";
    const hostname = window.location.hostname || "localhost";
    return `${protocol}//${hostname}:18000`;
  }

  if (configuredBaseUrl) {
    return trimTrailingSlash(configuredBaseUrl);
  }

  return "http://localhost:18000";
}
