<template>
  <el-input :model-value="modelValue || ''" :placeholder="placeholder" @update:model-value="$emit('update:modelValue', $event)" @blur="$emit('blur')">
    <template #append>
      <el-button :loading="busy" @click="go">浏览</el-button>
    </template>
  </el-input>
</template>

<script setup>
import { ref } from "vue";
import { api } from "../api";

const props = defineProps({
  modelValue: { type: String, default: "" },
  kind: { type: String, default: "file" },
  placeholder: { type: String, default: "" },
});
const emit = defineEmits(["update:modelValue", "blur"]);
const busy = ref(false);

async function go() {
  busy.value = true;
  try {
    const r = props.kind === "dir" ? await api.pickDir(props.modelValue) : await api.pickFile(props.modelValue);
    if (r?.path) {
      emit("update:modelValue", r.path);
      emit("blur");
    }
  } finally {
    busy.value = false;
  }
}
</script>
