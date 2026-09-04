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
export type SourcePriority = "high" | "medium" | "low";
export type ScrapeFetchMode = "http" | "dynamic" | "stealth";

export interface Source {
  id: string;
  code: string;
  name: string;
  country: string;
  status: SourceStatus;
  // Priorità reale della fonte (bug corretto: prima l'API non la
  // esponeva affatto, la colonna "Priority" della tabella fabbricava
  // un'etichetta High/Medium/Low da errorRate — mostrava il tasso di
  // errore travestito da priorità).
  priority: SourcePriority;
  lastRunAt: string | null;
  itemsLast24h: number;
  errorRate: number;
  consecutiveFailures: number;
  hasScrapeConfig: boolean;
}

export interface ScrapeFieldConfig {
  selector: string;
  attribute: string;
  multiple: boolean;
}

export interface ScrapeConfig {
  startUrls: string[];
  adLinkSelector: string;
  nextPageSelector: string | null;
  maxPages: number;
  maxAdsPerRun: number;
  rateLimitSeconds: number;
  fetchMode?: ScrapeFetchMode;
  renderJs: boolean;
  userAgent?: string | null;
  solveCloudflare?: boolean;
  blockWebrtc?: boolean;
  hideCanvas?: boolean;
  realChrome?: boolean;
  blockAds?: boolean;
  proxy?: string | null;
  waitSelector?: string | null;
  waitMs?: number | null;
  fields: Record<string, ScrapeFieldConfig>;
}

export interface RobotsCheckResult {
  allowed: boolean;
  robotsTxtFound: boolean;
  checkedUrl: string;
}

export interface TestConfigResult {
  adUrlsFound: number;
  sampleUrl: string | null;
  extractedFields: Record<string, unknown> | null;
  warnings: string[];
  error: string | null;
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
  phoneVisibility: "clear" | "masked";
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
  phoneVisibility: "clear" | "masked";
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
  classification: "safe" | "explicit" | "unclassified";
  classificationConfidence: number | null;
  safetySignals: {
    explicitContent?: boolean;
    explicitScore?: number;
    faceVisible?: boolean;
    faceScore?: number;
    watermarkPresent?: boolean;
    possibleMinorReview?: boolean;
  };
  reviewStatus: "not_required" | "required" | "reviewed";
  processingStatus: "pending" | "processing" | "ready" | "failed";
  displayUrl: string;
  originalUrl: string;
}

export interface WatermarkRemovalConfig {
  enabled: boolean;
  authorizationReference: string | null;
  regions: { x: number; y: number; width: number; height: number }[];
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
  provider: string;
  model: string;
}

// A single entry in the full version history (GET /records/{id}/ai-summary/versions),
// as opposed to RecordAiSummary which is only ever the latest one.
export interface RecordAiSummaryVersion extends RecordAiSummary {
  version: number;
}

export interface SummaryGenerationJob {
  id: string;
  recordId: string;
  status: "pending" | "processing" | "completed" | "failed";
  provider: string;
  model: string;
  providerConfigRevision: number | null;
  resultVersion: number | null;
  cacheHit: boolean;
  errorMessage: string | null;
  createdAt: string;
  startedAt: string | null;
  completedAt: string | null;
}

export type AIProviderName =
  | "ollama" | "openai" | "anthropic" | "google" | "groq"
  | "mistral" | "openrouter" | "custom_openai";

export interface AIProviderConfig {
  provider: AIProviderName;
  displayName: string;
  model: string;
  enabled: boolean;
  active: boolean;
  baseUrl: string | null;
  credentialConfigured: boolean;
  options: Record<string, string>;
  revision: number;
  lastTestedAt: string | null;
  lastTestSuccess: boolean | null;
}

export interface AISettings {
  activeProvider: AIProviderName;
  promptVersion: string;
  userDailyRequestLimit: number;
  providerRequestsPerMinute: number;
  globalDailyTokenBudget: number;
  revision: number;
  providers: AIProviderConfig[];
}

export interface AIModelCatalog {
  provider: AIProviderName;
  models: string[];
  cached: boolean;
}

export interface AIProviderTestResult {
  provider: AIProviderName;
  success: boolean;
  latencyMs: number;
  message: string;
}

export interface ScrapeError {
  id: string;
  url: string;
  errorMessage: string;
  createdAt: string;
}

export type ScrapeRunStatus = "running" | "completed" | "failed";

export interface ScrapeRun {
  id: string;
  startedAt: string;
  finishedAt: string | null;
  status: ScrapeRunStatus;
  itemsFound: number;
  itemsNew: number;
  errorsCount: number;
  errors: ScrapeError[];
}

export type ExportType = "text_only" | "complete_media" | "safe_complete";
export type ExportStatus = "pending" | "ready" | "processing" | "failed";

export interface ExportFilters {
  phone?: string;
  source?: string;
  status?: "verified" | "unverified" | "flagged";
  dateFrom?: string;
  dateTo?: string;
}

export interface ExportJob {
  id: string;
  type: ExportType;
  status: ExportStatus;
  progressPct: number;
  requestedBy: string;
  requestedAt: string;
  startedAt: string | null;
  completedAt: string | null;
  expiresAt: string | null;
  recordCount: number;
  estimatedUncompressedBytes: number;
  archiveSizeBytes: number | null;
  phoneVisibility: "clear" | "masked";
  errorMessage: string | null;
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
  canViewClearPhone: boolean;
}

export interface ErasureRequest {
  id: string;
  recordId: string | null;
  status: "draft" | "pending" | "processing" | "completed" | "failed";
  reason: string;
  authorizationReference: string;
  impact: Record<string, number>;
  result: Record<string, unknown> | null;
  errorMessage: string | null;
  createdAt: string;
  confirmedAt: string | null;
  completedAt: string | null;
}

export interface SourcePriorityJob {
  id: string; sourceId: string; previousPriority: SourcePriority; requestedPriority: SourcePriority;
  status: "pending" | "processing" | "completed" | "failed" | "superseded";
  recordsTotal: number; recordsProcessed: number; canonicalsChanged: number;
  errorMessage: string | null; createdAt: string; startedAt: string | null; completedAt: string | null;
}

export interface SourcePriorityConfig {
  sourceId: string; name: string; code: string; status: SourceStatus; priority: SourcePriority;
  affectedRecords: number; latestJob: SourcePriorityJob | null;
}

export interface ClassifierSettings {
  modelName: string; modelVersion: string; safeThreshold: number; explicitThreshold: number; revision: number;
  stats: { classifications: Record<string, number>; processing: Record<string, number>; reviews: Record<string, number> };
}

export interface OperationalNotification {
  id: string; kind: string; severity: "info" | "warning" | "error";
  title: string; message: string; link: string | null; isRead: boolean; createdAt: string;
}

export interface NotificationList { items: OperationalNotification[]; unreadCount: number }

export interface SystemComponent {
  name: string; status: "healthy" | "degraded" | "unavailable"; latencyMs: number | null; message: string | null;
}

export interface SystemStatus {
  status: "healthy" | "degraded" | "unavailable"; checkedAt: string; components: SystemComponent[];
}

export interface Paginated<T> {
  results: T[];
  total: number;
  page: number;
  pageSize: number;
}
