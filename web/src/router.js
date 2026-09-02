import { createRouter, createWebHistory } from "vue-router";
import DemandList from "./views/DemandList.vue";
import DemandNew from "./views/DemandNew.vue";
import DemandView from "./views/DemandView.vue";
import RunView from "./views/RunView.vue";
import Settings from "./views/Settings.vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/demands", component: DemandList },
    { path: "/demands/new", component: DemandNew },
    { path: "/demands/:id", component: DemandView },
    { path: "/runs/:id", component: RunView },
    { path: "/config", redirect: "/settings?tab=notify" },
    { path: "/settings", component: Settings },
    { path: "/", redirect: "/demands" },
    { path: "/login", redirect: "/demands" },
    { path: "/demands/:id/mapping", redirect: (to) => `/demands/${to.params.id}?tab=mapping` },
    { path: "/demands/:id/schedule", redirect: (to) => `/demands/${to.params.id}?tab=schedule` },
  ],
});

export default router;
