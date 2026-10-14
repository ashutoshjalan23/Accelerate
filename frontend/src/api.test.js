import { test, afterEach } from "node:test";
import assert from "node:assert/strict";
import { request } from "./api.js";

const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; });

test("cached-only choice is sent unchanged", async () => {
  globalThis.fetch = async (url, options) => {
    assert.equal(url, "http://localhost:8000/challenges/generate");
    assert.equal(JSON.parse(options.body).cache_only, true);
    assert.equal(options.headers["Content-Type"], "application/json");
    return { ok: true, json: async () => ({ cached: true }) };
  };
  assert.deepEqual(await request("http://localhost:8000", "/challenges/generate", {
    method: "POST", body: JSON.stringify({ github_url: "pallets/flask", cache_only: true }),
  }), { cached: true });
});

test("cache misses retain actionable backend error", async () => {
  globalThis.fetch = async () => ({ ok: false, status: 409, json: async () => ({ detail: "No saved challenge" }) });
  await assert.rejects(request("", "/challenges/generate"), error => error.status === 409 && error.message === "No saved challenge");
});

test("network errors identify backend connection failure", async () => {
  globalThis.fetch = async () => { throw new TypeError("fetch failed"); };
  await assert.rejects(request("http://localhost:8000", "/challenges"), /Cannot reach the API/);
});
