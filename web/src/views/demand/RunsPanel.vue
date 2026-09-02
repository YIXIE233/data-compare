<template>
  <div class="card" style="padding: 0">
    <el-table :data="rows" size="small" @row-click="(r) => $router.push('/runs/' + r.id)" style="cursor: pointer">
      <el-table-column label="时间" width="170">
        <template #default="{ row }">{{ shortTime(row.started_at) }}</template>
      </el-table-column>
      <el-table-column label="触发" width="80">
        <template #default="{ row }">{{ row.trigger === "manual" ? "手动" : "定时" }}</template>
      </el-table-column>
      <el-table-column label="结果" width="120">
        <template #default="{ row }">
          <Pill v-bind="resultMeta(row.execution_status, row.check_result)" />
        </template>
      </el-table-column>
      <el-table-column label="周期" min-width="150">
        <template #default="{ row }">
          <span class="muted" style="font-size: 13px">{{ periods(row) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="差异" width="70" align="right">
        <template #default="{ row }">
          <span :style="{ color: row.n_diff ? 'var(--danger)' : 'var(--text-3)' }">{{ row.n_diff ?? "—" }}</span>
        </template>
      </el-table-column>
      <el-table-column label="耗时" width="80" align="right">
        <template #default="{ row }">
          <span class="muted" style="font-size: 13px">{{ duration(row) }}</span>
        </template>
      </el-table-column>
      <template #empty><el-empty :image-size="60" description="还没有运行记录" /></template>
    </el-table>
  </div>
</template>

<script setup>
import { ref } from "vue";
import { api } from "../../api";
import Pill from "../../components/Pill.vue";
import { resultMeta, shortTime } from "../../fmt";

const props = defineProps({ demandId: Number });
const rows = ref([]);

function periods(r) {
  try {
    const p = JSON.parse(r.periods_json || "[]");
    if (!p.length) return "—";
    return p.length > 2 ? `${p[0]} ~ ${p[p.length - 1]}（${p.length} 期）` : p.join("、");
  } catch {
    return "—";
  }
}

function duration(r) {
  if (!r.started_at || !r.finished_at) return "—";
  const s = (new Date(r.finished_at) - new Date(r.started_at)) / 1000;
  return s < 60 ? `${s.toFixed(1)}s` : `${(s / 60).toFixed(1)}m`;
}

api.demandRuns(props.demandId).then((r) => (rows.value = r));
</script>
