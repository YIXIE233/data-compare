<template>
  <div>
    <el-form label-width="100px" label-position="left">
      <el-form-item label="需求名称">
        <el-input v-model="form.demand_name" @blur="fillPath" />
      </el-form-item>
      <el-form-item label="来源 CSV">
        <PathField v-model="form.source_path" @blur="checkSource" />
        <div v-if="srcState" style="font-size: 12px; margin-top: 4px" :style="{ color: srcState.ok ? 'var(--ok)' : 'var(--danger)' }">{{ srcState.msg }}</div>
      </el-form-item>
      <el-form-item label="通知">
        <el-checkbox v-model="form.notify" />
      </el-form-item>
      <el-form-item label="子分类">
        <CategoryField v-model="form.category" :module="modName" />
      </el-form-item>
      <el-form-item label="输出目录" class="out-dir">
        <div class="muted out-dir-path">{{ fullPath }}</div>
      </el-form-item>
    </el-form>
    <div style="display: flex; justify-content: flex-end">
      <el-button type="primary" :loading="busy" @click="save">保存</el-button>
    </div>
    <p v-if="err" style="color: var(--danger); font-size: 13px; margin: 8px 0 0">{{ err }}</p>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { api } from "../../api";
import PathField from "../../components/PathField.vue";
import CategoryField from "../../components/CategoryField.vue";

const props = defineProps({ demand: Object });
const emit = defineEmits(["updated"]);

const form = reactive({
  demand_name: props.demand.demand_name || "",
  source_path: props.demand.source_path || "",
  notify: !!props.demand.notify,
  category: (props.demand.paths || {}).category || "",
});
const srcState = ref(null);
const busy = ref(false);
const err = ref("");
const paths = computed(() => props.demand.paths || {});
const modName = computed(() => paths.value.module || "");
const fullPath = computed(() => {
  const rel = [paths.value.module, form.category, form.demand_name].map((x) => (x || "").trim()).filter(Boolean).join("\\");
  const root = String(paths.value.root || "").replace(/[\\/]+$/, "");
  if (root && rel) return root + "\\" + rel;
  return paths.value.demand_dir || rel || "—";
});

async function fillPath() {}

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
    await api.updateDemand(props.demand.id, {
      demand_name: form.demand_name,
      source_path: form.source_path,
      notify: form.notify ? 1 : 0,
      category: form.category,
    });
    ElMessage.success("已保存");
    emit("updated");
  } catch (e) {
    err.value = e.message;
  } finally {
    busy.value = false;
  }
}
</script>
