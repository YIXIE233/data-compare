<template>
  <p v-if="loading && !d" class="muted">加载中…</p>
  <p v-if="err && !d" style="color: var(--danger); font-size: 13px">{{ err }}</p>
  <div v-if="d">
    <div class="page-head">
      <div style="display: flex; align-items: center; gap: 12px; min-width: 0">
        <el-button text circle aria-label="返回任务列表" @click="$router.push('/demands')"><el-icon><ArrowLeft /></el-icon></el-button>
        <div style="min-width: 0">
          <div class="page-title" style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap">{{ d.demand_name }}</div>
          <div class="muted" style="font-size: 12px">{{ fileName(d.source_path) }}</div>
        </div>
        <Pill v-bind="statusMeta" />
      </div>
      <div style="display: flex; gap: 8px">
        <el-button v-if="showRun" :loading="busy" @click="toggleEnable">{{ d.status === 'enabled' ? '停用' : '启用' }}</el-button>
        <el-button type="danger" plain :loading="busy" @click="remove">删除</el-button>
        <el-button v-if="showRun" type="primary" :loading="busy" @click="run">立即运行</el-button>
        <el-button v-if="cta && !showRun" type="primary" :loading="busy" @click="cta.action">{{ cta.label }}<el-icon style="margin-left: 4px"><ArrowRight /></el-icon></el-button>
        <el-button v-else-if="cta" :loading="busy" @click="cta.action">{{ cta.label }}</el-button>
      </div>
    </div>


    <p v-if="err" style="color: var(--danger); font-size: 13px">{{ err }}</p>

    <div class="tabs">
      <span v-for="t in tabs" :key="t.key" class="tab" :class="{ active: tab === t.key }" @click="setTab(t.key)">
        {{ t.label }}<span v-if="t.num" class="num">{{ t.num }}</span>
      </span>
    </div>

    <MappingPanel v-if="tab === 'mapping'" :demand="d" @updated="load" />
    <SchedulePanel v-else-if="tab === 'schedule'" :demand="d" :suggest="suggest" @updated="load" />
    <ConfigPanel v-else-if="tab === 'config'" :demand="d" @updated="load" />
    <RunsPanel v-else :demand-id="d.id" :key="'runs' + reloadKey" />
  </div>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ArrowLeft, ArrowRight } from "@element-plus/icons-vue";
import { ElMessageBox } from "element-plus";
import { api } from "../api";
import { fileName } from "../fmt";
import Pill from "../components/Pill.vue";
import MappingPanel from "./demand/MappingPanel.vue";
import SchedulePanel from "./demand/SchedulePanel.vue";
import RunsPanel from "./demand/RunsPanel.vue";
import ConfigPanel from "./demand/ConfigPanel.vue";

const route = useRoute();
const router = useRouter();
const id = Number(route.params.id);
const d = ref(null);
const tab = ref(route.query.tab || "");
const busy = ref(false);
const err = ref("");
const loading = ref(true);
const reloadKey = ref(0);

const nUnmapped = computed(() => (d.value ? Math.max(0, (d.value.n_names || 0) - (d.value.n_mapped || 0)) : 0));

const suggest = computed(() =>
  d.value && d.value.suggested_frequency
    ? { frequency: d.value.suggested_frequency, run_time: d.value.suggested_time }
    : null
);

const tabs = computed(() => [
  { key: "runs", label: "运行记录" },
  { key: "mapping", label: "指标映射", num: nUnmapped.value || null },
  { key: "schedule", label: "调度" },
  { key: "config", label: "配置" },
]);

const statusMeta = computed(() => {
  if (!d.value) return {};
  if (d.value.status === "enabled") return { color: "green", text: "已启用" };
  if (d.value.schedule_confirmed && d.value.mapping_confirmed) return { color: "gray", text: "已停用" };
  return { color: "blue", text: "配置中" };
});

const cta = computed(() => {
  const v = d.value;
  if (!v || v.status === "enabled") return null;
  if (!v.mapping_confirmed || nUnmapped.value > 0) {
    if (tab.value === "mapping") return null;
    return { label: "去完成映射", action: () => setTab("mapping") };
  }
  if (!v.schedule_confirmed) {
    if (tab.value === "schedule") return null;
    return { label: "去配置调度", action: () => setTab("schedule") };
  }
  return null;
});

const showRun = computed(() => d.value && d.value.mapping_confirmed);

function setTab(t) {
  tab.value = t;
  router.replace({ query: { tab: t } });
}

async function toggleEnable() {
  err.value = "";
  busy.value = true;
  try {
    if (d.value.status === "enabled") await api.disable(id);
    else await api.enable(id);
    await load();
  } catch (e) {
    err.value = e.message;
  } finally {
    busy.value = false;
  }
}

async function run() {
  err.value = "";
  busy.value = true;
  try {
    const r = await api.run(id);
    router.push("/runs/" + r.run_id);
  } catch (e) {
    err.value = e.message;
    busy.value = false;
  }
}

function defaultTab() {
  const v = d.value;
  if (v.status === "enabled") return "runs";
  if (!v.mapping_confirmed || nUnmapped.value > 0) return "mapping";
  if (!v.schedule_confirmed) return "schedule";
  return "runs";
}

async function load() {
  err.value = "";
  try {
    d.value = await api.demand(id);
    reloadKey.value++;
    if (!route.query.tab && !tab.value) tab.value = defaultTab();
  } catch (e) {
    err.value = e.message || "加载失败";
  } finally {
    loading.value = false;
  }
}

async function remove() {
  try {
    await ElMessageBox.confirm("删除后不可恢复。确定删除该任务？", "删除任务", { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" });
  } catch {
    return;
  }
  busy.value = true;
  try {
    await api.deleteDemand(id);
    router.push("/demands");
  } catch (e) {
    err.value = e.message;
    busy.value = false;
  }
}
watch(() => route.query.tab, (t) => { if (t) tab.value = t; });
load();
</script>
