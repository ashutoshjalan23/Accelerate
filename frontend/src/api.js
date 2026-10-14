export async function request(baseUrl, path, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 300000);
  try {
    const response = await fetch(`${baseUrl}${path}`, {
      ...options,
      headers: { ...(options.body ? { "Content-Type": "application/json" } : {}), ...options.headers },
      signal: controller.signal,
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(typeof payload.detail === "string" ? payload.detail : "Check the repository URL and try again.");
      error.status = response.status;
      throw error;
    }
    return payload;
  } catch (error) {
    if (error.name === "AbortError") throw new Error("Generation is taking longer than five minutes. Check the API logs; the server may still finish.");
    if (error instanceof TypeError) throw new Error(`Cannot reach the API at ${baseUrl}. Start the backend and retry.`);
    throw error;
  } finally {
    clearTimeout(timer);
  }
}
