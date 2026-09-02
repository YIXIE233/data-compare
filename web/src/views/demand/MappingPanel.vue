<template>
  <div>
    <div class="card" style="padding: 12px 16px; margin-bottom: 12px; display: flex; align-items: center; gap: 14px">
      <div style="flex: 1">
        <div style="font-size: 13px">
          已映射 <b>{{ doneCount }}</b> / {{ rows.length }}
          <span v-if="reviewCount" style="color: var(--warn); margin-left: 10px">{{ reviewCount }} 个来源新指标</span>
        </div>
        <div class="progress" style="margin-top: 6px"><i :style="{ width: pct + '%' }" /></div>
        <div style="margin-top: 4px">
          <el-button text size="small" :loading="busy" @click="refresh">重新拉取来源</el-button>
        </div>
      </div>
      <el-button type="primary" :disabled="!dirty || conflicts.length > 0" :loading="busy" @click="save">保存映射</el-button>
    </div>
    <div style="display: flex; gap: 10px; margin-bottom: 12px; align-items: center">
      <div class="chips">
        <span v-for="c in chips" :key="c.key" class="chip" :class="{ active: chip === c.key }" @click="chip = c.key">
          {{ c.label }}<span class="num">{{ c.num }}</span>
        </span>
      </div>
      <template v-if="selected.length">
        <el-button size="small" @click="bulkConfirm">确认所选 {{ selected.length }}</el-button>
        <el-button size="small" @click="bulkClear">清空所选</el-button>
      </template>
      <el-input ref="searchEl" v-model="search" autofocus placeholder="搜索指标" clearable style="width: 220px; margin-left: auto" />
    </div>
    <div class="card" style="padding: 0">
      <el-table :data="filtered" size="small" @selection-change="selected = $event">
        <el-table-column type="selection" width="36" />
        <el-table-column label="来源指标名" min-width="220">
          <template #default="{ row }">
            {{ row.raw_name }}
            <Pill v-if="row.mapping_state === 'needs_review'" color="amber" text="新" style="margin-left: 6px" />
          </template>
        </el-table-column>
        <el-table-column label="映射到指标" min-width="260">
          <template #default="{ row }">
            <el-select v-model="row.code" filterable clearable placeholder="选择指标" style="width: 100%" @change="row.dirty = true">
              <el-option v-for="t in template" :key="t.code" :value="t.code" :label="t.name + '（' + t.code + '）'" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <Pill v-if="!row.code" color="red" text="未映射" />
            <Pill v-else color="green" text="已映射" />
          </template>
        </el-table-column>
        <template #empty><el-empty :image-size="60" description="来源还没有出现过指标" /></template>
      </el-table>
    </div>
    <div v-if="conflicts.length" class="card" style="border-color: var(--danger); margin-top: 12px">
      <div style="color: var(--danger); font-size: 13px">
        指标编码冲突：{{ conflicts.join("、") }} 被多个来源指标使用，一个目标只能映射一个来源。
      </div>
    </div>
    <p v-if="err" style="color: var(--danger); font-size: 13px">{{ err }}</p>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";
import { api } from "../../api";
import Pill from "../../components/Pill.vue";

const props = defineProps({ demand: Object });
const emit = defineEmits(["updated"]);
const router = useRouter();
const searchEl = ref(null);
const selected = ref([]);
const rows = ref([]);
const template = ref([]);
const version = ref(0);
const chip = ref("unmapped");
const search = ref("");
const busy = ref(false);
const err = ref("");

const filtered = computed(() => {
  let r = rows.value;
  if (chip.value === "unmapped") r = r.filter((x) => !x.code);
  if (chip.value === "mapped") r = r.filter((x) => x.code);
  if (search.value) r = r.filter((x) => x.raw_name.includes(search.value));
  return r;
});

const chips = computed(() => [
  { key: "all", label: "全部", num: rows.value.length },
  { key: "unmapped", label: "未映射", num: rows.value.filter((x) => !x.code).length },
  { key: "mapped", label: "已映射", num: rows.value.filter((x) => x.code).length },
]);

const doneCount = computed(() => rows.value.filter((x) => x.code).length);
const unmappedCount = computed(() => rows.value.filter((x) => !x.code).length);
const reviewCount = computed(() => rows.value.filter((x) => x.mapping_state === "needs_review").length);
const pct = computed(() => (rows.value.length ? Math.round((100 * doneCount.value) / rows.value.length) : 0));
const dirty = computed(() => rows.value.some((x) => x.dirty));
const conflicts = computed(() => {
  const seen = {};
  rows.value.forEach((x) => {
    if (x.code) seen[x.code] = (seen[x.code] || 0) + 1;
  });
  return Object.keys(seen).filter((k) => seen[k] > 1);
});

async function load() {
  const m = await api.mapping(props.demand.id);
  version.value = m.mapping_version;
  template.value = m.template;
  rows.value = m.rows.map((x) => {
    if (!x.code) {
      const hit = m.template.find((t) => t.name === x.raw_name);
      if (hit) return { ...x, code: hit.code, dirty: true };
    }
    return { ...x, dirty: false };
  });
  chip.value = rows.value.some((x) => !x.code) ? "unmapped" : "all";
}

async function save() {
  err.value = "";
  busy.value = true;
  try {
    const r = await api.putMapping(props.demand.id, {
      mapping_version: version.value,
      rows: rows.value.filter((x) => x.dirty).map((x) => ({ raw_name: x.raw_name, code: x.code || null })),
    });
    version.value = r.mapping_version;
    rows.value.forEach((x) => (x.dirty = false));
    emit("updated");
    if (!props.demand.mapping_confirmed && unmappedCount.value === 0) router.push({ query: { tab: "schedule" } });
  } catch (e) {
    if (e.status === 409) {
      err.value = "映射已被修改，已刷新";
      await load();
    } else {
      err.value = e.message;
    }
  } finally {
    busy.value = false;
  }
}

async function refresh() {
  busy.value = true;
  try {
    await api.refreshSource(props.demand.id);
    await load();
  } finally {
    busy.value = false;
  }
}

async function bulkConfirm() {
  if (!selected.value.length) return;
  busy.value = true;
  try {
    const r = await api.bulkConfirm(props.demand.id, {
      mapping_version: version.value,
      raw_names: selected.value.map((x) => x.raw_name),
    });
    version.value = r.mapping_version;
    await load();
    emit("updated");
  } catch (e) {
    if (e.status === 409) { err.value = "映射已被修改，已刷新"; await load(); }
    else err.value = e.message;
  } finally {
    busy.value = false;
  }
}

async function bulkClear() {
  if (!selected.value.length) return;
  busy.value = true;
  try {
    const r = await api.bulkClear(props.demand.id, {
      mapping_version: version.value,
      raw_names: selected.value.map((x) => x.raw_name),
    });
    version.value = r.mapping_version;
    await load();
    emit("updated");
  } catch (e) {
    if (e.status === 409) { err.value = "映射已被修改，已刷新"; await load(); }
    else err.value = e.message;
  } finally {
    busy.value = false;
  }
}

function onKey(e) {
  const tag = (e.target && e.target.tagName) || "";
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") {
    if (e.key === "Escape") e.target.blur();
    return;
  }
  if (e.key === "/") {
    e.preventDefault();
    const el = searchEl.value;
    if (el && el.focus) el.focus();
    else if (el && el.input) el.input.focus();
  }
  if (e.key === "Enter") bulkConfirm();
  if (e.key === "Delete" || e.key === "Backspace") bulkClear();
}

onMounted(() => window.addEventListener("keydown", onKey));
onUnmounted(() => window.removeEventListener("keydown", onKey));
load();
</script>
