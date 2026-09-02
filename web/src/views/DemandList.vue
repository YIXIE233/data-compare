<template>
  <div>
    <div class="page-head">
      <div class="page-title">任务<span class="count">{{ total }}</span></div>
      <el-button type="primary" @click="goNew">
        <el-icon style="margin-right: 4px"><Plus /></el-icon>新任务
      </el-button>
    </div>

    <div>
      <div class="chips" style="margin-bottom: 14px">
        <span
          v-for="c in chips"
          :key="c.key"
          class="chip"
          :class="{ active: chip === c.key }"
          @click="chip = c.key"
        >{{ c.label }}<span v-if="c.num != null" class="num">{{ c.num }}</span></span>
        <el-input v-model="q" placeholder="搜索需求" clearable style="width: 200px; margin-left: auto" />
      </div>

      <div class="card" style="padding: 0">
        <el-table :data="filtered" size="small" :show-header="filtered.length > 0" @row-click="(r) => $router.push('/demands/' + r.id)" style="cursor: pointer">
          <el-table-column label="需求" min-width="240">
            <template #default="{ row }">
              <div class="name" :title="row.demand_name">{{ row.demand_name }}</div>
            </template>
          </el-table-column>
          <el-table-column label="模块" width="110">
            <template #default="{ row }"><span class="muted">{{ row.module_name || "—" }}</span></template>
          </el-table-column>
          <el-table-column v-if="chip === 'setup'" label="映射" width="100">
            <template #default="{ row }">{{ row.mapping_confirmed ? "已完成" : "未完成" }}</template>
          </el-table-column>
          <el-table-column v-if="chip === 'setup'" label="调度" width="100">
            <template #default="{ row }">{{ row.schedule_confirmed ? "已完成" : "未完成" }}</template>
          </el-table-column>
          <el-table-column v-if="chip !== 'setup'" label="上次结果" width="160">
            <template #default="{ row }">
              <template v-if="row.last_run_id">
                <Pill v-bind="resultMeta(row.last_run_status, row.last_check_result)" />
                <span class="muted" style="font-size: 12px; margin-left: 6px">{{ shortTime(row.last_run_at) }}</span>
              </template>
              <span v-else class="muted">尚未运行</span>
            </template>
          </el-table-column>
          <el-table-column v-if="chip !== 'setup'" label="下次运行" width="140">
            <template #default="{ row }">
              <span :class="{ muted: !row.next_run_at }">{{ shortTime(row.next_run_at) || "—" }}</span>
            </template>
          </el-table-column>
          <el-table-column width="72" align="right">
            <template #default="{ row }">
              <el-button v-if="row.mapping_confirmed" text type="primary" size="small" @click.stop="runNow(row)">运行</el-button>
            </template>
          </el-table-column>
          <template #empty>
            <el-empty :image-size="80" :description="chip === 'enabled' ? '还没有已启用的任务' : '还没有任务，点右上角新建第一个'" />
          </template>
        </el-table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { Plus } from "@element-plus/icons-vue";
import { api } from "../api";
import Pill from "../components/Pill.vue";
import { resultMeta, shortTime } from "../fmt";

const router = useRouter();
const rows = ref([]);
const chip = ref("enabled");
const q = ref("");
const total = computed(() => rows.value.length);
const filtered = computed(() => {
  let all = rows.value;
  if (chip.value === "enabled") all = all.filter((r) => r.status === "enabled");
  if (chip.value === "setup") all = all.filter((r) => r.status !== "enabled");
  if (q.value.trim()) all = all.filter((r) => (r.demand_name || "").includes(q.value.trim()));
  return all;
});

const chips = computed(() => {
  const n = (f) => rows.value.filter(f).length;
  return [
    { key: "enabled", label: "已启用", num: n((r) => r.status === "enabled") },
    { key: "setup", label: "配置中", num: n((r) => r.status !== "enabled") },
    { key: "all", label: "全部" },
  ];
});

function goNew() {
  router.push("/demands/new");
}

async function runNow(row) {
  const r = await api.run(row.id);
  router.push("/runs/" + r.run_id);
}

onMounted(async () => {
  rows.value = await api.demands();
});
</script>

<style scoped>
.name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 600; max-width: 420px; }
</style>
