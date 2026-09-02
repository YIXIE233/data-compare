<template>
  <div v-if="run">
    <div class="page-head">
      <div style="display: flex; align-items: center; gap: 12px">
        <el-button text circle aria-label="返回运行记录" @click="$router.push('/demands/' + run.demand_id + '?tab=runs')"><el-icon><ArrowLeft /></el-icon></el-button>
        <div>
          <div class="page-title">{{ demandName || ('运行 #' + run.id) }}</div>
          <div class="muted" style="font-size: 12px">运行 #{{ run.id }}</div>
        </div>
      </div>
      <div style="display:flex;gap:8px">
        <el-button v-if="run.execution_status === 'FAILED'" type="primary" @click="retry">重试</el-button>
        <el-button v-if="run.n_diff > 0" @click="downloadXlsx(run.id)">
          <el-icon style="margin-right: 4px"><Download /></el-icon>下载差异明细
        </el-button>
      </div>
    </div>
    <div class="banner" :class="meta.color">
      <div class="t">{{ meta.text }}</div>
      <div class="s">{{ summary }}</div>
    </div>

    <div v-if="run.execution_status === 'FAILED'" class="card" style="border-color: var(--danger); margin-bottom: 14px">
      <div style="font-weight: 600; color: var(--danger); margin-bottom: 4px">失败于 {{ stepText(run.failed_step) }}</div>
      <div class="muted" style="font-size: 13px; word-break: break-all">{{ run.error_message || run.error_type }}</div>
    </div>

    <div v-if="unmapped.length" class="card" style="border-color: var(--warn); margin-bottom: 14px">
      <div style="font-weight: 600; color: var(--warn); margin-bottom: 6px">{{ unmapped.length }} 个来源指标未映射，本次未纳入比对</div>
      <div style="font-size: 13px; display: flex; flex-wrap: wrap; gap: 6px">
        <Pill v-for="u in unmapped" :key="u" color="amber" :text="u" />
      </div>
      <el-button size="small" style="margin-top: 6px" @click="$router.push('/demands/' + run.demand_id + '?tab=mapping')">去改映射</el-button>
    </div>

    <div class="meta-grid" style="margin-bottom: 14px">
      <div class="meta"><span>开始时间</span><b>{{ shortTime(run.started_at) }}</b></div>
      <div class="meta"><span>耗时</span><b>{{ duration }}</b></div>
      <div class="meta"><span>数据周期</span><b>{{ periods }}</b></div>
      <div class="meta"><span>拉取行数</span><b>{{ run.n_obs ?? "—" }}</b></div>
      <div class="meta"><span>参与比对</span><b>{{ run.n_mapped ?? "—" }}</b></div>
      <div class="meta"><span>差异条数</span><b :style="{ color: run.n_diff ? 'var(--danger)' : 'inherit' }">{{ run.n_diff ?? "—" }}</b></div>
      <div class="meta"><span>投递</span><b>{{ deliveryText }}</b></div>
    </div>
    <div v-if="diffs.length" class="card" style="padding: 0">
      <div style="padding: 14px 16px 0; font-weight: 600">差异明细</div>
      <el-table :data="diffs" size="small">
        <el-table-column prop="period" label="期间" width="110" />
        <el-table-column label="指标" min-width="200">
          <template #default="{ row }">
            {{ row.name }}<span class="muted" style="font-size: 12px; margin-left: 6px">{{ row.code }}</span>
          </template>
        </el-table-column>
        <el-table-column label="类型" width="110">
          <template #default="{ row }">
            <Pill :color="row.diff_type === '数值不同' ? 'red' : row.diff_type === '源有库无' ? 'amber' : 'blue'" :text="row.diff_type" />
          </template>
        </el-table-column>
        <el-table-column prop="src_value" label="来源值" width="130" align="right" />
        <el-table-column prop="ref_value" label="参考值" width="130" align="right" />
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { computed, onUnmounted, ref } from "vue";
import { useRoute } from "vue-router";
import { ArrowLeft, Download } from "@element-plus/icons-vue";
import { api, downloadXlsx } from "../api";
import { resultMeta, shortTime } from "../fmt";
import Pill from "../components/Pill.vue";

const route = useRoute();
const id = Number(route.params.id);
const run = ref(null);
const diffs = ref([]);
const demandName = ref("");
let timer = null;

const meta = computed(() => (run.value ? resultMeta(run.value.execution_status, run.value.check_result) : {}));

const summary = computed(() => {
  const r = run.value;
  if (!r) return "";
  if (r.execution_status === "RUNNING") return "正在拉取并比对数据…";
  if (r.execution_status === "FAILED") return stepText(r.failed_step) + "失败";
  if (r.check_result === "CLEAN") return "来源与参考数据完全一致";
  if (r.check_result === "DIFF_FOUND") return `发现 ${r.n_diff} 条差异`;
  if (r.check_result === "INCOMPLETE") return "部分指标未能完成比对";
  if (r.check_result === "NO_NEW_DATA") return "来源暂无新的数据周期";
  return "";
});

const periods = computed(() => {
  try {
    const p = JSON.parse(run.value.periods_json || "[]");
    if (!p.length) return "—";
    return p.length > 2 ? `${p[0]} ~ ${p[p.length - 1]}（${p.length} 期）` : p.join("、");
  } catch {
    return "—";
  }
});

const unmapped = computed(() => {
  try {
    return JSON.parse(run.value.unmapped_json || "[]");
  } catch {
    return [];
  }
});

const duration = computed(() => {
  const r = run.value;
  if (!r.started_at || !r.finished_at) return "—";
  const s = (new Date(r.finished_at) - new Date(r.started_at)) / 1000;
  return s < 60 ? `${s.toFixed(1)} 秒` : `${(s / 60).toFixed(1)} 分钟`;
});

const deliveryText = computed(() => {
  const m = { WRITTEN: "已写入", WRITE_FAILED: "写入失败", NONE: "无文件", LOCAL_WRITTEN: "已写入", SHARED_COPIED: "已写入", SHARED_FAILED: "写入失败" };
  return m[run.value && run.value.delivery_status] || (run.value && run.value.delivery_status) || "—";
});
function stepText(s) {
  return { pull: "拉取来源", validate: "校验数据", query: "查询库内数据", compare: "比对", artifact: "生成结果" }[s] || (s || "");
}

async function load() {
  run.value = await api.getRun(id);
  if (run.value.execution_status === "RUNNING") {
    timer = setTimeout(load, 2000);
    return;
  }
  diffs.value = await api.diffs(id);
  if (!demandName.value) {
    try {
      demandName.value = (await api.demand(run.value.demand_id)).demand_name;
    } catch {}
  }
}

async function retry() {
  await api.retryRun(run.value.id);
  load();
}

onUnmounted(() => clearTimeout(timer));
load();
</script>
