<script setup lang="ts">
import { HelpCircle } from "@lucide/vue";
import { NIcon, NTooltip } from "naive-ui";

defineProps<{
  label: string;
  tooltip: string;
}>();
</script>

<template>
  <span class="field-label">
    <span>{{ label }}</span>
    <NTooltip trigger="hover">
      <template #trigger>
        <NIcon class="field-label-help" size="14" :aria-label="tooltip">
          <HelpCircle />
        </NIcon>
      </template>
      {{ tooltip }}
    </NTooltip>
  </span>
</template>
