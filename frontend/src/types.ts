export interface Area {
  latitude: number;
  longitude: number;
  radius_m: number;
}
export interface Observation {
  observation_id: string;
  source_id: string;
  source_type: string;
  object_type: string;
  track_id: string | null;
  latitude: number | null;
  longitude: number | null;
  altitude: number | null;
  distance_m: number | null;
  bearing_deg: number | null;
  speed_mps: number | null;
  heading_deg: number | null;
  confidence: number | null;
  observed_at: string | null;
  received_at: string;
  freshness_seconds: number | null;
  location_accuracy_m: number | null;
  measurement_method: string;
  source_status: string;
  raw_data_reference: string;
  details: Record<string, unknown>;
  raw?: Record<string, unknown>;
}
export interface Source {
  id: string;
  name: string;
  source_type: string;
  status: string;
  availability: string;
  enabled: boolean;
  auth_state: string;
  coverage: string;
  last_success_at: string | null;
  last_observation_at: string | null;
  latency_ms: number | null;
  update_interval: number | null;
  error: string | null;
  rate_limited_until: string | null;
  quality: string;
  last_count: number | null;
  documentation_url: string | null;
  details: Record<string, unknown>;
}
export interface Scene {
  id: string;
  source_id: string;
  name: string;
  platform: string | null;
  acquired_at: string;
  footprint: GeoJSON.Geometry;
  product_type: string | null;
  resolution_m: number | null;
  preview_url: string | null;
  download_url: string | null;
  details: Record<string, unknown>;
}
export interface Camera {
  id: string;
  name: string;
  url_env: string;
  protocol: string;
  latitude: number | null;
  longitude: number | null;
  direction_deg: number | null;
  fov_deg: number | null;
  calibration: Record<string, unknown> | null;
}
