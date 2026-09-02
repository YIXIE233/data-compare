<template>
  <div style="max-width: 640px">
    <div class="page-head">
      <div style="display: flex; align-items: center; gap: 12px">
        <el-button text circle aria-label="返回任务列表" @click="back"><el-icon><ArrowLeft /></el-icon></el-button>
        <div class="page-title">新任务</div>
      </div>
    </div>
    <el-form label-width="90px" label-position="left">
      <el-form-item label="需求名称" required>
        <el-input v-model="form.demand_name" @blur="fillPath" />
      </el-form-item>
      <el-form-item v-if="!lockedMod" label="模块" required>
        <el-select v-model="form.profile_id" style="width: 100%">
          <el-option v-for="p in profiles" :key="p.id" :label="p.name" :value="p.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="子分类">
        <CategoryField v-model="form.category" :module="modName" />
      </el-form-item>
      <el-form-item label="来源 CSV" required>
        <PathField v-model="form.source_path" @blur="checkSource" />
        <div v-if="srcState" style="font-size: 12px; margin-top: 4px" :style="{ color: srcState.ok ? 'var(--ok)' : 'var(--danger)' }">{{ srcState.msg }}</div>
      </el-form-item>
      <el-form-item label="输出目录" class="out-dir">
        <div v-if="destText" class="muted out-dir-path">{{ destText }}</div>
      </el-form-item>
    </el-form>
    <p v-if="err" class="err-text">{{ err }}</p>
    <div style="display: flex; justify-content: flex-end; gap: 8px; margin-left: 90px">
      <el-button @click="back">取消</el-button>
      <el-button type="primary" :loading="busy" :disabled="!form.demand_name || !form.profile_id || !form.source_path" @click="save">创建</el-button>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ArrowLeft } from "@element-plus/icons-vue";
import { api } from "../api";
import PathField from "../components/PathField.vue";
import CategoryField from "../components/CategoryField.vue";

const route = useRoute();
const router = useRouter();
const busy = ref(false);
const err = ref("");
const profiles = ref([]);
const form = reactive({ demand_name: "", profile_id: null, source_path: "", notify: true, category: "", rel: "", root: "" });
const modName = computed(() => profiles.value.find((x) => x.id === form.profile_id)?.name || "");
const lockedMod = computed(() => Boolean(route.query.module && form.profile_id));
const destText = computed(() => {
  if (!form.rel) return "";
  const root = String(form.root || "").replace(/[\\/]+$/, "");
  return root ? root + "\\" + form.rel : form.rel;
});
const srcState = ref(null);

onMounted(async () => {
  profiles.value = await api.profiles();
  const q = route.query.module;
  if (q) {
    const p = profiles.value.find((x) => x.name === q || String(x.id) === String(q));
    if (p) form.profile_id = p.id;
  }
  await fillPath();
});

function back() {
  router.push("/demands");
}

async function fillPath() {
  const p = profiles.value.find((x) => x.id === form.profile_id);
  const name = form.demand_name.trim();
  try {
    const r = await api.parsePath({ name, module: p?.name || "", category: form.category || undefined });
    form.root = r.root || "";
    if (!name) { form.rel = ""; return; }
    if (!form.category) form.category = r.category;
    form.rel = r.rel;
  } catch {
    form.rel = "";
  }
}
watch(() => form.profile_id, () => { form.category = ""; fillPath(); });

function payload() {
  return {
    demand_name: form.demand_name.trim(),
    module_profile_id: form.profile_id,
    source_path: form.source_path.trim(),
    notify: form.notify ? 1 : 0,
    category: form.category,
  };
}

async function checkSource() {
  const p = form.source_path.trim();
  if (!p) { srcState.value = null; return; }
  try {
    const r = await api.previewSource(p);
    srcState.value = { ok: true, msg: `${r.n_names} 个指标` };
  } catch (e) {
    srcState.value = { ok: false, msg: e.message || "文件不可读" };
  }
}

async function save() {
  err.value = "";
  busy.value = true;
  try {
    const r = await api.createDemand(payload());
    router.push(`/demands/${r.id}?tab=mapping`);
  } catch (e) {
    err.value = e.message;
  } finally {
    busy.value = false;
  }
}
</script>

<style scoped>
.err-text { color: var(--danger); font-size: 13px; margin: 8px 0 0; }
</style>
