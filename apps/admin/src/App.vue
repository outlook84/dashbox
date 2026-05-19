<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, ref, watch, provide } from "vue";
import { NConfigProvider, NDialogProvider, NMessageProvider, darkTheme, useOsTheme } from "naive-ui";
import type { GlobalThemeOverrides } from "naive-ui";
import { onUnauthorized, session } from "./api";
import { t } from "./i18n";
import type { SessionState } from "./types";

// ── Naive UI theme overrides ──────────────────────────────────────────
const lightOverrides: GlobalThemeOverrides = {
  common: {
    primaryColor:         "#ea580c",
    primaryColorHover:    "#c2410c",
    primaryColorPressed:  "#9a3412",
    primaryColorSuppl:    "#f97316",
  }
};

const darkOverrides: GlobalThemeOverrides = {
  common: {
    primaryColor:         "#f59e0b",
    primaryColorHover:    "#fbbf24",
    primaryColorPressed:  "#d97706",
    primaryColorSuppl:    "#fcd34d",
  }
};

// ── Theme state ───────────────────────────────────────────────────────
const THEME_KEY = "dashbox.admin.theme";
const osTheme = useOsTheme();

function readStoredTheme(): "light" | "dark" | null {
  try {
    const v = localStorage.getItem(THEME_KEY);
    if (v === "light" || v === "dark") return v;
  } catch { /* ignore */ }
  return null;
}

const manualTheme = ref<"light" | "dark" | null>(readStoredTheme());

const isDark = computed(() =>
  manualTheme.value !== null
    ? manualTheme.value === "dark"
    : osTheme.value === "dark"
);

function toggleTheme() {
  manualTheme.value = isDark.value ? "light" : "dark";
  try { localStorage.setItem(THEME_KEY, manualTheme.value); } catch { /* ignore */ }
}

// Sync data-theme attribute on <html> so CSS variables react immediately
watch(isDark, (dark) => {
  document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
}, { immediate: true });

const naiveTheme = computed(() => isDark.value ? darkTheme : null);
const naiveOverrides = computed(() => isDark.value ? darkOverrides : lightOverrides);

provide("isDark", isDark);
provide("toggleTheme", toggleTheme);

type PageKey = "status" | "config" | "account";

const PAGE_STORAGE_KEY = "dashbox.admin.page";
const AdminShell = defineAsyncComponent(() => import("./components/AdminShell.vue"));
const LoginPage = defineAsyncComponent(() => import("./pages/LoginPage.vue"));
const ConfigPage = defineAsyncComponent(() => import("./pages/ConfigPage.vue"));
const StatusPage = defineAsyncComponent(() => import("./pages/StatusPage.vue"));
const AccountPage = defineAsyncComponent(() => import("./pages/AccountPage.vue"));

function normalizePage(value: string | null): PageKey | "" {
  if (value === "status" || value === "config" || value === "account") return value;
  return "";
}

function initialPage(): PageKey {
  try {
    return normalizePage(localStorage.getItem(PAGE_STORAGE_KEY)) || "status";
  } catch {
    return "status";
  }
}

const page = ref<PageKey>(initialPage());
const sessionState = ref<SessionState | null>(null);
const loading = ref(true);

const authenticated = computed(() => sessionState.value?.authenticated === true);

async function refreshSession() {
  loading.value = true;
  try {
    sessionState.value = await session();
  } finally {
    loading.value = false;
  }
}

function handleAuthenticated(next: SessionState) {
  sessionState.value = next;
}

function handleUnauthorized() {
  sessionState.value = { authenticated: false, setup_required: false };
}

onUnauthorized(handleUnauthorized);
onMounted(refreshSession);

watch(page, (next) => {
  try {
    localStorage.setItem(PAGE_STORAGE_KEY, next);
  } catch {
    // Ignore storage failures so navigation still works in restricted browsers.
  }
});
</script>

<template>
  <NConfigProvider :theme="naiveTheme" :theme-overrides="naiveOverrides">
    <NDialogProvider>
      <NMessageProvider>
        <div v-if="loading" class="boot-screen">{{ t("app.loading") }}</div>
        <LoginPage
          v-else-if="!authenticated"
          :setup-required="sessionState?.setup_required === true"
          @authenticated="handleAuthenticated"
        />
        <AdminShell v-else v-model:page="page" @logout="handleUnauthorized">
          <StatusPage v-if="page === 'status'" />
          <ConfigPage v-else-if="page === 'config'" />
          <AccountPage v-else />
        </AdminShell>
      </NMessageProvider>
    </NDialogProvider>
  </NConfigProvider>
</template>
