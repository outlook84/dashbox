<script setup lang="ts">
import { computed, ref, watch } from "vue";
import {
  NButton,
  NCollapse,
  NCollapseItem,
  NIcon,
  NInput,
  NModal,
  NSpace
} from "naive-ui";
import { ArrowDown, ArrowUp, Check, FolderPlus, Link, Pencil, Plus, Trash2, X } from "@lucide/vue";
import { t } from "../i18n";
import SourceItemsEditor from "./SourceItemsEditor.vue";
import type { SourceTreeSelection } from "./SourceItemsEditor.vue";

type SourceRecord = Record<string, unknown>;
type DraftSourceRecord = SourceRecord & { __draftKey: string; items?: unknown[] };
type ApplyDraftResult = { ok: true } | { ok: false; error: string };
const DRAFT_KEY = "__draftKey";
let draftKeyCounter = 0;

const props = defineProps<{
  modelValue: unknown[];
  subscriptionType: string;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: SourceRecord[]];
}>();

const isTvbox = computed(() => props.subscriptionType === "tvbox");
const draftSources = ref<DraftSourceRecord[]>([]);
const sources = computed(() => draftSources.value);
const deleteConfirmOpen = ref(false);
const pendingDeleteIndex = ref<number | null>(null);
const pendingDeleteLabel = ref("");
const editingSourceIndex = ref<number | null>(null);
const editingSourceName = ref("");
const selection = ref<SourceTreeSelection>({
  kind: "root",
  key: "root",
  label: t("sources.root")
});
const selectedKey = computed(() => selection.value.key);
const canAddItemsToSelection = computed(() =>
  selection.value.kind === "root" ? !isTvbox.value : selection.value.kind === "source" || selection.value.kind === "folder"
);

function isRecord(value: unknown): value is SourceRecord {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

watch(
  () => props.modelValue,
  (value) => {
    draftSources.value = value.filter(isRecord).map(createDraftRecord);
    selectRoot();
  },
  { immediate: true }
);

function updateSources(nextSources: SourceRecord[]) {
  draftSources.value = nextSources.filter(isRecord).map(ensureDraftRecord);
  if (selection.value.kind !== "root" && !draftKeyExists(draftSources.value, selection.value.key)) {
    selectRoot();
  }
}

function updateSource(index: number, mutator: (source: SourceRecord) => SourceRecord) {
  const nextSources = sources.value.slice();
  nextSources[index] = ensureDraftRecord(mutator({ ...nextSources[index] }));
  updateSources(nextSources);
}

function setSourceField(index: number, key: string, value: unknown) {
  updateSource(index, (source) => ({ ...source, [key]: value }));
}

function setSourceItems(index: number, value: SourceRecord[]) {
  updateSource(index, (source) => ({ ...source, items: value }));
}

function addSource() {
  const nextIndex = sources.value.length;
  const source = createDraftRecord({ id: "", name: "", items: [] });
  updateSources([...sources.value, source]);
  selection.value = {
    kind: "source",
    key: source.__draftKey,
    label: `${t("sources.source")} ${nextIndex + 1}`
  };
}

function addUrlToSelection() {
  addItemToSelection({ id: "", title: "", url: "" });
}

function addFolderToSelection() {
  addItemToSelection({ id: "", name: "", items: [] });
}

function addItemToSelection(item: SourceRecord) {
  if (!canAddItemsToSelection.value) return;
  const nextItem = createDraftRecord(item);
  if (selection.value.kind === "root") {
    updateSources([...sources.value, nextItem]);
    return;
  }
  updateSources(addItemToDraftKey(sources.value, selection.value.key, nextItem));
}

function sourceLabel(source: SourceRecord, index: number) {
  return String(source.name || `${t("sources.source")} ${index + 1}`);
}

function sourceNodeTitle(source: SourceRecord, index: number) {
  return `${t("sources.source")} ${index + 1} · ${sourceLabel(source, index)}`;
}

function sourceSelectionKey(source: SourceRecord) {
  return String(source[DRAFT_KEY]);
}

function selectRoot() {
  selection.value = {
    kind: "root",
    key: "root",
    label: t("sources.root")
  };
}

function selectSource(index: number, source: SourceRecord) {
  selection.value = {
    kind: "source",
    key: String(source[DRAFT_KEY]),
    label: sourceLabel(source, index)
  };
}

function selectSourceFromHeaderClick(event: MouseEvent, index: number, source: SourceRecord) {
  const target = event.target;
  if (!(target instanceof HTMLElement) || !target.closest(".n-collapse-item__header")) return;
  selectSource(index, source);
}

function cloneRecord(value: SourceRecord): SourceRecord {
  return JSON.parse(JSON.stringify(value)) as SourceRecord;
}

function nextDraftKey() {
  draftKeyCounter += 1;
  return `source-draft-${draftKeyCounter}`;
}

function createDraftRecord(value: SourceRecord): DraftSourceRecord {
  const draft = cloneRecord(value) as DraftSourceRecord;
  draft.__draftKey = nextDraftKey();
  if (Array.isArray(draft.items)) {
    draft.items = draft.items.filter(isRecord).map(createDraftRecord);
  }
  return draft;
}

function ensureDraftRecord(value: SourceRecord): DraftSourceRecord {
  const draft = { ...value } as DraftSourceRecord;
  draft.__draftKey = typeof draft.__draftKey === "string" ? draft.__draftKey : nextDraftKey();
  if (Array.isArray(draft.items)) {
    draft.items = draft.items.filter(isRecord).map(ensureDraftRecord);
  }
  return draft;
}

function cleanDraftRecord(value: SourceRecord): SourceRecord {
  const { [DRAFT_KEY]: _draftKey, ...clean } = value;
  if (Array.isArray(clean.items)) {
    clean.items = clean.items.filter(isRecord).map(cleanDraftRecord);
  }
  return clean;
}

function recordLabel(value: SourceRecord, fallback: string) {
  return String(value.name || value.title || value.url || fallback).trim() || fallback;
}

function validationError(message: string, key: string, label: string, kind: SourceTreeSelection["kind"]): ApplyDraftResult {
  selection.value = { kind, key, label };
  return { ok: false, error: message };
}

function validateItem(item: SourceRecord, path: string): ApplyDraftResult {
  const key = String(item[DRAFT_KEY] || "");
  const label = recordLabel(item, path);
  const hasUrl = Object.prototype.hasOwnProperty.call(item, "url");
  const hasItems = Object.prototype.hasOwnProperty.call(item, "items");
  if (hasUrl && hasItems) {
    return validationError(`${path}: ${t("sources.validationUrlAndItems")}`, key, label, "url");
  }
  if (hasUrl) {
    if (!String(item.url || "").trim()) {
      return validationError(`${path}: ${t("sources.validationUrlRequired")}`, key, label, "url");
    }
    if (Object.prototype.hasOwnProperty.call(item, "name")) {
      return validationError(`${path}: ${t("sources.validationUrlNameUnsupported")}`, key, label, "url");
    }
    return { ok: true };
  }
  if (hasItems) {
    if (!String(item.name || "").trim()) {
      return validationError(`${path}: ${t("sources.validationFolderNameRequired")}`, key, label, "folder");
    }
    if (!Array.isArray(item.items)) {
      return validationError(`${path}: ${t("sources.validationItemsArrayRequired")}`, key, label, "folder");
    }
    const children = item.items.filter(isRecord);
    for (const [index, child] of children.entries()) {
      const result = validateItem(child, `${path} / ${recordLabel(child, `${t("sources.items")} ${index + 1}`)}`);
      if (!result.ok) return result;
    }
    return { ok: true };
  }
  return validationError(`${path}: ${t("sources.validationUrlOrItemsRequired")}`, key, label, "url");
}

function validateDraft(): ApplyDraftResult {
  if (isTvbox.value) {
    for (const [sourceIndex, source] of sources.value.entries()) {
      const children = Array.isArray(source.items) ? source.items.filter(isRecord) : [];
      for (const [itemIndex, item] of children.entries()) {
        const itemPath = `${sourceLabel(source, sourceIndex)} / ${recordLabel(item, `${t("sources.items")} ${itemIndex + 1}`)}`;
        const result = validateItem(item, itemPath);
        if (!result.ok) return result;
      }
    }
    return { ok: true };
  }
  for (const [index, item] of sources.value.entries()) {
    const result = validateItem(item, recordLabel(item, `${t("sources.items")} ${index + 1}`));
    if (!result.ok) return result;
  }
  return { ok: true };
}

function draftKeyExists(items: SourceRecord[], key: string): boolean {
  return items.some((item) => {
    if (item[DRAFT_KEY] === key) return true;
    return Array.isArray(item.items) && draftKeyExists(item.items.filter(isRecord), key);
  });
}

function addItemToDraftKey(items: SourceRecord[], key: string, item: SourceRecord): DraftSourceRecord[] {
  return items.map((current) => {
    if (current[DRAFT_KEY] === key) {
      const childItems = Array.isArray(current.items) ? current.items.filter(isRecord).map(ensureDraftRecord) : [];
      return ensureDraftRecord({ ...current, items: [...childItems, item] });
    }
    if (!Array.isArray(current.items)) return ensureDraftRecord(current);
    return ensureDraftRecord({
      ...current,
      items: addItemToDraftKey(current.items.filter(isRecord), key, item)
    });
  });
}

function applyDraft(): ApplyDraftResult {
  const validation = validateDraft();
  if (!validation.ok) return validation;
  emit("update:modelValue", sources.value.map(cleanDraftRecord));
  return { ok: true };
}

defineExpose({
  applyDraft
});

function startEditSourceName(index: number, source: SourceRecord) {
  editingSourceIndex.value = index;
  editingSourceName.value = String(source.name || "");
}

function cancelEditSourceName() {
  editingSourceIndex.value = null;
  editingSourceName.value = "";
}

function applyEditSourceName(index: number) {
  setSourceField(index, "name", editingSourceName.value);
  cancelEditSourceName();
}

function requestRemoveSource(index: number) {
  const source = sources.value[index];
  pendingDeleteIndex.value = index;
  pendingDeleteLabel.value = source ? sourceLabel(source, index) : "";
  deleteConfirmOpen.value = true;
}

function cancelRemoveSource() {
  deleteConfirmOpen.value = false;
  pendingDeleteIndex.value = null;
  pendingDeleteLabel.value = "";
}

function confirmRemoveSource() {
  const index = pendingDeleteIndex.value;
  if (index === null) return;
  const nextSources = sources.value.slice();
  nextSources.splice(index, 1);
  updateSources(nextSources);
  cancelRemoveSource();
}

function moveSource(index: number, offset: -1 | 1) {
  const nextIndex = index + offset;
  if (nextIndex < 0 || nextIndex >= sources.value.length) return;
  const nextSources = sources.value.slice();
  const [source] = nextSources.splice(index, 1);
  nextSources.splice(nextIndex, 0, source);
  updateSources(nextSources);
}
</script>

<template>
  <div class="sources-editor">
    <template v-if="isTvbox">
      <NSpace class="source-editor-actions" size="small" align="center">
        <NButton size="small" secondary type="primary" @click="addSource">
          <template #icon>
            <NIcon><Plus /></NIcon>
          </template>
          {{ t("sources.addSource") }}
        </NButton>
        <NButton size="small" secondary :disabled="!canAddItemsToSelection" @click="addUrlToSelection">
          <template #icon>
            <NIcon><Link /></NIcon>
          </template>
          {{ t("sources.addUrl") }}
        </NButton>
        <NButton size="small" secondary :disabled="!canAddItemsToSelection" @click="addFolderToSelection">
          <template #icon>
            <NIcon><FolderPlus /></NIcon>
          </template>
          {{ t("sources.addFolder") }}
        </NButton>
        <span class="source-selection-label">{{ t("sources.addTo") }}: {{ selection.label }}</span>
      </NSpace>

      <NCollapse v-if="sources.length" class="source-tree-collapse source-sources-collapse">
        <NCollapseItem
          v-for="(source, index) in sources"
          :key="sourceSelectionKey(source)"
          :title="sourceNodeTitle(source, index)"
          :name="sourceSelectionKey(source)"
          :class="['source-tree-node', { 'source-tree-node-active': selectedKey === sourceSelectionKey(source) }]"
          @click="selectSourceFromHeaderClick($event, index, source)"
        >
          <template #header>
            <div
              :class="['source-node-title', { 'source-node-title-active': selectedKey === sourceSelectionKey(source) }]"
            >
              <template v-if="editingSourceIndex === index">
                <span>{{ t("sources.source") }} {{ index + 1 }} ·</span>
                <NInput
                  v-model:value="editingSourceName"
                  size="small"
                  class="source-inline-input"
                  @keydown.enter.stop.prevent="applyEditSourceName(index)"
                  @keydown.esc.stop.prevent="cancelEditSourceName"
                />
                <NButton
                  circle
                  quaternary
                  size="small"
                  :title="t('common.apply')"
                  :aria-label="t('common.apply')"
                  @click.stop="applyEditSourceName(index)"
                >
                  <NIcon><Check /></NIcon>
                </NButton>
                <NButton
                  circle
                  quaternary
                  size="small"
                  :title="t('common.cancel')"
                  :aria-label="t('common.cancel')"
                  @click.stop="cancelEditSourceName"
                >
                  <NIcon><X /></NIcon>
                </NButton>
              </template>
              <template v-else>
                <span>{{ sourceNodeTitle(source, index) }}</span>
                <NButton
                  circle
                  quaternary
                  size="small"
                  :title="t('common.edit')"
                  :aria-label="t('common.edit')"
                  @click.stop="startEditSourceName(index, source)"
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
                @click.stop="moveSource(index, -1)"
              >
                <NIcon><ArrowUp /></NIcon>
              </NButton>
              <NButton
                circle
                quaternary
                size="small"
                :disabled="index === sources.length - 1"
                :title="t('sources.moveDown')"
                :aria-label="t('sources.moveDown')"
                @click.stop="moveSource(index, 1)"
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
                @click.stop="requestRemoveSource(index)"
              >
                <NIcon><Trash2 /></NIcon>
              </NButton>
            </NSpace>
          </template>

          <div class="source-node-children">
            <SourceItemsEditor
              :model-value="Array.isArray(source.items) ? source.items : []"
              :selected-key="selectedKey"
              @update:model-value="(value) => setSourceItems(index, value)"
              @select-node="(value) => selection = value"
            />
          </div>
        </NCollapseItem>
      </NCollapse>
    </template>

    <template v-else>
      <NSpace class="source-editor-actions" size="small" align="center">
        <NButton size="small" secondary :disabled="!canAddItemsToSelection" @click="addUrlToSelection">
          <template #icon>
            <NIcon><Link /></NIcon>
          </template>
          {{ t("sources.addUrl") }}
        </NButton>
        <NButton size="small" secondary :disabled="!canAddItemsToSelection" @click="addFolderToSelection">
          <template #icon>
            <NIcon><FolderPlus /></NIcon>
          </template>
          {{ t("sources.addFolder") }}
        </NButton>
        <NButton
          size="small"
          quaternary
          :type="selectedKey === 'root' ? 'primary' : 'default'"
          :title="t('sources.selectTopLevel')"
          :aria-label="t('sources.selectTopLevel')"
          @click="selectRoot"
        >
          {{ t("sources.root") }}
        </NButton>
        <span class="source-selection-label">{{ t("sources.addTo") }}: {{ selection.label }}</span>
      </NSpace>
      <SourceItemsEditor
        :model-value="sources"
        :selected-key="selectedKey"
        @update:model-value="updateSources"
        @select-node="(value) => selection = value"
      />
    </template>

    <NModal
      v-model:show="deleteConfirmOpen"
      preset="dialog"
      type="warning"
      :title="t('sources.deleteSource')"
      :positive-text="t('common.delete')"
      :negative-text="t('common.cancel')"
      @positive-click="confirmRemoveSource"
      @negative-click="cancelRemoveSource"
      @close="cancelRemoveSource"
    >
      <p>{{ t("sources.confirmDeleteSource") }}</p>
      <p v-if="pendingDeleteLabel">{{ pendingDeleteLabel }}</p>
    </NModal>
  </div>
</template>
