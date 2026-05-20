import { t, type MessageKey } from "./i18n";

export type LabelGroup =
  | "configField"
  | "imageProxyMode"
  | "authMode"
  | "subscriptionType"
  | "cookiesMode"
  | "ytdlpSearchPrefixMode"
  | "vodStyle"
  | "searchProvider";

const labelKeys: Record<LabelGroup, Record<string, MessageKey>> = {
  configField: {
    image_proxy_mode: "labels.configField.image_proxy_mode",
    proxy_media_idle_ttl_seconds: "labels.configField.proxy_media_idle_ttl_seconds",
    upstream_timeout: "labels.configField.upstream_timeout",
    public_base_url: "labels.configField.public_base_url"
  },
  imageProxyMode: {
    known: "labels.imageProxyMode.known",
    all: "labels.imageProxyMode.all",
    off: "labels.imageProxyMode.off"
  },
  authMode: {
    anonymous: "labels.authMode.anonymous",
    access_code: "labels.authMode.access_code"
  },
  subscriptionType: {
    tvbox: "labels.subscriptionType.tvbox",
    kodi: "labels.subscriptionType.kodi"
  },
  cookiesMode: {
    disabled: "labels.cookiesMode.disabled",
    firefox: "labels.cookiesMode.firefox",
    firefox_data_dir: "labels.cookiesMode.firefox_data_dir",
    chrome: "labels.cookiesMode.chrome",
    edge: "labels.cookiesMode.edge",
    brave: "labels.cookiesMode.brave",
    chromium: "labels.cookiesMode.chromium",
    custom: "labels.cookiesMode.custom"
  },
  ytdlpSearchPrefixMode: {
    youtube: "labels.ytdlpSearchPrefixMode.youtube",
    bilibili: "labels.ytdlpSearchPrefixMode.bilibili",
    soundcloud: "labels.ytdlpSearchPrefixMode.soundcloud",
    custom: "labels.ytdlpSearchPrefixMode.custom"
  },
  vodStyle: {
    list: "labels.vodStyle.list",
    landscape: "labels.vodStyle.landscape",
    portrait: "labels.vodStyle.portrait"
  },
  searchProvider: {
    ytdlp: "labels.searchProvider.ytdlp",
    bilibili: "labels.searchProvider.bilibili"
  }
};

export function displayLabel(group: LabelGroup, value: unknown) {
  const text = String(value || "");
  const key = labelKeys[group][text];
  return key ? t(key) : text;
}
