import { FREQ, DOW } from "./api";

export const RESULT_META = {
  CLEAN: { text: "通过", color: "green" },
  DIFF_FOUND: { text: "有差异", color: "red" },
  INCOMPLETE: { text: "不完整", color: "amber" },
  NO_NEW_DATA: { text: "无新数据", color: "gray" },
};

export function resultMeta(runStatus, checkResult) {
  if (runStatus === "FAILED") return { text: "失败", color: "red" };
  if (runStatus === "RUNNING") return { text: "运行中", color: "blue" };
  return RESULT_META[checkResult] || { text: "—", color: "gray" };
}

function asList(v) {
  if (v == null || v === "") return [];
  if (Array.isArray(v)) return v;
  if (typeof v === "number") return [v];
  return String(v).split(",").map((x) => {
    const s = x.trim();
    if (s === "last") return "last";
    const n = Number(s);
    return Number.isNaN(n) ? s : n;
  }).filter((x) => x !== "");
}

export function freqText(d) {
  if (!d || !d.frequency) return "未调度";
  const n = d.interval || 1;
  const time = d.run_time ? " " + d.run_time : "";
  let f = d.frequency;
  let dows = asList(d.weekly_dow);
  let months = asList(d.yearly_month);
  let days = asList(d.monthly_dom);
  if (f === "weekdays") { f = "weekly"; dows = [1, 2, 3, 4, 5]; }
  if (f === "yearly") { f = "monthly"; if (!months.length) months = [12]; }
  if (f === "quarterly") { f = "monthly"; months = [3, 6, 9, 12]; if (!days.length) days = ["last"]; }
  if (f === "semiannual") { f = "monthly"; months = [6, 12]; if (!days.length) days = ["last"]; }
  if (f === "daily") return (n === 1 ? "每天" : `每${n}天`) + time;
  if (f === "weekly") {
    const ds = (dows.length ? dows : [1]).map((x) => "周" + (DOW[x] || x)).join("、");
    return (n === 1 ? "每周" : `每${n}周`) + " " + ds + time;
  }
  if (f === "monthly") {
    const ds = (days.length ? days : ["last"]).map((x) => (x === "last" ? "末" : x + "日")).join("、");
    if (months.length === 1) return `每年${months[0]}月` + ds + time;
    const ms = months.length && months.length < 12 ? months.map((m) => m + "月").join("、") : "每月";
    return ms + " " + (ds === "末" ? "最后一天" : ds) + time;
  }
  return (FREQ[d.frequency] || d.frequency) + time;
}

export function shortTime(t) {
  if (!t) return "—";
  const s = String(t).replace("T", " ");
  const y = s.slice(0, 4);
  const nowY = String(new Date().getFullYear());
  return y === nowY ? s.slice(5, 16) : s.slice(0, 16);
}

export function fileName(p) {
  if (!p) return "";
  return String(p).split(/[\\/]/).pop();
}
