<template>
  <div>
    <template v-if="!open">
      <div style="padding: 14px 16px; display: flex; gap: 8px; border-bottom: 1px solid var(--border); flex-wrap: wrap">
        <el-input v-model="np.name" placeholder="模块名" style="width: 160px" />
        <el-button type="primary" @click="addProf">添加模块</el-button>
      </div>
      <el-table :data="profiles">
        <el-table-column label="模块名" min-width="160">
          <template #default="{ row }"><el-input v-model="row.name" size="small" /></template>
        </el-table-column>
        <el-table-column label="启用" width="70">
          <template #default="{ row }"><el-switch v-model="row.enabled" :active-value="1" :inactive-value="0" /></template>
        </el-table-column>
        <el-table-column width="230">
          <template #default="{ row }">
            <el-button size="small" @click="open = row">子分类</el-button>
            <el-button size="small" @click="saveProf(row)">保存</el-button>
            <el-button size="small" type="danger" text @click="delProf(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </template>
    <template v-else>
      <div style="padding: 14px 16px; display: flex; align-items: center; gap: 8px; border-bottom: 1px solid var(--border); flex-wrap: wrap">
        <el-button @click="open = null">返回</el-button>
        <span style="font-weight: 600; margin-right: auto">{{ open.name }} · 子分类</span>
        <el-input v-model="draft[open.id]" placeholder="子分类名" style="width: 200px" @keyup.enter="addFor(open)" />
        <el-button type="primary" @click="addFor(open)">添加子分类</el-button>
      </div>
      <el-table :data="catsOf(open.name)">
        <el-table-column prop="name" label="子分类" />
        <el-table-column width="80">
          <template #default="{ row }">
            <el-button size="small" type="danger" text @click="delCat(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <p v-if="!catsOf(open.name).length" class="muted" style="padding: 16px">无子分类</p>
    </template>
    <p v-if="err" style="color: var(--danger); font-size: 13px; padding: 8px 16px">{{ err }}</p>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { api } from "../api";

const profiles = ref([]);
const cats = ref([]);
const open = ref(null);
const np = reactive({ name: "" });
const draft = reactive({});
const err = ref("");

function catsOf(mod) {
  return cats.value.filter((c) => c.module === mod);
}

async function load() {
  profiles.value = await api.profiles(true);
  cats.value = await api.categories();
}

async function saveProf(row) {
  await api.putProfile(row.id, { name: row.name, enabled: row.enabled });
  ElMessage.success("已保存");
}

async function addProf() {
  err.value = "";
  if (!np.name.trim()) return;
  try {
    await api.createProfile({ name: np.name.trim() });
    np.name = "";
    await load();
  } catch (e) {
    err.value = e.message;
  }
}

async function delProf(row) {
  try {
    await ElMessageBox.confirm(`删除模块 ${row.name}？`, "确认", { type: "warning" });
    await api.deleteProfile(row.id);
    await load();
  } catch (e) {
    if (e !== "cancel") err.value = e.message;
  }
}

async function addFor(row) {
  const name = (draft[row.id] || "").trim();
  if (!name) return;
  await api.addCategory(row.name, name);
  draft[row.id] = "";
  cats.value = await api.categories();
}

async function delCat(row) {
  await api.deleteCategory(row.id);
  cats.value = await api.categories();
}

onMounted(load);
</script>
