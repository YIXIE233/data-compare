<template>
  <div style="max-width: 640px">
    <div v-if="suggest && suggest.frequency && !demand.schedule_confirmed" class="card" style="border-color: var(--brand); background: #fafaff; margin-bottom: 12px">
      <div style="display: flex; align-items: center; gap: 12px">
        <div style="flex: 1">
          <div style="font-size: 13px; font-weight: 600">建议方案</div>
          <div class="muted" style="font-size: 13px; margin-top: 2px">{{ freqText(suggest) }}</div>
        </div>
        <el-button @click="adopt">采用建议</el-button>
      </div>
    </div>

    <div class="card">
      <div class="freq-grid">
        <div v-for="f in FREQS" :key="f.v" class="freq-card" :class="{ on: form.frequency === f.v }" @click="form.frequency = f.v">
          {{ f.label }}
        </div>
      </div>

      <div class="presets">
        <span class="muted" style="font-size: 12px; margin-right: 6px">预设</span>
        <span v-for="p in PRESETS" :key="p.label" class="chip" :class="{ active: isPreset(p) }" @click="applyPreset(p)">{{ p.label }}</span>
      </div>

      <div v-if="form.frequency !== 'monthly'" class="row">
        <span class="lbl">每隔</span>
        <el-input-number v-model="form.interval" :min="1" :max="365" :controls="false" style="width: 72px" />
        <span class="muted">{{ form.frequency === 'weekly' ? '周' : '天' }}</span>
      </div>

      <div v-if="form.frequency === 'weekly'" class="row">
        <span class="lbl">星期</span>
        <div class="pick">
          <b v-for="o in DOWS" :key="o.v" :class="{ on: form.dows.includes(o.v) }" @click="toggle(form.dows, o.v)">{{ o.label }}</b>
        </div>
      </div>

      <div v-if="form.frequency === 'monthly'" class="row">
        <span class="lbl">月份</span>
        <div>
          <div class="pick">
            <b v-for="n in 12" :key="n" :class="{ on: form.months.includes(n) }" @click="toggle(form.months, n)">{{ n }}月</b>
          </div>
          <button class="link" type="button" @click="form.months = ALL_M.slice()">全选</button>
        </div>
      </div>

      <div v-if="form.frequency === 'monthly'" class="row">
        <span class="lbl">日期</span>
        <div>
          <div class="day-grid">
            <b v-for="n in 31" :key="n" :class="{ on: form.days.includes(n) }" @click="toggle(form.days, n)">{{ n }}</b>
            <b class="last" :class="{ on: form.days.includes('last') }" @click="toggle(form.days, 'last')">最后一天</b>
          </div>
        </div>
      </div>

      <div class="row">
        <span class="lbl">时间</span>
        <input v-model="form.run_time" type="time" class="time-in" />
        <span v-if="demand.next_run_at && demand.status === 'enabled'" class="muted">下次 {{ shortTime(demand.next_run_at) }}</span>
      </div>

      <div style="margin-top: 14px; display: flex; justify-content: flex-end">
        <el-button type="primary" :loading="busy" @click="save">保存调度</el-button>
      </div>
      <p v-if="err" style="color: var(--danger); font-size: 13px; margin: 8px 0 0">{{ err }}</p>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { api } from "../../api";
import { freqText, shortTime } from "../../fmt";

const props = defineProps({ demand: Object, suggest: Object });
const emit = defineEmits(["updated"]);

const ALL_M = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];
const FREQS = [
  { v: "daily", label: "每天" },
  { v: "weekly", label: "每周" },
  { v: "monthly", label: "每月" },
]
const PRESETS = [
  { label: "工作日", frequency: "weekly", interval: 1, dows: [1, 2, 3, 4, 5] },
  { label: "每周五", frequency: "weekly", interval: 1, dows: [5] },
  { label: "每月末", frequency: "monthly", months: ALL_M, days: ["last"] },
  { label: "每季末", frequency: "monthly", months: [3, 6, 9, 12], days: ["last"] },
  { label: "每年末", frequency: "monthly", months: [12], days: ["last"] },
];
const DOWS = [
  { v: 1, label: "周一" }, { v: 2, label: "周二" }, { v: 3, label: "周三" },
  { v: 4, label: "周四" }, { v: 5, label: "周五" }, { v: 6, label: "周六" }, { v: 7, label: "周日" },
];

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

function hydrate(d) {
  let f = d.frequency || "daily";
  let dows = asList(d.weekly_dow);
  let months = asList(d.yearly_month);
  let days = asList(d.monthly_dom);
  if (f === "weekdays") { f = "weekly"; dows = [1, 2, 3, 4, 5]; }
  if (f === "yearly") { f = "monthly"; if (!months.length) months = [12]; }
  if (f === "quarterly") { f = "monthly"; months = [3, 6, 9, 12]; if (!days.length) days = ["last"]; }
  if (f === "semiannual") { f = "monthly"; months = [6, 12]; if (!days.length) days = ["last"]; }
  if (f === "weekly" && !dows.length) dows = [1];
  if (f === "monthly") {
    if (!months.length) months = ALL_M.slice();
    if (!days.length) days = ["last"];
  }
  return {
    frequency: ["daily", "weekly", "monthly"].includes(f) ? f : "daily",
    run_time: d.run_time || "09:00",
    interval: d.interval || 1,
    dows,
    months,
    days,
  };
}

const form = reactive(hydrate(props.demand || {}));
const busy = ref(false);
const err = ref("");

function sameSet(a, b) {
  return [...a].map(String).sort().join() === [...b].map(String).sort().join();
}

function isPreset(p) {
  if (form.frequency !== p.frequency) return false;
  if ((form.interval || 1) !== (p.interval || 1)) return false;
  if (p.dows && !sameSet(form.dows, p.dows)) return false;
  if (p.months && !sameSet(form.months, p.months)) return false;
  if (p.days && !sameSet(form.days, p.days)) return false;
  return true;
}

function applyPreset(p) {
  form.frequency = p.frequency;
  form.interval = p.interval || 1;
  if (p.dows) form.dows = p.dows.slice();
  if (p.months) form.months = p.months.slice();
  if (p.days) form.days = p.days.slice();
}

function toggle(arr, v) {
  const i = arr.indexOf(v);
  if (i >= 0) {
    if (arr.length === 1) return;
    arr.splice(i, 1);
  } else {
    arr.push(v);
  }
}

function adopt() {
  Object.assign(form, hydrate({ ...props.demand, ...props.suggest, run_time: props.suggest.run_time || form.run_time }));
}

async function save() {
  err.value = "";
  if (form.frequency === "weekly" && !form.dows.length) {
    err.value = "请选择星期";
    return;
  }
  if (form.frequency === "monthly" && !form.days.length) {
    err.value = "请选择日期";
    return;
  }
  busy.value = true;
  try {
    await api.putSchedule(props.demand.id, {
      frequency: form.frequency,
      run_time: form.run_time,
      interval: form.frequency === "monthly" ? 1 : (form.interval || 1),
      weekly_dow: form.frequency === "weekly" ? form.dows : null,
      monthly_dom: form.frequency === "monthly" ? form.days : null,
      yearly_month: form.frequency === "monthly" ? form.months : null,
    });
    ElMessage.success("调度已保存");
    emit("updated");
  } catch (e) {
    err.value = e.message;
  } finally {
    busy.value = false;
  }
}
</script>

<style scoped>
.freq-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
.freq-card {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 10px 12px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
}
.freq-card:hover { border-color: var(--text-3); }

.freq-card.on { border-color: var(--brand); background: var(--brand-soft); color: var(--brand); }
.presets { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; margin-top: 12px; }
.row { display: flex; gap: 12px; margin-top: 14px; align-items: flex-start; }
.lbl { width: 36px; flex: none; color: var(--text-2); font-size: 13px; line-height: 32px; }
.pick { display: flex; flex-wrap: wrap; gap: 6px; }
.pick b, .day-grid b {
  min-width: 36px;
  text-align: center;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 8px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  user-select: none;
  background: #fff;
}
.pick b.on, .day-grid b.on { border-color: var(--brand); background: var(--brand-soft); color: var(--brand); }
.day-grid { display: grid; grid-template-columns: repeat(7, 36px); gap: 6px; }
.day-grid b.last { grid-column: span 3; }
.link { border: 0; background: none; color: var(--brand); cursor: pointer; font-size: 12px; padding: 6px 0 0; }
.time-in {
  height: 32px; border: 1px solid var(--border); border-radius: 6px;
  padding: 0 8px; font-size: 13px; color: var(--text-1);
}
</style>
