<template>
  <el-select
    :model-value="modelValue"
    filterable
    allow-create
    default-first-option
    clearable
    :disabled="!module"
    placeholder=""
    style="width: 100%"
    @update:model-value="onChange"
  >
    <el-option v-for="n in names" :key="n" :label="n" :value="n" />
  </el-select>
</template>

<script setup>
import { ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { api } from "../api";

const props = defineProps({ modelValue: String, module: String });
const emit = defineEmits(["update:modelValue"]);
const names = ref([]);

async function load() {
  if (!props.module) {
    names.value = [];
    return;
  }
  names.value = (await api.categories(props.module)).map((r) => r.name);
}

watch(() => props.module, load, { immediate: true });

async function onChange(v) {
  const s = (v || "").trim();
  emit("update:modelValue", s);
  if (!s || !props.module || names.value.includes(s)) return;
  try {
    await api.addCategory(props.module, s);
    names.value = [...names.value, s].sort((a, b) => a.localeCompare(b, "zh"));
  } catch (e) {
    ElMessage.error(e.message || "子分类无效");
    emit("update:modelValue", "");
  }
}
</script>
