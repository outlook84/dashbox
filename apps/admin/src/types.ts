export interface SessionState {
  authenticated: boolean;
  setup_required: boolean;
}

export interface AdminStatus {
  ok: boolean;
  config_path: string;
  config_writable: boolean;
  project_url: string;
  version: string;
}

export interface ConfigResponse {
  config: Record<string, unknown>;
  config_path: string;
  env_overrides: Record<string, unknown>;
  effective_values?: Record<string, unknown>;
}

export interface NormalizeChange {
  path: string;
  field: string;
  value: unknown;
}

export interface NormalizeResponse {
  ok: boolean;
  config: Record<string, unknown>;
  changes: NormalizeChange[];
  warnings: string[];
}

export interface AdminSchema {
  schema_version: number;
  search_provider: string[];
  vod_style: string[];
  tvbox_locale: string[];
  video_codec: string[];
  audio_codec: string[];
  subscription_type: string[];
  auth_mode: string[];
  log_level: string[];
  cookies_from_browser_mode: string[];
  ytdlp_search_prefix_mode: string[];
  item_type: string[];
  max_video_height: number[];
  max_video_fps: number[];
  limits: Record<string, number>;
  defaults: Record<string, unknown>;
}

export interface ApiOk {
  ok: boolean;
  error?: string;
  detail?: string;
}

export interface CookieStatus {
  enabled: boolean;
  source: string;
  loaded: boolean;
  loaded_at: number | null;
  cookie_count: number;
  last_error: string;
  last_auto_reload_at: number | null;
  auto_reload_cooldown_seconds: number;
  reload_generation: number;
}

export interface SubscriptionSummary {
  id: string;
  type: string;
  auth_mode: string;
  access_code_hash_set?: boolean;
}
