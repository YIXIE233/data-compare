<template>
  <div>
    <div class="page-head">
      <div class="page-title">系统设置</div>
    </div>
    <div class="tabs">
      <span v-for="t in tabs" :key="t.key" class="tab" :class="{ active: tab === t.key }" @click="tab = t.key">{{ t.label }}</span>
    </div>
    <div v-if="tab === 'storage'" class="card">
      <el-form label-width="140px" label-position="left">
        <el-form-item label="本机数据目录"><PathField v-model="cfg.local_root" kind="dir" /></el-form-item>
      </el-form>
      <div style="display: flex; justify-content: flex-end">
        <el-button type="primary" @click="saveStorage().catch(() => {})">保存</el-button>
      </div>
    </div>
    <div v-else-if="tab === 'notify'" class="card">
      <el-form label-width="90px" label-position="left">
        <el-form-item label="Webhook"><el-input v-model="cfg.webhook_url" /></el-form-item>
      </el-form>
      <div style="display: flex; justify-content: flex-end">
        <el-button type="primary" @click="saveNotify().catch(() => {})">保存</el-button>
      </div>
    </div>
    <div v-else-if="tab === 'modules'" class="card" style="padding: 0; overflow: hidden">
      <ProfilesPanel />
    </div>
    <p v-if="err" style="color: var(--danger); font-size: 13px; margin-top: 10px">{{ err }}</p>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { ElMessage } from "element-plus";
import { api } from "../api";
import ProfilesPanel from "./ProfilesPanel.vue";
import PathField from "../components/PathField.vue";

const route = useRoute();
const tabs = [
  { key: "storage", label: "存储路径" },
  { key: "notify", label: "通知" },
  { key: "modules", label: "模块" },
];
const tab = ref(route.query.tab || "storage");
const cfg = reactive({ local_root: "", webhook_url: "" });
const err = ref("");

watch(() => route.query.tab, (t) => { if (t) tab.value = t; });

async function load() {
  const s = await api.settings();
  Object.assign(cfg, s);
}

async function saveStorage() {
  err.value = "";
  try {
    await api.putSettings({ local_root: cfg.local_root });
    ElMessage.success("已保存");
  } catch (e) {
    err.value = e.message;
    throw e;
  }
}

async function saveNotify() {
  err.value = "";
  try {
    await api.putSettings({ webhook_url: cfg.webhook_url });
    ElMessage.success("已保存");
  } catch (e) {
    err.value = e.message;
    throw e;
  }
}

onMounted(load);
</script>
