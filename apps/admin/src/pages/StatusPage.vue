<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { NAlert, NButton, NCard, NDataTable, NDescriptions, NDescriptionsItem, NIcon, NSpace, useMessage } from "naive-ui";
import type { DataTableColumns } from "naive-ui";
import { Download } from "@lucide/vue";
import { cookieStatus, readConfig, reloadCookies, status as readStatus } from "../api";
import { t } from "../i18n";
import { displayLabel } from "../labels";
import type { AdminStatus, ConfigResponse, CookieStatus, SubscriptionSummary } from "../types";

const message = useMessage();
const props = defineProps<{ adminStatus: AdminStatus | null }>();
const emit = defineEmits<{
  "status-loaded": [value: AdminStatus];
}>();
const loading = ref(false);
const cookiesLoading = ref(false);
const localStatus = ref<AdminStatus | null>(props.adminStatus);
const configResponse = ref<ConfigResponse | null>(null);
const cookies = ref<CookieStatus | null>(null);
const narrowDescriptions = ref(false);
const subs = ref<SubscriptionSummary[]>([]);

const envEntries = computed(() => Object.entries(configResponse.value?.env_overrides || {}));
const publicBaseUrl = computed(() => String(configResponse.value?.env_overrides.public_base_url || "").trim());
const statusDescriptionColumns = computed(() => (narrowDescriptions.value ? 1 : 3));
const cookieDescriptionColumns = computed(() => (narrowDescriptions.value ? 1 : 4));
const cookieSource = computed(() => cookies.value?.source || t("common.notSet"));
const cookieLoadedAt = computed(() => formatUnixTime(cookies.value?.loaded_at));
const cookieCount = computed(() => cookies.value?.cookie_count ?? 0);
const repoZipUrl = computed(() => new URL("/repo.zip", window.location.href).toString());

function isObjectRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function formatUnixTime(value: number | null | undefined) {
  if (typeof value !== "number" || !Number.isFinite(value)) return t("cookies.notLoaded");
  return new Date(value * 1000).toLocaleString();
}

function updateNarrowDescriptions() {
  narrowDescriptions.value = window.matchMedia("(max-width: 760px)").matches;
}

const subscriptionColumns = computed<DataTableColumns<SubscriptionSummary>>(() => [
  { title: t("subscriptions.id"), key: "id" },
  {
    title: t("subscriptions.type"),
    key: "type",
    render(row) {
      return displayLabel("subscriptionType", row.type);
    }
  },
  {
    title: t("subscriptions.auth"),
    key: "auth_mode",
    render(row) {
      return displayLabel("authMode", row.auth_mode);
    }
  },
  {
    title: t("subscriptions.hash"),
    key: "access_code_hash_set",
    render(row) {
      return row.access_code_hash_set ? t("common.hashSet") : t("common.hashUnset");
    }
  },
  {
    title: t("subscriptions.entry"),
    key: "url",
    render(row) {
      return subscriptionEntry(row);
    }
  }
]);

function fillSubscriptions(data: ConfigResponse) {
  const items = Array.isArray(data.config.subs) ? data.config.subs : [];
  subs.value = items.filter(isObjectRecord).map((item) => ({
    id: String(item.id || ""),
    type: String(item.type || ""),
    auth_mode: String(item.auth_mode || ""),
    access_code_hash_set: Boolean(item.access_code_hash_set)
  }));
}

function runtimeOverrideLabel(key: string) {
  return displayLabel("configField", key) || key;
}

function runtimeOverrideValue(key: string, value: unknown) {
  if (value === "" || value === null || value === undefined) return t("common.empty");
  if (key === "image_proxy_mode") return displayLabel("imageProxyMode", value);
  return String(value);
}

function subscriptionEntry(row: SubscriptionSummary) {
  const baseUrl = publicBaseUrl.value.replace(/\/+$/, "");
  if (row.type === "tvbox") {
    const path = `/sub/${encodeURIComponent(row.id)}`;
    return baseUrl ? `${baseUrl}${path}` : path;
  }
  if (row.type === "kodi") return baseUrl;
  return "";
}

async function load() {
  loading.value = true;
  try {
    const [statusData, configData, cookieData] = await Promise.all([
      readStatus(),
      readConfig(),
      cookieStatus()
    ]);
    localStatus.value = statusData;
    emit("status-loaded", statusData);
    configResponse.value = configData;
    cookies.value = cookieData;
    fillSubscriptions(configData);
  } catch (error) {
    message.error(error instanceof Error ? error.message : t("status.readFailed"));
  } finally {
    loading.value = false;
  }
}

async function reload(loadCookies: boolean) {
  cookiesLoading.value = true;
  try {
    cookies.value = await reloadCookies(loadCookies);
    message.success(loadCookies ? t("cookies.loaded") : t("cookies.cleared"));
  } catch (error) {
    message.error(error instanceof Error ? error.message : t("cookies.failed"));
  } finally {
    cookiesLoading.value = false;
  }
}

onMounted(() => {
  updateNarrowDescriptions();
  window.addEventListener("resize", updateNarrowDescriptions);
  load();
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", updateNarrowDescriptions);
});
</script>

<template>
  <div class="page-stack">
    <div class="page-heading page-heading-actions-only">
      <NSpace>
        <NButton tag="a" :href="repoZipUrl" download>
          <template #icon>
            <NIcon>
              <Download />
            </NIcon>
          </template>
          {{ t("status.downloadRepoZip") }}
        </NButton>
        <NButton :loading="loading" @click="load">{{ t("common.refresh") }}</NButton>
      </NSpace>
    </div>

    <NCard size="small" :title="t('status.service')">
      <NDescriptions size="small" :column="statusDescriptionColumns" bordered>
        <NDescriptionsItem :label="t('status.version')">v{{ localStatus?.version || "0.1.0" }}</NDescriptionsItem>
        <NDescriptionsItem :label="t('config.configFile')">{{ localStatus?.config_path || t("common.notSet") }}</NDescriptionsItem>
        <NDescriptionsItem :label="t('status.configWritable')">
          {{ localStatus?.config_writable ? t("common.writable") : t("common.readonly") }}
        </NDescriptionsItem>
        <NDescriptionsItem v-for="[key, value] in envEntries" :key="key" :label="runtimeOverrideLabel(key)">
          {{ runtimeOverrideValue(key, value) }}
        </NDescriptionsItem>
      </NDescriptions>
    </NCard>

    <NCard size="small" :title="t('cookies.title')">
      <template #header-extra>
        <NSpace>
          <NButton size="small" :loading="cookiesLoading" @click="reload(true)">{{ t("common.load") }}</NButton>
          <NButton size="small" :loading="cookiesLoading" @click="reload(false)">{{ t("cookies.clearCache") }}</NButton>
        </NSpace>
      </template>
      <div class="cookie-status">
        <NDescriptions size="small" :column="cookieDescriptionColumns" bordered>
          <NDescriptionsItem :label="t('cookies.source')">{{ cookieSource }}</NDescriptionsItem>
          <NDescriptionsItem :label="t('cookies.loadState')">
            {{ cookies?.loaded ? t("cookies.cacheLoaded") : t("cookies.cacheUnloaded") }}
          </NDescriptionsItem>
          <NDescriptionsItem :label="t('cookies.cookieCount')">{{ cookieCount }}</NDescriptionsItem>
          <NDescriptionsItem :label="t('cookies.loadedAt')">{{ cookieLoadedAt }}</NDescriptionsItem>
        </NDescriptions>
        <NAlert v-if="cookies?.last_error" type="error" :title="t('cookies.lastError')">
          {{ cookies.last_error }}
        </NAlert>
      </div>
    </NCard>

    <NCard size="small" :title="t('subscriptions.title')">
      <NDataTable :columns="subscriptionColumns" :data="subs" :bordered="false" />
    </NCard>
  </div>
</template>
