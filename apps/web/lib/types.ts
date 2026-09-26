export interface TimelineEvent {
  ts: number;
  label: string;
  detail: string;
  kind: "info" | "success" | "warn" | "error" | "waiting";
}

export interface BlastRadiusChange {
  role_name: string;
  action: string;
  source_policy: string;
  last_accessed: string | null;
  reason: string;
  events_checked: number;
  validator_agreement: boolean;
  safe_to_remove: boolean;
  broken_event_count: number;
  broken_events_sample: { event_time: string; action: string; resource_arns: string[] }[];
}

export interface VerifyResult {
  roles_updated: number;
  permissions_removed: number;
  mismatches: unknown[];
  verified: boolean;
}

export interface Understood {
  role_name: string | null;
  role_prefix: string | null;
  lookback_days: number;
  exclude_actions: string[];
  exclude_role_patterns: string[];
}

export interface ReviewRun {
  id: string;
  request_text: string;
  status:
    | "running"
    | "no_candidates"
    | "awaiting_approval"
    | "approved"
    | "rejected"
    | "committed"
    | "verified"
    | "failed";
  timeline: TimelineEvent[];
  understood: Understood | null;
  error: string | null;
  sandbox_used: boolean;
  validator_source: string | null;
  safe_changes: BlastRadiusChange[];
  unsafe_candidates: BlastRadiusChange[];
  total_candidates: number;
  verify_result: VerifyResult | null;
}
