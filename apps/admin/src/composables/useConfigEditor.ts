import { computed, onMounted, ref, watch } from "vue";
import type { MessageApi, TreeOption } from "naive-ui";
import { normalizeConfig, readConfig, readSchema, saveConfig, validateConfig } from "../api";
import { locale, t } from "../i18n";
import { displayLabel, type LabelGroup } from "../labels";
import type { AdminSchema, ConfigResponse } from "../types";

type SelectOption = {
  label: string;
  value: string;
};

type CodecOrderItem = SelectOption & {
  enabled: boolean;
};

type SubscriptionPayloadKey = "kodi" | "tvbox";

let subscriptionDraftKeyCounter = 0;

export function useConfigEditor(message: MessageApi) {
  const loading = ref(false);
  const saving = ref(false);
  const schema = ref<AdminSchema | null>(null);
  const editor = ref("");
  const lastError = ref("");
  const saveConfirmOpen = ref(false);
  const pendingSaveConfig = ref<Record<string, unknown> | null>(null);
  const deleteConfirmOpen = ref(false);
  const pendingDeleteSubscriptionIndex = ref<number | null>(null);
  const pendingDeleteSubscriptionLabel = ref("");
  const showJsonEditor = ref(false);
  const sourceEditorOpen = ref(false);
  const sourceEditorSubscriptionIndex = ref<number | null>(null);
  const sourceEditorDraft = ref<Record<string, unknown>[]>([]);
  const effectiveValues = ref<Record<string, unknown>>({});
  const savedSubscriptionIds = ref<Set<string>>(new Set());
  const subscriptionDraftKeys = ref<string[]>([]);
  const subscriptionNumberDrafts = ref<Record<string, number | null>>({});

  const configObject = computed(() => parseEditorSilently());
  const subs = computed(() => {
    const items = configObject.value?.subs;
    return Array.isArray(items) ? items.filter(isRecord) : [];
  });
  const effectiveUserAgent = computed(() => String(effectiveValues.value.user_agent || ""));

  const logLevelOptions = computed(() => selectOptions(schema.value?.log_level));
  const cookieModeOptions = computed(() => selectOptions(schema.value?.cookies_from_browser_mode, "cookiesMode"));
  const authModeOptions = computed(() => selectOptions(schema.value?.auth_mode, "authMode"));
  const subscriptionTypeOptions = computed(() => selectOptions(schema.value?.subscription_type, "subscriptionType"));
  const searchProviderOptions = computed(() => selectOptions(schema.value?.search_provider, "searchProvider"));
  const ytdlpSearchPrefixModeOptions = computed(() => selectOptions(schema.value?.ytdlp_search_prefix_mode, "ytdlpSearchPrefixMode"));
  const vodStyleOptions = computed(() => selectOptions(schema.value?.vod_style, "vodStyle"));
  const tvboxLocaleOptions = computed(() => selectOptions(schema.value?.tvbox_locale));
  const videoCodecOptions = computed(() => selectOptions(schema.value?.video_codec));
  const audioCodecOptions = computed(() => selectOptions(schema.value?.audio_codec));
  const maxVideoHeightOptions = computed(() => numberOptions(schema.value?.max_video_height, t("subscriptions.unlimited")));
  const maxVideoFpsOptions = computed(() => numberOptions(schema.value?.max_video_fps, t("subscriptions.unlimited")));

  function isRecord(value: unknown): value is Record<string, unknown> {
    return Boolean(value) && typeof value === "object" && !Array.isArray(value);
  }

  function selectOptions(values: string[] | undefined, labelGroup?: LabelGroup) {
    return (values || []).map((value) => ({ label: labelGroup ? displayLabel(labelGroup, value) : value, value }));
  }

  function numberOptions(values: number[] | undefined, zeroLabel: string) {
    const items = values && values.includes(0) ? values : [0, ...(values || [])];
    return items.map((value) => ({ label: value === 0 ? zeroLabel : String(value), value }));
  }

  function nextSubscriptionDraftKey() {
    subscriptionDraftKeyCounter += 1;
    return `subscription-draft-${subscriptionDraftKeyCounter}`;
  }

  function resetSubscriptionDraftKeys(value: unknown) {
    const length = Array.isArray(value) ? value.filter(isRecord).length : 0;
    subscriptionDraftKeys.value = Array.from({ length }, nextSubscriptionDraftKey);
    subscriptionNumberDrafts.value = {};
  }

  function reconcileSubscriptionDraftKeys(length: number) {
    const keys = subscriptionDraftKeys.value.slice(0, length);
    while (keys.length < length) {
      keys.push(nextSubscriptionDraftKey());
    }
    subscriptionDraftKeys.value = keys;
  }

  function subscriptionCardKey(index: number) {
    return subscriptionDraftKeys.value[index] || `subscription-draft-fallback-${index}`;
  }

  function subscriptionDraftFieldKey(index: number, payloadKey: SubscriptionPayloadKey, key: string) {
    return `${subscriptionCardKey(index)}:${payloadKey}:${key}`;
  }

  function subscriptionPayloadNumberValue(
    index: number,
    payload: Record<string, unknown>,
    payloadKey: SubscriptionPayloadKey,
    key: string,
    fallback: number | null
  ) {
    const draftKey = subscriptionDraftFieldKey(index, payloadKey, key);
    return Object.prototype.hasOwnProperty.call(subscriptionNumberDrafts.value, draftKey)
      ? subscriptionNumberDrafts.value[draftKey]
      : effectivePayloadNumber(payload, key, fallback);
  }

  function updateSubscriptionPayloadNumber(
    index: number,
    payloadKey: SubscriptionPayloadKey,
    key: string,
    value: number | null
  ) {
    subscriptionNumberDrafts.value[subscriptionDraftFieldKey(index, payloadKey, key)] = value;
    updateSubPayload(index, payloadKey, key, value, { deleteEmpty: true });
  }

  function clearSubscriptionPayloadNumberDraft(index: number, payloadKey: SubscriptionPayloadKey, key: string) {
    const draftKey = subscriptionDraftFieldKey(index, payloadKey, key);
    if (!Object.prototype.hasOwnProperty.call(subscriptionNumberDrafts.value, draftKey)) return;
    const { [draftKey]: _removed, ...nextDrafts } = subscriptionNumberDrafts.value;
    subscriptionNumberDrafts.value = nextDrafts;
  }

  function clearSubscriptionDraftsForCard(cardKey: string) {
    const prefix = `${cardKey}:`;
    subscriptionNumberDrafts.value = Object.fromEntries(
      Object.entries(subscriptionNumberDrafts.value).filter(([key]) => !key.startsWith(prefix))
    );
  }

  function parseEditorSilently(): Record<string, unknown> | null {
    try {
      const value = JSON.parse(editor.value);
      return isRecord(value) ? value : null;
    } catch {
      return null;
    }
  }

  function parseEditor(): Record<string, unknown> | null {
    try {
      const value = JSON.parse(editor.value);
      if (!isRecord(value)) {
        throw new Error(t("config.objectRequired"));
      }
      lastError.value = "";
      return value as Record<string, unknown>;
    } catch (error) {
      lastError.value = error instanceof Error ? error.message : t("config.parseFailed");
      message.error(lastError.value);
      return null;
    }
  }

  function fill(data: ConfigResponse) {
    editor.value = JSON.stringify(data.config, null, 2);
    effectiveValues.value = data.effective_values || {};
    savedSubscriptionIds.value = subscriptionIds(data.config.subs);
    resetSubscriptionDraftKeys(data.config.subs);
  }

  function writeConfig(config: Record<string, unknown>) {
    editor.value = JSON.stringify(config, null, 2);
  }

  function updateConfig(mutator: (config: Record<string, unknown>) => void) {
    const config = parseEditor();
    if (!config) return;
    mutator(config);
    writeConfig(config);
  }

  function updateGlobal(key: string, value: unknown) {
    updateConfig((config) => {
      config[key] = value;
    });
  }

  function cookieConfig(): Record<string, unknown> {
    const cookies = configObject.value?.cookies_from_browser;
    return isRecord(cookies) ? cookies : {};
  }

  function updateCookies(key: string, value: unknown) {
    updateConfig((config) => {
      const cookies = isRecord(config.cookies_from_browser) ? { ...config.cookies_from_browser } : {};
      cookies[key] = value;
      if (key === "mode" && value !== "custom") {
        delete cookies.value;
      }
      config.cookies_from_browser = cookies;
    });
  }

  function updateSub(index: number, key: string, value: unknown) {
    updateConfig((config) => {
      const items = Array.isArray(config.subs) ? [...config.subs] : [];
      const sub = isRecord(items[index]) ? { ...items[index] as Record<string, unknown> } : {};
      const oldId = String(sub.id || "").trim();
      sub[key] = value;
      if (key === "type") {
        applySubscriptionTypePayload(sub, String(value || "tvbox"), items, index);
      }
      if (key === "id" && String(sub.type || "") === "tvbox") {
        syncTvboxSiteKeyForSubscriptionId(sub, oldId, items, index);
      }
      if (key === "auth_mode" && value === "anonymous") {
        delete sub.access_code;
        sub.access_code_hash_action = "clear";
      }
      if (key === "auth_mode" && value === "access_code" && !accessCodeEditing(sub)) {
        sub.access_code_hash_action = sub.access_code_hash_set ? "keep" : "replace";
      }
      if (key === "access_code_hash_action" && value !== "replace") {
        delete sub.access_code;
      }
      items[index] = sub;
      config.subs = items;
    });
  }

  function addSubscription() {
    updateConfig((config) => {
      const items = Array.isArray(config.subs) ? [...config.subs] : [];
      const type = defaultSubscriptionType();
      const id = uniqueSubscriptionId(items);
      subscriptionDraftKeys.value = [nextSubscriptionDraftKey(), ...subscriptionDraftKeys.value];
      items.unshift({
        id,
        type,
        auth_mode: "anonymous",
        ...defaultSubscriptionPayload(type, id, items)
      });
      config.subs = items;
    });
  }

  function defaultSubscriptionType() {
    return locale.value === "zh-CN" ? "tvbox" : "kodi";
  }

  function requestDeleteSubscription(index: number, sub: Record<string, unknown>) {
    pendingDeleteSubscriptionIndex.value = index;
    pendingDeleteSubscriptionLabel.value = String(sub.id || `sub-${index + 1}`);
    deleteConfirmOpen.value = true;
  }

  function cancelDeleteSubscription() {
    deleteConfirmOpen.value = false;
    pendingDeleteSubscriptionIndex.value = null;
    pendingDeleteSubscriptionLabel.value = "";
  }

  function confirmDeleteSubscription() {
    const index = pendingDeleteSubscriptionIndex.value;
    if (index === null) return;
    const cardKey = subscriptionCardKey(index);
    updateConfig((config) => {
      const items = Array.isArray(config.subs) ? [...config.subs] : [];
      items.splice(index, 1);
      subscriptionDraftKeys.value.splice(index, 1);
      clearSubscriptionDraftsForCard(cardKey);
      config.subs = items;
    });
    cancelDeleteSubscription();
  }

  function sourcesForSub(sub: Record<string, unknown>) {
    const payload = activeSubscriptionPayload(sub);
    return Array.isArray(payload.sources) ? payload.sources.filter(isRecord).map(cloneRecord) : [];
  }

  function openSourceEditor(index: number, sub: Record<string, unknown>) {
    sourceEditorSubscriptionIndex.value = index;
    sourceEditorDraft.value = sourcesForSub(sub);
    sourceEditorOpen.value = true;
  }

  function cancelSourceEditor() {
    sourceEditorOpen.value = false;
    sourceEditorSubscriptionIndex.value = null;
    sourceEditorDraft.value = [];
  }

  function updateSourceEditorDraft(value: Record<string, unknown>[]) {
    sourceEditorDraft.value = value.map(cloneRecord);
  }

  function applySourceEditor() {
    const index = sourceEditorSubscriptionIndex.value;
    if (index === null) return;
    updateConfig((config) => {
      const items = Array.isArray(config.subs) ? [...config.subs] : [];
      const sub = isRecord(items[index]) ? { ...items[index] as Record<string, unknown> } : {};
      const payloadKey = String(sub.type || "") === "kodi" ? "kodi" : "tvbox";
      const payload = isRecord(sub[payloadKey]) ? { ...sub[payloadKey] as Record<string, unknown> } : {};
      payload.sources = sourceEditorDraft.value.map(cloneRecord);
      sub[payloadKey] = payload;
      items[index] = sub;
      config.subs = items;
    });
    cancelSourceEditor();
  }

  function isSavedSubscription(sub: Record<string, unknown>) {
    const id = String(sub.id || "").trim();
    return Boolean(id) && savedSubscriptionIds.value.has(id);
  }

  function subscriptionIds(value: unknown) {
    const ids = new Set<string>();
    if (!Array.isArray(value)) return ids;
    for (const item of value) {
      if (!isRecord(item)) continue;
      const id = String(item.id || "").trim();
      if (id) ids.add(id);
    }
    return ids;
  }

  function uniqueSubscriptionId(items: unknown[]) {
    const existing = new Set(
      items
        .filter(isRecord)
        .map((item) => String(item.id || "").trim())
        .filter(Boolean)
    );
    const base = "new-subscription";
    if (!existing.has(base)) return base;
    for (let suffix = 2; ; suffix += 1) {
      const candidate = `${base}-${suffix}`;
      if (!existing.has(candidate)) return candidate;
    }
  }

  function defaultSubscriptionPayload(type: string, subId = "", items: unknown[] = [], currentIndex = -1): Record<string, unknown> {
    return type === "kodi"
      ? { kodi: { sources: [] } }
      : {
          tvbox: {
            site_key: uniqueTvboxSiteKey(subId, items, currentIndex),
            site_name: "Dashbox",
            sources: [],
            video_codec_preferences: defaultCodecPreferences(videoCodecOptions.value),
            audio_codec_preferences: defaultCodecPreferences(audioCodecOptions.value)
          }
        };
  }

  function applySubscriptionTypePayload(sub: Record<string, unknown>, type: string, items: unknown[] = [], currentIndex = -1) {
    delete sub.tvbox;
    delete sub.kodi;
    Object.assign(sub, defaultSubscriptionPayload(type, String(sub.id || ""), items, currentIndex));
  }

  function slugId(value: string, fallback: string) {
    const normalized = String(value || "")
      .toLowerCase()
      .replace(/[^a-z0-9_-]+/g, "_")
      .replace(/_+/g, "_")
      .replace(/^[_-]+|[_-]+$/g, "");
    return normalized && /^[a-z0-9]/.test(normalized) ? normalized.slice(0, 48) : fallback;
  }

  function tvboxSiteKeyForSubId(subId: string) {
    return `dashbox_${slugId(subId, "subscription")}`;
  }

  function existingTvboxSiteKeys(items: unknown[], currentIndex: number) {
    const keys = new Set<string>();
    for (const [itemIndex, item] of items.entries()) {
      if (itemIndex === currentIndex || !isRecord(item) || String(item.type || "") !== "tvbox") continue;
      const tvbox = isRecord(item.tvbox) ? item.tvbox : {};
      const key = String(tvbox.site_key || "").trim();
      if (key) keys.add(key);
    }
    return keys;
  }

  function uniqueTvboxSiteKey(subId: string, items: unknown[], currentIndex = -1) {
    const used = existingTvboxSiteKeys(items, currentIndex);
    const base = tvboxSiteKeyForSubId(subId);
    if (!used.has(base)) return base;
    for (let suffix = 2; ; suffix += 1) {
      const candidate = `${base}_${suffix}`;
      if (!used.has(candidate)) return candidate;
    }
  }

  function syncTvboxSiteKeyForSubscriptionId(
    sub: Record<string, unknown>,
    oldId: string,
    items: unknown[],
    currentIndex: number
  ) {
    const tvbox = isRecord(sub.tvbox) ? { ...sub.tvbox } : {};
    const currentSiteKey = String(tvbox.site_key || "").trim();
    const oldDefaultSiteKey = tvboxSiteKeyForSubId(oldId);
    if (!currentSiteKey || currentSiteKey === "dashbox" || currentSiteKey === oldDefaultSiteKey) {
      tvbox.site_key = uniqueTvboxSiteKey(String(sub.id || ""), items, currentIndex);
      sub.tvbox = tvbox;
    }
  }

  function subscriptionPayload(sub: Record<string, unknown>, payloadKey: "tvbox" | "kodi") {
    const payload = sub[payloadKey];
    return isRecord(payload) ? payload : {};
  }

  function activeSubscriptionPayload(sub: Record<string, unknown>) {
    return subscriptionPayload(sub, String(sub.type || "") === "kodi" ? "kodi" : "tvbox");
  }

  function ytdlpSearchPrefix(payload: Record<string, unknown>) {
    return isRecord(payload.ytdlp_search_prefix) ? payload.ytdlp_search_prefix : {};
  }

  function schemaDefaultString(key: string) {
    const value = schema.value?.defaults[key];
    return typeof value === "string" ? value : null;
  }

  function schemaDefaultObject(key: string) {
    const value = schema.value?.defaults[key];
    return isRecord(value) ? value : {};
  }

  function effectivePayloadString(payload: Record<string, unknown>, key: string, fallback: string | null) {
    const value = payload[key];
    return value === undefined || value === null || value === "" ? fallback : String(value);
  }

  function effectivePrefixMode(payload: Record<string, unknown>) {
    if (isRecord(payload.ytdlp_search_prefix)) {
      return String(ytdlpSearchPrefix(payload).mode || "");
    }
    return String(schemaDefaultObject("ytdlp_search_prefix").mode || "");
  }

  function effectivePrefixValue(payload: Record<string, unknown>) {
    if (isRecord(payload.ytdlp_search_prefix)) {
      return String(ytdlpSearchPrefix(payload).value || "");
    }
    return String(schemaDefaultObject("ytdlp_search_prefix").value || "");
  }

  function effectivePayloadNumber(payload: Record<string, unknown>, key: string, fallback: number | null) {
    return payload[key] === undefined ? fallback : Number(payload[key]);
  }

  function schemaDefaultNumber(key: string) {
    const value = schema.value?.defaults[key];
    return typeof value === "number" ? value : null;
  }

  function defaultCodecPreferences(options: SelectOption[]) {
    return options.map((option) => ({ codec: option.value, enabled: true }));
  }

  function codecPreferenceItems(payload: Record<string, unknown>, key: string, options: SelectOption[]) {
    const rawItems = Array.isArray(payload[key]) ? payload[key] : defaultCodecPreferences(options);
    const optionsByValue = new Map(options.map((option) => [option.value, option.label]));
    const seen = new Set<string>();
    const items: CodecOrderItem[] = [];

    for (const item of rawItems) {
      if (!isRecord(item)) {
        continue;
      }
      const value = String(item.codec || "");
      const label = optionsByValue.get(value);
      if (!label || seen.has(value)) {
        continue;
      }
      items.push({ label, value, enabled: Boolean(item.enabled) });
      seen.add(value);
    }

    for (const option of options) {
      if (!seen.has(option.value)) {
        items.push({ ...option, enabled: false });
        seen.add(option.value);
      }
    }

    return items;
  }

  function codecPreferencePayload(items: CodecOrderItem[]) {
    return items.map((item) => ({ codec: item.value, enabled: item.enabled }));
  }

  function updateSubPayload(
    index: number,
    payloadKey: "tvbox" | "kodi",
    key: string,
    value: unknown,
    options: { deleteEmpty?: boolean } = {}
  ) {
    updateConfig((config) => {
      const items = Array.isArray(config.subs) ? [...config.subs] : [];
      const sub = isRecord(items[index]) ? { ...items[index] as Record<string, unknown> } : {};
      const payload = isRecord(sub[payloadKey]) ? { ...sub[payloadKey] as Record<string, unknown> } : {};
      if (options.deleteEmpty && (value === null || value === undefined || value === "")) {
        delete payload[key];
      } else {
        payload[key] = value;
      }
      sub[payloadKey] = payload;
      items[index] = sub;
      config.subs = items;
    });
  }

  function updateSubPrefix(
    index: number,
    payloadKey: "tvbox" | "kodi",
    key: "mode" | "value",
    value: unknown
  ) {
    updateConfig((config) => {
      const items = Array.isArray(config.subs) ? [...config.subs] : [];
      const sub = isRecord(items[index]) ? { ...items[index] as Record<string, unknown> } : {};
      const payload = isRecord(sub[payloadKey]) ? { ...sub[payloadKey] as Record<string, unknown> } : {};
      if (key === "mode" && (value === null || value === undefined || value === "")) {
        delete payload.ytdlp_search_prefix;
      } else {
        const prefix = isRecord(payload.ytdlp_search_prefix) ? { ...payload.ytdlp_search_prefix } : {};
        prefix[key] = value;
        if (key === "mode" && value !== "custom") {
          delete prefix.value;
        }
        payload.ytdlp_search_prefix = prefix;
      }
      sub[payloadKey] = payload;
      items[index] = sub;
      config.subs = items;
    });
  }

  function accessCodeEditing(sub: Record<string, unknown>) {
    return String(sub.access_code_hash_action || "") === "replace";
  }

  function accessCodeToggleLabel(sub: Record<string, unknown>) {
    return accessCodeEditing(sub) ? t("subscriptions.cancelAccessCodeEdit") : t("subscriptions.editAccessCode");
  }

  function toggleAccessCodeEdit(index: number, sub: Record<string, unknown>) {
    updateSub(index, "access_code_hash_action", accessCodeEditing(sub) ? "keep" : "replace");
  }

  function configWithEmptyAccessCodeEditsKept(config: Record<string, unknown>) {
    const subs = Array.isArray(config.subs) ? config.subs : [];
    const nextSubs = subs.map((item) => {
      if (!isRecord(item)) return item;
      if (
        String(item.access_code_hash_action || "") !== "replace" ||
        !item.access_code_hash_set ||
        String(item.access_code || "").trim()
      ) {
        return item;
      }
      const sub = { ...item };
      delete sub.access_code;
      sub.access_code_hash_action = "keep";
      return sub;
    });
    return nextSubs.some((item, index) => item !== subs[index]) ? { ...config, subs: nextSubs } : config;
  }

  function subscriptionTreeNode(sub: Record<string, unknown>, index: number): TreeOption {
    const subId = String(sub.id || `sub-${index}`);
    const subType = String(sub.type || "");
    const payload = isRecord(subType === "kodi" ? sub.kodi : sub.tvbox) ? subType === "kodi" ? sub.kodi : sub.tvbox : {};
    const rawSources = isRecord(payload) && Array.isArray(payload.sources) ? payload.sources : [];
    const children = subType === "tvbox"
      ? rawSources.filter(isRecord).map((source, sourceIndex) => ({
          key: `${subId}:source:${sourceIndex}`,
          label: labelWithId(String(source.name || source.id || "source"), source.id),
          children: Array.isArray(source.items)
            ? source.items.filter(isRecord).map((item, itemIndex) => itemTreeNode(item, `${subId}:source:${sourceIndex}:${itemIndex}`))
            : []
        }))
      : rawSources.filter(isRecord).map((item, itemIndex) => itemTreeNode(item, `${subId}:kodi:${itemIndex}`));

    return {
      key: `${subId}:${index}`,
      label: `${subId} (${subType || "unknown"})`,
      children
    };
  }

  function sourceNodesForSub(sub: Record<string, unknown>, index: number): TreeOption[] {
    return subscriptionTreeNode(sub, index).children || [];
  }

  function subscriptionCardTitle(sub: Record<string, unknown>, index: number) {
    const id = String(sub.id || `sub-${index + 1}`).trim();
    const type = String(sub.type || "unknown").trim();
    return `${id} · ${displayLabel("subscriptionType", type) || type}`;
  }

  function itemTreeNode(item: Record<string, unknown>, key: string): TreeOption {
    const isFolder = Array.isArray(item.items);
    const title = isFolder ? String(item.name || item.id || "folder") : String(item.title || item.url || item.id || "url");
    return {
      key,
      label: isFolder ? labelWithId(title, item.id) : labelWithId(title, item.id),
      url: !isFolder && typeof item.url === "string" ? item.url : undefined,
      children: isFolder ? (item.items as unknown[]).filter(isRecord).map((child, index) => itemTreeNode(child, `${key}:${index}`)) : undefined
    };
  }

  function cloneRecord<T extends Record<string, unknown>>(value: T): T {
    return JSON.parse(JSON.stringify(value)) as T;
  }

  function labelWithId(label: string, id: unknown) {
    const value = String(id || "");
    return value ? `${label} [${value}]` : label;
  }

  async function load() {
    loading.value = true;
    try {
      const [configData, schemaData] = await Promise.all([readConfig(), readSchema()]);
      fill(configData);
      schema.value = schemaData;
    } catch (error) {
      message.error(error instanceof Error ? error.message : t("config.readFailed"));
    } finally {
      loading.value = false;
    }
  }

  async function validate() {
    const parsed = parseEditor();
    const config = parsed ? configWithEmptyAccessCodeEditsKept(parsed) : null;
    if (!config) return;
    const result = await validateConfig(config);
    if (result.ok) message.success(t("config.valid"));
  }

  async function normalizeForSave() {
    const parsed = parseEditor();
    const config = parsed ? configWithEmptyAccessCodeEditsKept(parsed) : null;
    if (!config) return null;
    const result = await normalizeConfig(config);
    editor.value = JSON.stringify(result.config, null, 2);
    return result.config;
  }

  async function prepareSave() {
    saving.value = true;
    try {
      const normalized = await normalizeForSave();
      if (!normalized) return;
      pendingSaveConfig.value = normalized;
      saveConfirmOpen.value = true;
    } catch (error) {
      message.error(error instanceof Error ? error.message : t("config.saveFailed"));
    } finally {
      saving.value = false;
    }
  }

  async function confirmSave() {
    if (!pendingSaveConfig.value) return;
    saving.value = true;
    try {
      const result = await saveConfig(pendingSaveConfig.value);
      fill(result);
      saveConfirmOpen.value = false;
      pendingSaveConfig.value = null;
      message.success(t("config.saved"));
    } catch (error) {
      message.error(error instanceof Error ? error.message : t("config.saveFailed"));
    } finally {
      saving.value = false;
    }
  }

  onMounted(load);

  watch(
    () => subs.value.length,
    (length) => reconcileSubscriptionDraftKeys(length),
    { immediate: true }
  );

  return {
    loading,
    saving,
    schema,
    editor,
    lastError,
    saveConfirmOpen,
    pendingSaveConfig,
    deleteConfirmOpen,
    pendingDeleteSubscriptionIndex,
    pendingDeleteSubscriptionLabel,
    showJsonEditor,
    sourceEditorOpen,
    sourceEditorSubscriptionIndex,
    sourceEditorDraft,
    effectiveValues,
    savedSubscriptionIds,
    configObject,
    subs,
    effectiveUserAgent,
    logLevelOptions,
    cookieModeOptions,
    authModeOptions,
    subscriptionTypeOptions,
    searchProviderOptions,
    ytdlpSearchPrefixModeOptions,
    vodStyleOptions,
    tvboxLocaleOptions,
    videoCodecOptions,
    audioCodecOptions,
    maxVideoHeightOptions,
    maxVideoFpsOptions,
    isRecord,
    selectOptions,
    numberOptions,
    parseEditorSilently,
    parseEditor,
    fill,
    writeConfig,
    updateConfig,
    updateGlobal,
    cookieConfig,
    updateCookies,
    updateSub,
    addSubscription,
    requestDeleteSubscription,
    cancelDeleteSubscription,
    confirmDeleteSubscription,
    sourcesForSub,
    openSourceEditor,
    cancelSourceEditor,
    updateSourceEditorDraft,
    applySourceEditor,
    isSavedSubscription,
    subscriptionIds,
    uniqueSubscriptionId,
    defaultSubscriptionPayload,
    applySubscriptionTypePayload,
    slugId,
    tvboxSiteKeyForSubId,
    existingTvboxSiteKeys,
    uniqueTvboxSiteKey,
    syncTvboxSiteKeyForSubscriptionId,
    subscriptionPayload,
    activeSubscriptionPayload,
    ytdlpSearchPrefix,
    schemaDefaultString,
    schemaDefaultObject,
    effectivePayloadString,
    effectivePrefixMode,
    effectivePrefixValue,
    effectivePayloadNumber,
    schemaDefaultNumber,
    defaultCodecPreferences,
    codecPreferenceItems,
    codecPreferencePayload,
    updateSubPayload,
    updateSubPrefix,
    accessCodeEditing,
    accessCodeToggleLabel,
    toggleAccessCodeEdit,
    configWithEmptyAccessCodeEditsKept,
    subscriptionTreeNode,
    sourceNodesForSub,
    subscriptionCardTitle,
    subscriptionCardKey,
    subscriptionPayloadNumberValue,
    updateSubscriptionPayloadNumber,
    clearSubscriptionPayloadNumberDraft,
    itemTreeNode,
    labelWithId,
    load,
    validate,
    prepareSave,
    confirmSave,
  };
}
