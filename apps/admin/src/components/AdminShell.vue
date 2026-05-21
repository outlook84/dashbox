<script setup lang="ts">
import { computed, inject } from "vue";
import type { Ref } from "vue";
import { NButton, NLayout, NLayoutContent, NLayoutHeader, NSelect, NSpace, NTooltip, useMessage } from "naive-ui";
import { ExternalLink, Moon, Sun, TvMinimalPlay } from "@lucide/vue";
import { logout } from "../api";
import { locale, localeOptions, setLocale, t, type AdminLocale } from "../i18n";
import type { AdminStatus } from "../types";

const isDark = inject<Ref<boolean>>("isDark");
const toggleTheme = inject<() => void>("toggleTheme");

const props = defineProps<{ page: string; adminStatus: AdminStatus | null }>();
const emit = defineEmits<{
  "update:page": [value: string];
  logout: [];
}>();

const message = useMessage();

const navItems = computed(() => [
  { label: t("nav.status"), key: "status" },
  { label: t("nav.config"), key: "config" },
  { label: t("nav.account"), key: "account" }
]);

const selected = computed({
  get: () => props.page,
  set: (value: string) => emit("update:page", value)
});
const projectUrl = computed(() => props.adminStatus?.project_url.trim() || "");

async function doLogout() {
  await logout();
  message.success(t("session.loggedOut"));
  emit("logout");
}

function changeLocale(value: string) {
  setLocale(value as AdminLocale);
}
</script>

<template>
  <NLayout class="admin-layout">
    <NLayoutHeader bordered class="topbar">
      <div class="brand">
        <span class="brand-mark" aria-hidden="true">
          <TvMinimalPlay :size="20" :stroke-width="2.2" />
        </span>
        <div class="brand-title">Dashbox</div>
      </div>
      <nav class="topbar-tabs" :aria-label="t('app.title')">
        <button
          v-for="item in navItems"
          :key="item.key"
          class="topbar-tab"
          :class="{ 'topbar-tab-active': selected === item.key }"
          type="button"
          @click="selected = item.key"
        >
          {{ item.label }}
        </button>
      </nav>
      <div class="topbar-actions">
        <NTooltip v-if="projectUrl" trigger="hover">
          <template #trigger>
          <NButton
            class="topbar-icon-button"
            text
            tag="a"
            :href="projectUrl"
            target="_blank"
            rel="noreferrer"
            size="small"
            :aria-label="t('app.github')"
          >
            <template #icon>
              <ExternalLink :size="16" />
            </template>
          </NButton>
          </template>
          {{ t("app.github") }}
        </NTooltip>
        <NTooltip trigger="hover">
          <template #trigger>
          <NButton
            class="topbar-icon-button"
            text
            size="small"
            :aria-label="isDark ? t('theme.switchLight') : t('theme.switchDark')"
            @click="toggleTheme"
          >
            <template #icon>
              <Sun v-if="isDark" :size="16" />
              <Moon v-else :size="16" />
            </template>
          </NButton>
          </template>
          {{ isDark ? t("theme.switchLight") : t("theme.switchDark") }}
        </NTooltip>
          <NSelect
          :value="locale"
          :options="localeOptions"
          size="small"
          class="locale-select"
          :aria-label="t('common.language')"
          @update:value="changeLocale"
        />
        <NButton size="small" @click="doLogout">{{ t("common.logout") }}</NButton>
      </div>
    </NLayoutHeader>
    <NLayoutContent class="content">
      <slot />
    </NLayoutContent>
  </NLayout>
</template>
