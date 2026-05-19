<script setup lang="ts">
import { defineAsyncComponent, ref } from "vue";
import { NButton, NCard, NForm, NFormItem, NInput, NSpace, useMessage } from "naive-ui";
import { updateAccessCode } from "../api";
import { t } from "../i18n";

const FieldLabel = defineAsyncComponent(() => import("../components/FieldLabel.vue"));
const message = useMessage();
const loading = ref(false);
const currentCode = ref("");
const newCode = ref("");
const confirmCode = ref("");

async function submit() {
  if (newCode.value !== confirmCode.value) {
    message.error(t("account.mismatch"));
    return;
  }
  loading.value = true;
  try {
    await updateAccessCode(currentCode.value, newCode.value);
    currentCode.value = "";
    newCode.value = "";
    confirmCode.value = "";
    message.success(t("account.updated"));
  } catch (error) {
    message.error(error instanceof Error ? error.message : t("account.failed"));
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="page-stack narrow">
    <NCard size="small">
      <NForm @submit.prevent="submit">
        <NFormItem>
          <template #label>
            <FieldLabel :label="t('account.currentCode')" :tooltip="t('tooltips.admin_access_code')" />
          </template>
          <NInput v-model:value="currentCode" type="password" />
        </NFormItem>
        <NFormItem>
          <template #label>
            <FieldLabel :label="t('account.newCode')" :tooltip="t('tooltips.admin_access_code')" />
          </template>
          <NInput v-model:value="newCode" type="password" />
        </NFormItem>
        <NFormItem>
          <template #label>
            <FieldLabel :label="t('account.confirmNewCode')" :tooltip="t('tooltips.admin_access_code')" />
          </template>
          <NInput v-model:value="confirmCode" type="password" />
        </NFormItem>
        <NSpace justify="end">
          <NButton type="primary" attr-type="submit" :loading="loading">{{ t("common.update") }}</NButton>
        </NSpace>
      </NForm>
    </NCard>
  </div>
</template>
