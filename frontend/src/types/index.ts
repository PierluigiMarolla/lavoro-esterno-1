// Shared domain types used across api/, hooks/ and routes/.
// Kept intentionally close to the backend Pydantic schemas so the two stay easy to reconcile.

// Matches the Postgres enum `user_role` in the backend exactly
// (backend/app/models/users.py) — "operator" here previously read "analyst",
// a naming mismatch that silently broke any frontend logic keyed on role.
export type UserRole = "admin" | "operator" | "viewer";

export interface User {
  id: string;
  email: string;
  name: string;
  role: UserRole;
  mfaEnabled: boolean;
  status: "active" | "suspended" | "invited";
}

export interface AuthTokens {
  accessToken: string;
  refreshToken: string;
}

// Login can succeed outright, require a second factor, or (for roles where
// 2FA is mandatory) require completing 2FA enrollment before anything else
// works — the caller discriminates on `status` to decide which step to show.
export type LoginResult =
  | { status: "authenticated"; tokens: AuthTokens; user: User; newBackupCodes?: string[] }
  | { status: "mfa_required"; mfaToken: string }
  | { status: "mfa_setup_required"; tokens: AuthTokens; user: User };

export type SourceStatus = "healthy" | "degraded" | "offline";

export interface Source {
  id: string;
  code: string;
  name: string;
  country: string;
  status: SourceStatus;
  lastRunAt: string | null;
  itemsLast24h: number;
  errorRate: number;
}

export type ScrapingRunStatus =
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "rate_limited";

export interface ScrapingActivity {
  id: string;
  sourceId: string;
  sourceName: string;
  sourceCode: string;
  status: ScrapingRunStatus;
  startedAt: string | null;
  durationSeconds: number | null;
  items: number | null;
  errors: number | null;
}

export interface DashboardKpis {
  totalRecords: number;
  totalRecordsDeltaPct: number;
  activeSources: number;
  activeSourcesHealthyPct: number;
  newRecordsToday: number;
  scrapingErrors: number;
  scrapingErrorsDelta: number;
  activeExports: number;
}

export interface SourceHealthBreakdown {
  healthy: number;
  rateLimited: number;
  error: number;
  total: number;
}

export type ActivityActor = "system" | "admin" | "scraper" | "ai";

export interface ActivityEvent {
  id: string;
  actor: ActivityActor;
  actorLabel: string;
  message: string;
  occurredAt: string;
}

export interface RecordSearchResult {
  id: string;
  phone: string;
  canonicalTitle: string;
  sourcesCount: number;
  occurrencesCount: number;
  firstSeenAt: string;
  lastSeenAt: string;
  status: "verified" | "unverified" | "flagged";
}

export interface RecordSearchFilters {
  phone?: string;
  source?: string;
  status?: string;
  dateFrom?: string;
  dateTo?: string;
  page?: number;
  pageSize?: number;
}

export interface RecordSearchResponse {
  results: RecordSearchResult[];
  total: number;
  page: number;
  pageSize: number;
}

export interface RecordOverview {
  id: string;
  phone: string;
  canonicalTitle: string;
  canonicalDescription: string;
  confidenceScore: number;
  sourcesCount: number;
  occurrencesCount: number;
  firstSeenAt: string;
  lastSeenAt: string;
  status: "verified" | "unverified" | "flagged";
  tags: string[];
}

export interface RecordOccurrence {
  id: string;
  sourceName: string;
  sourceCode: string;
  title: string;
  url: string;
  scrapedAt: string;
  isCanonical: boolean;
  matchConfidence: number;
}

export type MediaSensitivity = "safe" | "explicit";

export interface RecordMedia {
  id: string;
  url: string;
  thumbnailUrl: string;
  type: "image" | "video";
  sensitivity: MediaSensitivity;
  sourceName: string;
  addedAt: string;
}

export interface RecordHistoryEvent {
  id: string;
  actor: ActivityActor;
  actorLabel: string;
  action: string;
  detail: string;
  occurredAt: string;
}

export interface RecordAiSummary {
  generatedAt: string | null;
  executiveSynthesis: string;
  unverifiedClaims: string[];
  forumChatter: string[];
  sourcesUsed: { name: string; url: string }[];
}

export type ExportType = "text_only" | "complete_media" | "safe_complete";
export type ExportStatus = "ready" | "processing" | "failed";

export interface ExportJob {
  id: string;
  type: ExportType;
  status: ExportStatus;
  progressPct: number;
  requestedBy: string;
  requestedAt: string;
  recordCount: number;
  downloadUrl: string | null;
}

export interface AdminUser {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  status: "active" | "suspended" | "invited";
  mfaEnabled: boolean;
  lastLoginAt: string | null;
}

export interface Paginated<T> {
  results: T[];
  total: number;
  page: number;
  pageSize: number;
}
