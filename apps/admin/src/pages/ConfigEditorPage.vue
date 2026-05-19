<script setup lang="ts">
import { defineAsyncComponent, h, ref } from "vue";
import type { VNodeChild } from "vue";
import {
  NAlert,
  NButton,
  NCard,
  NCollapse,
  NCollapseItem,
  NForm,
  NFormItem,
  NGi,
  NGrid,
  NIcon,
  NInput,
  NInputNumber,
  NModal,
  NSelect,
  NSpace,
  NSwitch,
  NTabPane,
  NTabs,
  NTree,
  useMessage
} from "naive-ui";
import type { TreeOption } from "naive-ui";
import { ExternalLink, Pencil, Plus, RotateCcw, Trash2 } from "@lucide/vue";
import { t } from "../i18n";
import { displayLabel } from "../labels";
import { useConfigEditor } from "../composables/useConfigEditor";
import { safeWebUrl } from "../utils/url";

const JsonConfigEditor = defineAsyncComponent(() => import("../components/JsonConfigEditor.vue"));
const CodecOrderEditor = defineAsyncComponent(() => import("../components/CodecOrderEditor.vue"));
const FieldLabel = defineAsyncComponent(() => import("../components/FieldLabel.vue"));
const SourcesEditor = defineAsyncComponent(() => import("../components/SourcesEditor.vue"));
type SourcesEditorApplyResult = { ok: true } | { ok: false; error: string };
const message = useMessage();
const sourcesEditorRef = ref<{ applyDraft: () => SourcesEditorApplyResult } | null>(null);

const {
  loading,
  saving,
  schema,
  editor,
  lastError,
  saveConfirmOpen,
  deleteConfirmOpen,
  pendingDeleteSubscriptionLabel,
  showJsonEditor,
  sourceEditorOpen,
  sourceEditorSubscriptionIndex,
  sourceEditorDraft,
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
  updateGlobal,
  cookieConfig,
  updateCookies,
  updateSub,
  addSubscription,
  requestDeleteSubscription,
  cancelDeleteSubscription,
  confirmDeleteSubscription,
  openSourceEditor,
  cancelSourceEditor,
  updateSourceEditorDraft,
  applySourceEditor,
  isSavedSubscription,
  subscriptionPayload,
  activeSubscriptionPayload,
  schemaDefaultString,
  effectivePayloadString,
  effectivePrefixMode,
  effectivePrefixValue,
  schemaDefaultNumber,
  codecPreferenceItems,
  codecPreferencePayload,
  updateSubPayload,
  updateSubPrefix,
  accessCodeEditing,
  accessCodeToggleLabel,
  toggleAccessCodeEdit,
  sourceNodesForSub,
  subscriptionCardTitle,
  subscriptionCardKey,
  subscriptionPayloadNumberValue,
  updateSubscriptionPayloadNumber,
  clearSubscriptionPayloadNumberDraft,
  load,
  validate,
  prepareSave,
  confirmSave,
} = useConfigEditor(message);

function applySourcesEditor() {
  const result = sourcesEditorRef.value?.applyDraft();
  if (result && !result.ok) {
    message.error(result.error);
    return;
  }
  applySourceEditor();
}

function currentSourceEditorType(): string {
  const index = sourceEditorSubscriptionIndex.value;
  const sub = index === null ? null : subs.value[index];
  return String(sub?.type || "tvbox");
}

function currentSourceEditorTitle(): string {
  const index = sourceEditorSubscriptionIndex.value;
  if (index === null) return t("sources.edit");
  const sub = subs.value[index];
  return sub ? `${t("sources.edit")} · ${subscriptionCardTitle(sub, index)}` : t("sources.edit");
}

function subscriptionConfigKey(sub: Record<string, unknown>): "kodi" | "tvbox" {
  return String(sub.type || "") === "kodi" ? "kodi" : "tvbox";
}

function effectiveSearchProvider(payload: Record<string, unknown>): string {
  return effectivePayloadString(payload, "search_provider", schemaDefaultString("default_search_provider")) || "";
}

function usesBilibiliSearchProvider(payload: Record<string, unknown>): boolean {
  return effectiveSearchProvider(payload) === "bilibili";
}

function searchResultLimitTooltip(payload: Record<string, unknown>): string {
  return usesBilibiliSearchProvider(payload) ? t("tooltips.bilibili_search_limit") : t("tooltips.ytdlp_search_limit");
}

function renderSourceTreeLabel({ option }: { option: TreeOption }): VNodeChild {
  const label = h("span", { class: "source-tree-label-text" }, String(option.label || ""));
  const url = safeWebUrl(option.url);
  if (!url) {
    return h("span", { class: "source-tree-label" }, [label]);
  }
  return h("span", { class: "source-tree-label source-tree-label-with-action" }, [
    h(
      "a",
      {
        class: "source-tree-open-link",
        href: url,
        target: "_blank",
        rel: "noopener noreferrer",
        title: t("config.openUrl"),
        "aria-label": t("config.openUrl"),
        onClick: (event: MouseEvent) => event.stopPropagation()
      },
      [
        h(
          NIcon,
          { size: 14 },
          {
            default: () => h(ExternalLink)
          }
        )
      ]
    ),
    label
  ]);
}
</script>

<template>
  <div class="page-stack config-page">
    <div class="page-heading">
      <span v-if="schema" class="page-heading-meta">{{ t("config.schema") }} v{{ schema.schema_version }}</span>
      <NSpace>
        <NButton @click="showJsonEditor = !showJsonEditor">
          {{ showJsonEditor ? t("config.showForm") : t("config.showJson") }}
        </NButton>
        <NButton :loading="loading" @click="load">{{ t("common.refresh") }}</NButton>
        <NButton @click="validate">{{ t("config.validate") }}</NButton>
        <NButton type="primary" :loading="saving" @click="prepareSave">{{ t("common.save") }}</NButton>
      </NSpace>
    </div>

    <NAlert v-if="lastError" type="error" :show-icon="false">{{ lastError }}</NAlert>

    <JsonConfigEditor v-if="showJsonEditor" v-model="editor" class="config-json-editor" />

    <NCard v-if="!showJsonEditor" size="small">
      <NCollapse :default-expanded-names="['global-settings']">
        <NCollapseItem :title="t('config.globalSettings')" name="global-settings">
          <NForm label-placement="top">
            <NGrid cols="1 s:2 m:3" :x-gap="16" responsive="screen">
              <NGi>
                <NFormItem>
                  <template #label>
                    <FieldLabel :label="t('config.logLevel')" :tooltip="t('tooltips.log_level')" />
                  </template>
                  <NSelect
                    :value="String(configObject?.log_level || '')"
                    :options="logLevelOptions"
                    @update:value="(value) => updateGlobal('log_level', value)"
                  />
                </NFormItem>
              </NGi>
              <NGi>
                <NFormItem>
                  <template #label>
                    <FieldLabel :label="t('config.ytdlpConcurrency')" :tooltip="t('tooltips.ytdlp_concurrency')" />
                  </template>
                  <NInputNumber
                    :value="Number(configObject?.ytdlp_concurrency || 0)"
                    :min="1"
                    :max="schema?.limits.max_ytdlp_concurrency"
                    @update:value="(value) => updateGlobal('ytdlp_concurrency', value || 1)"
                  />
                </NFormItem>
              </NGi>
              <NGi>
                <NFormItem>
                  <template #label>
                    <FieldLabel :label="t('config.proxyIdleTtl')" :tooltip="t('tooltips.proxy_media_idle_ttl_seconds')" />
                  </template>
                  <NInputNumber
                    :value="Number(configObject?.proxy_media_idle_ttl_seconds || 0)"
                    :min="1"
                    :max="schema?.limits.max_proxy_media_idle_ttl_seconds"
                    @update:value="(value) => updateGlobal('proxy_media_idle_ttl_seconds', value || 1)"
                  />
                </NFormItem>
              </NGi>
              <NGi>
                <NFormItem>
                  <template #label>
                    <FieldLabel :label="t('config.proxyDashMediaUrl')" :tooltip="t('tooltips.proxy_dash_media_url')" />
                  </template>
                  <NSwitch
                    :value="Boolean(configObject?.proxy_dash_media_url)"
                    @update:value="(value) => updateGlobal('proxy_dash_media_url', value)"
                  />
                </NFormItem>
              </NGi>
              <NGi>
                <NFormItem>
                  <template #label>
                    <FieldLabel :label="t('config.cookiesMode')" :tooltip="t('tooltips.cookies_from_browser.mode')" />
                  </template>
                  <NSelect
                    :value="String(cookieConfig().mode || '')"
                    :options="cookieModeOptions"
                    @update:value="(value) => updateCookies('mode', value)"
                  />
                </NFormItem>
              </NGi>
              <NGi>
                <NFormItem>
                  <template #label>
                    <FieldLabel :label="t('config.cookiesValue')" :tooltip="t('tooltips.cookies_from_browser.value')" />
                  </template>
                  <NInput
                    :value="String(cookieConfig().value || '')"
                    :disabled="cookieConfig().mode !== 'custom'"
                    @update:value="(value) => updateCookies('value', value)"
                  />
                </NFormItem>
              </NGi>
            </NGrid>
            <NFormItem>
              <template #label>
                <FieldLabel :label="t('config.userAgent')" :tooltip="t('tooltips.user_agent')" />
              </template>
              <div class="user-agent-field">
                <NInput
                  :value="String(configObject?.user_agent || '')"
                  @update:value="(value) => updateGlobal('user_agent', value)"
                />
                <div v-if="effectiveUserAgent" class="form-hint">
                  {{ t("config.effectiveUserAgent") }}: {{ effectiveUserAgent }}
                </div>
              </div>
            </NFormItem>
          </NForm>
        </NCollapseItem>
      </NCollapse>
    </NCard>

    <NCard v-if="!showJsonEditor" size="small" :title="t('config.subscriptions')">
      <template #header-extra>
        <NButton secondary type="primary" @click="addSubscription">
          <template #icon>
            <NIcon>
              <Plus />
            </NIcon>
          </template>
          {{ t("subscriptions.add") }}
        </NButton>
      </template>
      <div class="subscription-form-list">
        <NCard v-for="(sub, index) in subs" :key="subscriptionCardKey(index)" size="small" embedded class="subscription-card">
          <NCollapse :default-expanded-names="[`subscription-${index}`]">
            <NCollapseItem :title="subscriptionCardTitle(sub, index)" :name="`subscription-${index}`">
              <template #header-extra>
                <NButton
                  circle
                  quaternary
                  type="error"
                  :title="t('subscriptions.delete')"
                  :aria-label="t('subscriptions.delete')"
                  @click.stop="requestDeleteSubscription(index, sub)"
                >
                  <NIcon size="18">
                    <Trash2 />
                  </NIcon>
                </NButton>
              </template>
              <NForm label-placement="top">
                <NGrid cols="1 s:2 m:4" :x-gap="16" responsive="screen">
              <NGi>
                <NFormItem>
                  <template #label>
                    <FieldLabel :label="t('subscriptions.id')" :tooltip="t('tooltips.sub.id')" />
                  </template>
                  <NInput :value="String(sub.id || '')" @update:value="(value) => updateSub(index, 'id', value)" />
                </NFormItem>
              </NGi>
              <NGi>
                <NFormItem>
                  <template #label>
                    <FieldLabel :label="t('subscriptions.type')" :tooltip="t('tooltips.sub.type')" />
                  </template>
                  <NInput v-if="isSavedSubscription(sub)" :value="displayLabel('subscriptionType', sub.type)" disabled />
                  <NSelect
                    v-else
                    :value="String(sub.type || '')"
                    :options="subscriptionTypeOptions"
                    @update:value="(value) => updateSub(index, 'type', value)"
                  />
                </NFormItem>
              </NGi>
              <NGi>
                <NFormItem>
                  <template #label>
                    <FieldLabel :label="t('subscriptions.auth')" :tooltip="t('tooltips.sub.auth_mode')" />
                  </template>
                  <NSelect
                    :value="String(sub.auth_mode || '')"
                    :options="authModeOptions"
                    @update:value="(value) => updateSub(index, 'auth_mode', value)"
                  />
                </NFormItem>
              </NGi>
              <NGi>
                <NFormItem>
                  <template #label>
                    <FieldLabel :label="t('subscriptions.accessCode')" :tooltip="t('tooltips.sub.access_code')" />
                  </template>
                  <div class="access-code-edit-field">
                    <NButton
                      circle
                      secondary
                      :disabled="sub.auth_mode === 'anonymous'"
                      :title="accessCodeToggleLabel(sub)"
                      :aria-label="accessCodeToggleLabel(sub)"
                      @click="toggleAccessCodeEdit(index, sub)"
                    >
                      <NIcon size="18">
                        <RotateCcw v-if="accessCodeEditing(sub)" />
                        <Pencil v-else />
                      </NIcon>
                    </NButton>
                    <NInput
                      v-if="accessCodeEditing(sub)"
                      :value="String(sub.access_code || '')"
                      type="password"
                      :placeholder="t('subscriptions.newAccessCode')"
                      @update:value="(value) => updateSub(index, 'access_code', value)"
                    />
                  </div>
                </NFormItem>
              </NGi>
                </NGrid>
              </NForm>
              <NTabs type="line" animated class="subscription-tabs">
            <NTabPane :tab="t('subscriptions.commonSettings')" :name="`common-${index}`">
              <NForm label-placement="top">
                <NGrid cols="1 s:2 m:3" :x-gap="16" responsive="screen">
                  <NGi>
                    <NFormItem>
                      <template #label>
                        <FieldLabel :label="t('subscriptions.searchMethod')" :tooltip="t('tooltips.search_provider')" />
                      </template>
                      <NSelect
                        clearable
                        :value="effectiveSearchProvider(activeSubscriptionPayload(sub))"
                        :options="searchProviderOptions"
                        @update:value="(value) => updateSubPayload(index, subscriptionConfigKey(sub), 'search_provider', value, { deleteEmpty: true })"
                      />
                    </NFormItem>
                  </NGi>
                  <NGi v-if="!usesBilibiliSearchProvider(activeSubscriptionPayload(sub))">
                    <NFormItem>
                      <template #label>
                        <FieldLabel :label="t('subscriptions.searchTarget')" :tooltip="t('tooltips.ytdlp_search_prefix.mode')" />
                      </template>
                      <NSelect
                        clearable
                        :value="effectivePrefixMode(activeSubscriptionPayload(sub))"
                        :options="ytdlpSearchPrefixModeOptions"
                        @update:value="(value) => updateSubPrefix(index, subscriptionConfigKey(sub), 'mode', value)"
                      />
                    </NFormItem>
                  </NGi>
                  <NGi v-if="!usesBilibiliSearchProvider(activeSubscriptionPayload(sub)) && effectivePrefixMode(activeSubscriptionPayload(sub)) === 'custom'">
                    <NFormItem>
                      <template #label>
                        <FieldLabel :label="t('subscriptions.ytdlpSearchPrefixValue')" :tooltip="t('tooltips.ytdlp_search_prefix.value')" />
                      </template>
                      <NInput
                        :value="effectivePrefixValue(activeSubscriptionPayload(sub))"
                        @update:value="(value) => updateSubPrefix(index, subscriptionConfigKey(sub), 'value', value)"
                      />
                    </NFormItem>
                  </NGi>
                  <NGi>
                    <NFormItem>
                      <template #label>
                        <FieldLabel
                          :label="t('subscriptions.searchResultLimit')"
                          :tooltip="searchResultLimitTooltip(activeSubscriptionPayload(sub))"
                        />
                      </template>
                      <NInputNumber
                        v-if="usesBilibiliSearchProvider(activeSubscriptionPayload(sub))"
                        clearable
                        :value="
                          subscriptionPayloadNumberValue(
                            index,
                            activeSubscriptionPayload(sub),
                            subscriptionConfigKey(sub),
                            'bilibili_search_limit',
                            schemaDefaultNumber('bilibili_search_limit')
                          )
                        "
                        :min="0"
                        :max="schema?.limits.max_search_limit"
                        @update:value="(value) => updateSubscriptionPayloadNumber(index, subscriptionConfigKey(sub), 'bilibili_search_limit', value)"
                        @blur="clearSubscriptionPayloadNumberDraft(index, subscriptionConfigKey(sub), 'bilibili_search_limit')"
                      />
                      <NInputNumber
                        v-else
                        clearable
                        :value="
                          subscriptionPayloadNumberValue(
                            index,
                            activeSubscriptionPayload(sub),
                            subscriptionConfigKey(sub),
                            'ytdlp_search_limit',
                            schemaDefaultNumber('ytdlp_search_limit')
                          )
                        "
                        :min="0"
                        :max="schema?.limits.max_search_limit"
                        @update:value="(value) => updateSubscriptionPayloadNumber(index, subscriptionConfigKey(sub), 'ytdlp_search_limit', value)"
                        @blur="clearSubscriptionPayloadNumberDraft(index, subscriptionConfigKey(sub), 'ytdlp_search_limit')"
                      />
                    </NFormItem>
                  </NGi>
                  <NGi>
                    <NFormItem>
                      <template #label>
                        <FieldLabel :label="t('subscriptions.playlistLimit')" :tooltip="t('tooltips.playlist_limit')" />
                      </template>
                      <NInputNumber
                        clearable
                        :value="
                          subscriptionPayloadNumberValue(
                            index,
                            activeSubscriptionPayload(sub),
                            subscriptionConfigKey(sub),
                            'playlist_limit',
                            schemaDefaultNumber('playlist_limit')
                          )
                        "
                        :min="0"
                        :max="schema?.limits.max_list_limit"
                        @update:value="(value) => updateSubscriptionPayloadNumber(index, subscriptionConfigKey(sub), 'playlist_limit', value)"
                        @blur="clearSubscriptionPayloadNumberDraft(index, subscriptionConfigKey(sub), 'playlist_limit')"
                      />
                    </NFormItem>
                  </NGi>
                  <NGi>
                    <NFormItem>
                      <template #label>
                        <FieldLabel :label="t('subscriptions.bilibiliListLimit')" :tooltip="t('tooltips.bilibili_list_limit')" />
                      </template>
                      <NInputNumber
                        clearable
                        :value="
                          subscriptionPayloadNumberValue(
                            index,
                            activeSubscriptionPayload(sub),
                            subscriptionConfigKey(sub),
                            'bilibili_list_limit',
                            schemaDefaultNumber('bilibili_list_limit')
                          )
                        "
                        :min="0"
                        :max="schema?.limits.max_list_limit"
                        @update:value="(value) => updateSubscriptionPayloadNumber(index, subscriptionConfigKey(sub), 'bilibili_list_limit', value)"
                        @blur="clearSubscriptionPayloadNumberDraft(index, subscriptionConfigKey(sub), 'bilibili_list_limit')"
                      />
                    </NFormItem>
                  </NGi>
                </NGrid>
              </NForm>
            </NTabPane>
            <NTabPane
              v-if="String(sub.type || '') === 'tvbox'"
              :tab="t('subscriptions.tvboxSettings')"
              :name="`tvbox-${index}`"
            >
              <NForm label-placement="top">
                <NGrid cols="1 s:2 m:3" :x-gap="16" responsive="screen">
                  <NGi>
                    <NFormItem>
                      <template #label>
                        <FieldLabel :label="t('subscriptions.siteName')" :tooltip="t('tooltips.site_name')" />
                      </template>
                      <NInput
                        :value="String(subscriptionPayload(sub, 'tvbox').site_name || '')"
                        @update:value="(value) => updateSubPayload(index, 'tvbox', 'site_name', value || 'Dashbox')"
                      />
                    </NFormItem>
                  </NGi>
                  <NGi>
                    <NFormItem>
                      <template #label>
                        <FieldLabel :label="t('subscriptions.locale')" :tooltip="t('tooltips.locale')" />
                      </template>
                      <NSelect
                        :value="String(subscriptionPayload(sub, 'tvbox').locale || 'zh-CN')"
                        :options="tvboxLocaleOptions"
                        @update:value="(value) => updateSubPayload(index, 'tvbox', 'locale', value)"
                      />
                    </NFormItem>
                  </NGi>
                  <NGi>
                    <NFormItem>
                      <template #label>
                        <FieldLabel :label="t('subscriptions.vodStyle')" :tooltip="t('tooltips.vod_style')" />
                      </template>
                      <NSelect
                        :value="String(subscriptionPayload(sub, 'tvbox').vod_style || 'list')"
                        :options="vodStyleOptions"
                        @update:value="(value) => updateSubPayload(index, 'tvbox', 'vod_style', value)"
                      />
                    </NFormItem>
                  </NGi>
                  <NGi>
                    <NFormItem>
                      <template #label>
                        <FieldLabel :label="t('subscriptions.maxVideoHeight')" :tooltip="t('tooltips.max_video_height')" />
                      </template>
                      <NSelect
                        :value="Number(subscriptionPayload(sub, 'tvbox').max_video_height || 0)"
                        :options="maxVideoHeightOptions"
                        @update:value="(value) => updateSubPayload(index, 'tvbox', 'max_video_height', value)"
                      />
                    </NFormItem>
                  </NGi>
                  <NGi>
                    <NFormItem>
                      <template #label>
                        <FieldLabel :label="t('subscriptions.maxVideoFps')" :tooltip="t('tooltips.max_video_fps')" />
                      </template>
                      <NSelect
                        :value="Number(subscriptionPayload(sub, 'tvbox').max_video_fps || 0)"
                        :options="maxVideoFpsOptions"
                        @update:value="(value) => updateSubPayload(index, 'tvbox', 'max_video_fps', value)"
                      />
                    </NFormItem>
                  </NGi>
                  <NGi>
                    <NFormItem>
                      <template #label>
                        <FieldLabel :label="t('subscriptions.youtubeSubtitles')" :tooltip="t('tooltips.youtube_subtitles')" />
                      </template>
                      <NSwitch
                        :value="Boolean(subscriptionPayload(sub, 'tvbox').youtube_subtitles)"
                        @update:value="(value) => updateSubPayload(index, 'tvbox', 'youtube_subtitles', value)"
                      />
                    </NFormItem>
                  </NGi>
                </NGrid>
                <NFormItem>
                  <template #label>
                    <FieldLabel :label="t('subscriptions.videoCodecOrder')" :tooltip="t('tooltips.video_codec_preferences')" />
                  </template>
                  <CodecOrderEditor
                    :model-value="
                      codecPreferenceItems(subscriptionPayload(sub, 'tvbox'), 'video_codec_preferences', videoCodecOptions)
                    "
                    @update:model-value="
                      (value) =>
                        updateSubPayload(index, 'tvbox', 'video_codec_preferences', codecPreferencePayload(value))
                    "
                  />
                </NFormItem>
                <NFormItem>
                  <template #label>
                    <FieldLabel :label="t('subscriptions.audioCodecOrder')" :tooltip="t('tooltips.audio_codec_preferences')" />
                  </template>
                  <CodecOrderEditor
                    :model-value="
                      codecPreferenceItems(subscriptionPayload(sub, 'tvbox'), 'audio_codec_preferences', audioCodecOptions)
                    "
                    @update:model-value="
                      (value) =>
                        updateSubPayload(index, 'tvbox', 'audio_codec_preferences', codecPreferencePayload(value))
                    "
                  />
                </NFormItem>
              </NForm>
            </NTabPane>
            <NTabPane :name="`sources-${index}`">
              <template #tab>
                <span class="sources-preview-tab">
                  <span>{{ t("config.sourcesPreview") }}</span>
                  <NButton
                    circle
                    quaternary
                    size="tiny"
                    :title="t('sources.edit')"
                    :aria-label="t('sources.edit')"
                    @click.stop="openSourceEditor(index, sub)"
                  >
                    <NIcon size="14">
                      <Pencil />
                    </NIcon>
                  </NButton>
                </span>
              </template>
              <NTree
                v-if="sourceNodesForSub(sub, index).length"
                block-line
                :data="sourceNodesForSub(sub, index)"
                :render-label="renderSourceTreeLabel"
              />
              <NAlert v-else type="default" :show-icon="false">{{ t("config.noSources") }}</NAlert>
            </NTabPane>
              </NTabs>
            </NCollapseItem>
          </NCollapse>
        </NCard>
        <NAlert v-if="!subs.length" type="default" :show-icon="false">{{ t("subscriptions.empty") }}</NAlert>
      </div>
    </NCard>

    <NModal
      v-model:show="deleteConfirmOpen"
      preset="dialog"
      type="warning"
      :title="t('subscriptions.delete')"
      :positive-text="t('common.delete')"
      :negative-text="t('common.cancel')"
      @positive-click="confirmDeleteSubscription"
      @negative-click="cancelDeleteSubscription"
      @close="cancelDeleteSubscription"
    >
      <p>{{ t("subscriptions.confirmDelete") }}</p>
      <p v-if="pendingDeleteSubscriptionLabel">{{ pendingDeleteSubscriptionLabel }}</p>
    </NModal>

    <NModal
      v-model:show="sourceEditorOpen"
      preset="card"
      :title="currentSourceEditorTitle()"
      class="sources-editor-modal"
      :bordered="false"
      @close="cancelSourceEditor"
    >
      <SourcesEditor
        ref="sourcesEditorRef"
        :model-value="sourceEditorDraft"
        :subscription-type="currentSourceEditorType()"
        @update:model-value="updateSourceEditorDraft"
      />
      <template #footer>
        <NSpace justify="end">
          <NButton @click="cancelSourceEditor">{{ t("common.cancel") }}</NButton>
          <NButton type="primary" @click="applySourcesEditor">{{ t("common.apply") }}</NButton>
        </NSpace>
      </template>
    </NModal>

    <NModal
      v-model:show="saveConfirmOpen"
      preset="dialog"
      type="warning"
      :title="t('common.save')"
      :positive-text="t('common.save')"
      :negative-text="t('common.cancel')"
      :loading="saving"
      @positive-click="confirmSave"
    >
      <p>{{ t("config.saveConfirm") }}</p>
    </NModal>
  </div>
</template>
