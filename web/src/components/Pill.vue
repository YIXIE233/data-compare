<template>
  <span class="pill" :class="color">{{ text }}<slot /></span>
</template>

<script setup>
defineProps({ color: { type: String, default: "gray" }, text: { type: String, default: "" } });
</script>
