<script setup lang="ts">
import { computed, defineAsyncComponent, ref } from "vue";
import {
  NButton,
  NCollapse,
  NCollapseItem,
  NFormItem,
  NGi,
  NGrid,
  NIcon,
  NInput,
  NModal,
  NSpace
} from "naive-ui";
import { ArrowDown, ArrowUp, Check, Folder, Link, Pencil, Trash2, X } from "@lucide/vue";
import { t } from "../i18n";
import { safeWebUrl } from "../utils/url";

const FieldLabel = defineAsyncComponent(() => import("./FieldLabel.vue"));

type SourceItemKind = "url" | "folder";
type SourceItem = Record<string, unknown>;
export type SourceTreeSelection = {
  kind: "root" | "source" | "folder" | "url";
  key: string;
  label: string;
};
const DRAFT_KEY = "__draftKey";

const props = withDefaults(defineProps<{
  modelValue: unknown[];
  depth?: number;
  selectedKey?: string;
}>(), {
  depth: 0,
  selectedKey: ""
});

const emit = defineEmits<{
  "update:modelValue": [value: SourceItem[]];
  "select-node": [value: SourceTreeSelection];
}>();

const items = computed(() => props.modelValue.filter(isRecord).map((item) => ({ ...item })));
const deleteConfirmOpen = ref(false);
const pendingDeleteIndex = ref<number | null>(null);
const pendingDeleteLabel = ref("");
const editingItemIndex = ref<number | null>(null);
const editingItemLabel = ref("");

function isRecord(value: unknown): value is SourceItem {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function itemKind(item: SourceItem): SourceItemKind {
  return Array.isArray(item.items) ? "folder" : "url";
}

function updateItems(nextItems: SourceItem[]) {
  emit("update:modelValue", nextItems);
}

function updateItem(index: number, mutator: (item: SourceItem) => SourceItem) {
  const nextItems = items.value.slice();
  nextItems[index] = mutator({ ...nextItems[index] });
  updateItems(nextItems);
}

function setItemField(index: number, key: string, value: unknown) {
  updateItem(index, (item) => ({ ...item, [key]: value }));
}

function setFolderItems(index: number, value: SourceItem[]) {
  updateItem(index, (item) => ({ ...item, items: value }));
}

function itemLabel(item: SourceItem, index: number) {
  if (itemKind(item) === "folder") {
    return String(item.name || `${t("sources.folderItem")} ${index + 1}`);
  }
  return String(item.title || item.url || `${t("sources.urlItem")} ${index + 1}`);
}

function itemNodeTitle(item: SourceItem, index: number) {
  return itemLabel(item, index);
}

function itemKey(item: SourceItem, index: number) {
  return String(item[DRAFT_KEY] || `item:${props.depth}:${index}`);
}

function selectItem(index: number, item: SourceItem) {
  emit("select-node", {
    kind: itemKind(item),
    key: itemKey(item, index),
    label: itemLabel(item, index)
  });
}

function selectItemFromHeaderClick(event: MouseEvent, index: number, item: SourceItem) {
  const target = event.target;
  if (!(target instanceof Element) || !target.closest(".n-collapse-item__header")) return;
  selectItem(index, item);
}

function itemLabelField(item: SourceItem) {
  return itemKind(item) === "folder" ? "name" : "title";
}

function itemOpenUrl(item: SourceItem) {
  return itemKind(item) === "url" ? safeWebUrl(item.url) : "";
}

function startEditItemLabel(index: number, item: SourceItem) {
  editingItemIndex.value = index;
  editingItemLabel.value = String(item[itemLabelField(item)] || "");
}

function cancelEditItemLabel() {
  editingItemIndex.value = null;
  editingItemLabel.value = "";
}

function applyEditItemLabel(index: number, item: SourceItem) {
  setItemField(index, itemLabelField(item), editingItemLabel.value);
  cancelEditItemLabel();
}

function requestRemoveItem(index: number) {
  const item = items.value[index];
  pendingDeleteIndex.value = index;
  pendingDeleteLabel.value = item ? itemLabel(item, index) : "";
  deleteConfirmOpen.value = true;
}

function cancelRemoveItem() {
  deleteConfirmOpen.value = false;
  pendingDeleteIndex.value = null;
  pendingDeleteLabel.value = "";
}

function confirmRemoveItem() {
  const index = pendingDeleteIndex.value;
  if (index === null) return;
  const nextItems = items.value.slice();
  nextItems.splice(index, 1);
  updateItems(nextItems);
  cancelRemoveItem();
}

function moveItem(index: number, offset: -1 | 1) {
  const nextIndex = index + offset;
  if (nextIndex < 0 || nextIndex >= items.value.length) return;
  const nextItems = items.value.slice();
  const [item] = nextItems.splice(index, 1);
  nextItems.splice(nextIndex, 0, item);
  updateItems(nextItems);
}
</script>

<template>
  <div class="source-items-editor" :class="{ 'source-items-editor-nested': depth > 0 }" @click.stop>
    <NCollapse v-if="items.length" class="source-tree-collapse source-items-collapse">
      <NCollapseItem
        v-for="(item, index) in items"
        :key="itemKey(item, index)"
        :title="itemNodeTitle(item, index)"
        :name="itemKey(item, index)"
        :class="['source-tree-node', { 'source-tree-node-active': selectedKey === itemKey(item, index) }]"
        @click="selectItemFromHeaderClick($event, index, item)"
      >
        <template #header>
          <div
            :class="['source-node-title', { 'source-node-title-active': selectedKey === itemKey(item, index) }]"
          >
            <template v-if="editingItemIndex === index">
              <NIcon size="16">
                <Folder v-if="itemKind(item) === 'folder'" />
                <Link v-else />
              </NIcon>
              <NInput
                v-model:value="editingItemLabel"
                size="small"
                class="source-inline-input"
                @keydown.enter.stop.prevent="applyEditItemLabel(index, item)"
                @keydown.esc.stop.prevent="cancelEditItemLabel"
              />
              <NButton
                circle
                quaternary
                size="small"
                :title="t('common.apply')"
                :aria-label="t('common.apply')"
                @click.stop="applyEditItemLabel(index, item)"
              >
                <NIcon><Check /></NIcon>
              </NButton>
              <NButton
                circle
                quaternary
                size="small"
                :title="t('common.cancel')"
                :aria-label="t('common.cancel')"
                @click.stop="cancelEditItemLabel"
              >
                <NIcon><X /></NIcon>
              </NButton>
            </template>
            <template v-else>
              <NIcon v-if="itemKind(item) === 'folder'" size="16">
                <Folder />
              </NIcon>
              <a
                v-else-if="itemOpenUrl(item)"
                class="source-node-icon-link"
                :href="itemOpenUrl(item)"
                target="_blank"
                rel="noopener noreferrer"
                :title="t('config.openUrl')"
                :aria-label="t('config.openUrl')"
                @click.stop
              >
                <NIcon size="16"><Link /></NIcon>
              </a>
              <NIcon v-else size="16">
                <Link />
              </NIcon>
              <span>{{ itemNodeTitle(item, index) }}</span>
              <NButton
                v-if="itemKind(item) === 'folder'"
                circle
                quaternary
                size="small"
                :title="t('common.edit')"
                :aria-label="t('common.edit')"
                @click.stop="startEditItemLabel(index, item)"
              >
                <NIcon><Pencil /></NIcon>
              </NButton>
            </template>
          </div>
        </template>
        <template #header-extra>
          <NSpace size="small">
            <NButton
              circle
              quaternary
              size="small"
              :disabled="index === 0"
              :title="t('sources.moveUp')"
              :aria-label="t('sources.moveUp')"
              @click.stop="moveItem(index, -1)"
            >
              <NIcon><ArrowUp /></NIcon>
            </NButton>
            <NButton
              circle
              quaternary
              size="small"
              :disabled="index === items.length - 1"
              :title="t('sources.moveDown')"
              :aria-label="t('sources.moveDown')"
              @click.stop="moveItem(index, 1)"
            >
              <NIcon><ArrowDown /></NIcon>
            </NButton>
            <NButton
              circle
              quaternary
              size="small"
              type="error"
              :title="t('common.delete')"
              :aria-label="t('common.delete')"
              @click.stop="requestRemoveItem(index)"
            >
              <NIcon><Trash2 /></NIcon>
            </NButton>
          </NSpace>
        </template>

        <div v-if="itemKind(item) === 'folder'" class="source-node-children">
          <SourceItemsEditor
            :model-value="Array.isArray(item.items) ? item.items : []"
            :depth="depth + 1"
            :selected-key="selectedKey"
            @update:model-value="(value) => setFolderItems(index, value)"
            @select-node="(value) => emit('select-node', value)"
          />
        </div>
        <NGrid v-else cols="1 s:2" :x-gap="12" responsive="screen">
          <NGi>
            <NFormItem>
              <template #label>
                <FieldLabel :label="t('sources.title')" :tooltip="t('tooltips.item.title')" />
              </template>
              <NInput :value="String(item.title || '')" @update:value="(value) => setItemField(index, 'title', value)" />
            </NFormItem>
          </NGi>
          <NGi>
            <NFormItem>
              <template #label>
                <FieldLabel :label="t('sources.url')" :tooltip="t('tooltips.item.url')" />
              </template>
              <NInput :value="String(item.url || '')" @update:value="(value) => setItemField(index, 'url', value)" />
            </NFormItem>
          </NGi>
        </NGrid>
      </NCollapseItem>
    </NCollapse>

    <NModal
      v-model:show="deleteConfirmOpen"
      preset="dialog"
      type="warning"
      :title="t('sources.deleteItem')"
      :positive-text="t('common.delete')"
      :negative-text="t('common.cancel')"
      @positive-click="confirmRemoveItem"
      @negative-click="cancelRemoveItem"
      @close="cancelRemoveItem"
    >
      <p>{{ t("sources.confirmDeleteItem") }}</p>
      <p v-if="pendingDeleteLabel">{{ pendingDeleteLabel }}</p>
    </NModal>
  </div>
</template>
