<template>
  <div class="shell">
    <header class="sbar">
      <div class="brand"><span class="logo">C</span>比对演示</div>
      <nav>
        <router-link to="/demands" class="nav-item" aria-label="任务" :class="{ on: navOn('demands') }">
          <el-icon><List /></el-icon>任务
        </router-link>
        <router-link to="/settings" class="nav-item" aria-label="系统设置" :class="{ on: route.path === '/settings' }">
          <el-icon><Setting /></el-icon>设置
        </router-link>
      </nav>
    </header>
    <main class="main"><router-view /></main>
  </div>
</template>

<script setup>
import { useRoute } from "vue-router";
import { List, Setting } from "@element-plus/icons-vue";

const route = useRoute();

function navOn(key) {
  return key === "demands" && (route.path.startsWith("/demands") || route.path.startsWith("/runs/"));
}
</script>
