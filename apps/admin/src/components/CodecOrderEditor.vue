<script setup lang="ts">
import { computed, ref } from "vue";
import { GripVertical } from "@lucide/vue";
import { NCheckbox, NIcon } from "naive-ui";
import { t } from "../i18n";

type CodecOption = {
  label: string;
  value: string;
  enabled: boolean;
};

const props = defineProps<{
  modelValue: CodecOption[];
}>();

const emit = defineEmits<{
  "update:modelValue": [value: CodecOption[]];
}>();

const draggingCodec = ref("");

const enabledCodecs = computed(() => props.modelValue.filter((item) => item.enabled));

function emitItems(items: CodecOption[]) {
  emit("update:modelValue", items);
}

function updateChecked(value: string, checked: boolean) {
  if (!checked && enabledCodecs.value.length <= 1) {
    return;
  }

  emitItems(props.modelValue.map((item) => (item.value === value ? { ...item, enabled: checked } : item)));
}

function dragCodec(value: string) {
  draggingCodec.value = value;
}

function dropCodec(target: string) {
  const source = draggingCodec.value;
  draggingCodec.value = "";
  if (!source || source === target) {
    return;
  }

  const next = props.modelValue.filter((item) => item.value !== source);
  const sourceItem = props.modelValue.find((item) => item.value === source);
  const targetIndex = next.findIndex((item) => item.value === target);
  if (!sourceItem || targetIndex === -1) {
    return;
  }
  next.splice(targetIndex, 0, sourceItem);
  emitItems(next);
}
</script>

<template>
  <div class="codec-order-editor">
    <div
      v-for="codec in modelValue"
      :key="codec.value"
      class="codec-row"
      :class="{ 'codec-row-dragging': draggingCodec === codec.value }"
      draggable="true"
      @dragstart="dragCodec(codec.value)"
      @dragover.prevent
      @drop="dropCodec(codec.value)"
      @dragend="draggingCodec = ''"
    >
      <span class="codec-drag-handle" :title="t('codec.dragToSort')">
        <NIcon :component="GripVertical" />
      </span>
      <NCheckbox
        :checked="codec.enabled"
        :disabled="codec.enabled && enabledCodecs.length <= 1"
        :title="codec.enabled && enabledCodecs.length <= 1 ? t('codec.keepOne') : undefined"
        @update:checked="(checked) => updateChecked(codec.value, checked)"
      >
        {{ codec.label }}
      </NCheckbox>
    </div>
  </div>
</template>
