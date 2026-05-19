<script setup lang="ts">
import { defineAsyncComponent, ref } from "vue";
import { NButton, NCard, NForm, NFormItem, NInput, NSelect, NSpace, useMessage } from "naive-ui";
import { TvMinimalPlay } from "@lucide/vue";
import { login, setup, session } from "../api";
import { locale, localeOptions, setLocale, t, type AdminLocale } from "../i18n";
import type { SessionState } from "../types";

const FieldLabel = defineAsyncComponent(() => import("../components/FieldLabel.vue"));

const props = defineProps<{ setupRequired: boolean }>();
const emit = defineEmits<{ authenticated: [value: SessionState] }>();

const message = useMessage();
const loading = ref(false);
const setupCode = ref("");
const accessCode = ref("");
const confirmAccessCode = ref("");

async function submit() {
  if (props.setupRequired && accessCode.value !== confirmAccessCode.value) {
    message.error(t("login.mismatch"));
    return;
  }
  loading.value = true;
  try {
    if (props.setupRequired) {
      await setup(setupCode.value, accessCode.value);
    } else {
      await login(accessCode.value);
    }
    emit("authenticated", await session());
  } catch (error) {
    message.error(error instanceof Error ? error.message : t("login.failed"));
  } finally {
    loading.value = false;
  }
}

function changeLocale(value: string) {
  setLocale(value as AdminLocale);
}
</script>

<template>
  <div class="login-screen">
    <NCard class="login-card" :bordered="false">
      <NSpace justify="space-between" align="center" class="login-title-row">
        <div class="login-brand">
          <span class="login-brand-mark" aria-hidden="true">
            <TvMinimalPlay :size="24" :stroke-width="2.2" />
          </span>
          <h1>{{ t("app.title") }}</h1>
        </div>
        <NSelect
          :value="locale"
          :options="localeOptions"
          size="small"
          class="locale-select"
          :aria-label="t('common.language')"
          @update:value="changeLocale"
        />
      </NSpace>
      <NForm @submit.prevent="submit">
        <NFormItem v-if="setupRequired" :label="t('login.setupCode')">
          <NInput v-model:value="setupCode" autofocus />
        </NFormItem>
        <NFormItem>
          <template #label>
            <FieldLabel :label="t('login.accessCode')" :tooltip="t('tooltips.admin_access_code')" />
          </template>
          <NInput v-model:value="accessCode" type="password" :autofocus="!setupRequired" />
        </NFormItem>
        <NFormItem v-if="setupRequired">
          <template #label>
            <FieldLabel :label="t('login.confirmAccessCode')" :tooltip="t('tooltips.admin_access_code')" />
          </template>
          <NInput v-model:value="confirmAccessCode" type="password" />
        </NFormItem>
        <NSpace justify="end">
          <NButton type="primary" attr-type="submit" :loading="loading">
            {{ setupRequired ? t("login.finishSetup") : t("login.login") }}
          </NButton>
        </NSpace>
      </NForm>
    </NCard>
  </div>
</template>
