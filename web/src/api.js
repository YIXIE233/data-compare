async function req(path, opts = {}) {
  const r = await fetch(path, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  const ct = r.headers.get("content-type") || "";
  const data = ct.includes("json") ? await r.json() : await r.blob();
  if (!r.ok) throw Object.assign(new Error((data && data.detail) || r.status), { status: r.status, data });
  return data;
}

export const api = {
  demands: (qs = "") => req("/api/demands" + qs),
  demand: (id) => req(`/api/demands/${id}`),
  updateDemand: (id, body) => req(`/api/demands/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  deleteDemand: (id) => req(`/api/demands/${id}`, { method: "DELETE" }),
  profiles: (all = false) => req("/api/module-profiles" + (all ? "?all=1" : "")),
  putProfile: (id, body) => req(`/api/module-profiles/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  previewSource: (path) => req("/api/sources/preview", { method: "POST", body: JSON.stringify({ path }) }),
  parsePath: (body) => req("/api/path-parse", { method: "POST", body: JSON.stringify(body) }),
  createDemand: (body) => req("/api/demands", { method: "POST", body: JSON.stringify(body) }),
  mapping: (id) => req(`/api/demands/${id}/mapping`),
  putMapping: (id, body) => req(`/api/demands/${id}/mapping`, { method: "PUT", body: JSON.stringify(body) }),
  bulkConfirm: (id, body) => req(`/api/demands/${id}/mapping/bulk-confirm`, { method: "POST", body: JSON.stringify(body) }),
  bulkClear: (id, body) => req(`/api/demands/${id}/mapping/bulk-clear`, { method: "POST", body: JSON.stringify(body) }),
  refreshTemplate: (id) => req(`/api/demands/${id}/refresh-template`, { method: "POST" }),
  refreshSource: (id) => req(`/api/demands/${id}/refresh-source`, { method: "POST" }),
  schedule: (id) => req(`/api/demands/${id}/schedule`),
  putSchedule: (id, body) => req(`/api/demands/${id}/schedule`, { method: "PUT", body: JSON.stringify(body) }),
  enable: (id) => req(`/api/demands/${id}/enable`, { method: "POST" }),
  disable: (id) => req(`/api/demands/${id}/disable`, { method: "POST" }),
  run: (id) => req(`/api/demands/${id}/run`, { method: "POST" }),
  backfill: (id, periods) => req(`/api/demands/${id}/backfill`, { method: "POST", body: JSON.stringify({ periods }) }),
  retryRun: (id) => req(`/api/runs/${id}/retry`, { method: "POST" }),
  demandRuns: (id) => req(`/api/demands/${id}/runs`),
  getRun: (id) => req(`/api/runs/${id}`),
  diffs: (id) => req(`/api/runs/${id}/diffs`),
  settings: () => req("/api/settings"),
  putSettings: (body) => req("/api/settings", { method: "PUT", body: JSON.stringify(body) }),
  createProfile: (body) => req("/api/module-profiles", { method: "POST", body: JSON.stringify(body) }),
  deleteProfile: (id) => req(`/api/module-profiles/${id}`, { method: "DELETE" }),
  pickFile: (start) => req("/api/pick/file", { method: "POST", body: JSON.stringify({ start: start || null }) }),
  pickDir: (start) => req("/api/pick/dir", { method: "POST", body: JSON.stringify({ start: start || null }) }),
  checkPath: (path, kind) => req("/api/paths/check", { method: "POST", body: JSON.stringify({ path, kind }) }),
  categories: (module) => req("/api/categories" + (module ? "?module=" + encodeURIComponent(module) : "")),
  addCategory: (module, name) => req("/api/categories", { method: "POST", body: JSON.stringify({ module, name }) }),
  deleteCategory: (id) => req(`/api/categories/${id}`, { method: "DELETE" }),
};

export async function downloadXlsx(id) {
  const r = await fetch(`/api/runs/${id}/diffs.xlsx`);
  if (!r.ok) throw new Error("下载失败");
  const b = await r.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(b);
  a.download = `run_${id}_diff.xlsx`;
  a.click();
  URL.revokeObjectURL(a.href);
}

export const FREQ = {
  daily: "每天",
  weekdays: "每工作日",
  weekly: "每周",
  monthly: "每月",
};

export const DOW = { 0: "日", 1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六" };
