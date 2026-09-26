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
  policy_kind: "managed" | "inline";
  last_accessed: string | null;
  reason: string;
  severity: "critical" | "high" | "medium" | "low";
  shared_with_roles: string[];
  events_checked: number;
  validator_agreement: boolean;
  safe_to_remove: boolean;
  broken_event_count: number;
  broken_events_sample: { event_time: string; action: string; resource_arns: string[] }[];
}

export interface ReviewSummary {
  id: string;
  request_text: string;
  status: string;
  role_name: string | null;
  safe_count: number;
  unsafe_count: number;
  created_at: number;
  updated_at: number;
}

export interface PermissionCheckResult extends BlastRadiusChange {
  granted: boolean;
  message?: string;
  validator_source?: string | null;
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
  requested_lookback_days: number | null;
  lookback_capped: boolean;
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
