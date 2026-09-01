import { Fragment, useEffect, useState, type FormEvent } from "react";
import {
  useSources,
  useSourcesSummary,
  useRunSourceScan,
  usePauseSource,
  useDisableSource,
  useSourceRuns,
  useSource,
  useCreateSource,
  useUpdateSource,
  useDeleteSource,
  useCheckSourceRobots,
  useTestSourceConfig,
} from "@/hooks/useSources";
import { useAuth } from "@/context/AuthContext";
import Icon from "@/components/ui/Icon";
import Badge, { type BadgeTone } from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import Input from "@/components/ui/Input";
import Select from "@/components/ui/Select";
import Dialog from "@/components/ui/Dialog";
import { EmptyRow, ErrorRow, LoadingRow, Table, TBody, Td, Th, THead, Tr } from "@/components/ui/Table";
import ErrorState from "@/components/ui/ErrorState";
import { describeError } from "@/lib/errors";
import type {
  ScrapeConfig,
  ScrapeFetchMode,
  ScrapeFieldConfig,
  Source,
  SourcePriority,
  SourceStatus,
  ScrapeRunStatus,
  TestConfigResult,
} from "@/types";

// Replicates desing/sources_lavoro_esterno/code.html: 4 summary cards
// (Total/Active/Degraded/Offline) followed by a sources table with
// hover-revealed row actions. "Add Source" (present in the mockup, never
// wired up before) now opens a real configuration dialog for the generic
// scraping engine (see PROGETTO.md § 4).

const STATUS_TONE: Record<SourceStatus, BadgeTone> = {
  healthy: "success",
  degraded: "warning",
  offline: "error",
};

const STATUS_LABEL: Record<SourceStatus, string> = {
  healthy: "Healthy",
  degraded: "Degraded",
  offline: "Offline",
};

const PRIORITY_LABEL: Record<SourcePriority, string> = {
  high: "High",
  medium: "Medium",
  low: "Low",
};

const RUN_STATUS_TONE: Record<ScrapeRunStatus, BadgeTone> = {
  running: "warning",
  completed: "success",
  failed: "error",
};

const RUN_STATUS_LABEL: Record<ScrapeRunStatus, string> = {
  running: "Running",
  completed: "Completed",
  failed: "Failed",
};

// Threshold mirrors backend/app/api/v1/sources.py:CONSECUTIVE_FAILURES_ALERT_THRESHOLD.
const CONSECUTIVE_FAILURES_ALERT_THRESHOLD = 3;

interface SummaryCardConfig {
  key: string;
  label: string;
  value: number | undefined;
  accent: string;
}

function formatDateTime(iso: string | null): string {
  if (!iso) return "-";
  return new Date(iso).toLocaleString([], { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function truncate(text: string, max = 80): string {
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

// Drill-down panel rendered as an extra <tr> under an expanded source row.
// Fetches run history lazily (only while the row is expanded) via
// useSourceRuns, and surfaces per-run scraping errors that the aggregate
// errorRate column on the main row cannot show.
function SourceRunsPanel({ sourceId, colSpan }: { sourceId: string; colSpan: number }) {
  const runs = useSourceRuns(sourceId, true);

  return (
    <tr className="bg-surface-container-low">
      <td colSpan={colSpan} className="px-5 py-4">
        {runs.isLoading && <p className="text-body-md text-on-surface-variant">Loading run history…</p>}
        {runs.isError && <ErrorState error={runs.error} onRetry={() => runs.refetch()} />}
        {runs.data && runs.data.length === 0 && (
          <p className="text-body-md text-on-surface-variant">No scan runs recorded yet.</p>
        )}
        {runs.data && runs.data.length > 0 && (
          <div className="space-y-3">
            {runs.data.map((run) => (
              <div key={run.id} className="bg-surface-container-lowest border border-border rounded-lg p-3">
                <div className="flex flex-wrap items-center gap-3 justify-between">
                  <div className="flex items-center gap-3">
                    <Badge tone={RUN_STATUS_TONE[run.status]}>{RUN_STATUS_LABEL[run.status]}</Badge>
                    <span className="text-body-md text-on-surface-variant">
                      {formatDateTime(run.startedAt)} → {formatDateTime(run.finishedAt)}
                    </span>
                  </div>
                  <div className="flex gap-4 text-label-sm text-on-surface-variant font-mono">
                    <span>Found: {run.itemsFound.toLocaleString()}</span>
                    <span>New: {run.itemsNew.toLocaleString()}</span>
                    <span className={run.errorsCount > 0 ? "text-error" : undefined}>Errors: {run.errorsCount}</span>
                  </div>
                </div>
                {run.errorsCount > 0 && run.errors.length > 0 && (
                  <ul className="mt-2 space-y-1 border-t border-border pt-2">
                    {run.errors.map((err) => (
                      <li key={err.id} className="text-label-sm text-on-surface-variant">
                        <span className="font-mono text-error">{truncate(err.url, 60)}</span>
                        {" — "}
                        <span>{truncate(err.errorMessage)}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>
        )}
      </td>
    </tr>
  );
}

function formatRelativeTime(iso: string | null): string {
  if (!iso) return "Never";
  const diffMs = Date.now() - new Date(iso).getTime();
  const minutes = Math.round(diffMs / 60000);
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes} min${minutes === 1 ? "" : "s"} ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.round(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

interface FieldRow {
  name: string;
  selector: string;
  attribute: string;
  multiple: boolean;
}

function fieldsToRows(fields: Record<string, ScrapeFieldConfig>): FieldRow[] {
  return Object.entries(fields).map(([name, f]) => ({ name, ...f }));
}

function rowsToFields(rows: FieldRow[]): Record<string, ScrapeFieldConfig> {
  const fields: Record<string, ScrapeFieldConfig> = {};
  for (const row of rows) {
    const name = row.name.trim();
    if (name && row.selector.trim()) {
      fields[name] = { selector: row.selector.trim(), attribute: row.attribute, multiple: row.multiple };
    }
  }
  return fields;
}

const EMPTY_FIELD_ROWS: FieldRow[] = [{ name: "phone", selector: "", attribute: "text", multiple: false }];

// Add/Edit dialog: name/base_url/priority plus the full generic scraping
// engine configuration (start URLs, ad link/pagination selectors, per-field
// CSS selectors). The operator supplies every selector themselves — this
// component has no knowledge of any specific target site (see
// PROGETTO.md § 4 for why).
function SourceFormDialog({
  open,
  onClose,
  editingSource,
}: {
  open: boolean;
  onClose: () => void;
  editingSource: Source | null;
}) {
  const isEdit = editingSource !== null;
  const detail = useSource(editingSource?.id ?? "", isEdit && open);
  const createSource = useCreateSource();
  const updateSource = useUpdateSource();
  const testConfig = useTestSourceConfig();

  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [priority, setPriority] = useState<SourcePriority>("medium");
  const [startUrlsText, setStartUrlsText] = useState("");
  const [adLinkSelector, setAdLinkSelector] = useState("");
  const [nextPageSelector, setNextPageSelector] = useState("");
  const [maxPages, setMaxPages] = useState(3);
  const [maxAdsPerRun, setMaxAdsPerRun] = useState(50);
  const [rateLimitSeconds, setRateLimitSeconds] = useState(2);
  const [fetchMode, setFetchMode] = useState<ScrapeFetchMode>("http");
  const [userAgent, setUserAgent] = useState("");
  const [solveCloudflare, setSolveCloudflare] = useState(false);
  const [blockWebrtc, setBlockWebrtc] = useState(false);
  const [hideCanvas, setHideCanvas] = useState(false);
  const [realChrome, setRealChrome] = useState(false);
  const [blockAds, setBlockAds] = useState(false);
  const [proxy, setProxy] = useState("");
  const [waitSelector, setWaitSelector] = useState("");
  const [waitMs, setWaitMs] = useState<number | "">("");
  const [fieldRows, setFieldRows] = useState<FieldRow[]>(EMPTY_FIELD_ROWS);
  const [watermarkEnabled, setWatermarkEnabled] = useState(false);
  const [watermarkAuthorization, setWatermarkAuthorization] = useState("");
  const [watermarkRegion, setWatermarkRegion] = useState({ x: 0.7, y: 0.85, width: 0.25, height: 0.1 });
  const [formError, setFormError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<TestConfigResult | null>(null);

  // Reset (new source) or populate (editing, once its detail has loaded)
  // whenever the dialog transitions to open — not on every render.
  useEffect(() => {
    if (!open) return;
    if (!isEdit) {
      setName("");
      setSlug("");
      setBaseUrl("");
      setPriority("medium");
      setStartUrlsText("");
      setAdLinkSelector("");
      setNextPageSelector("");
      setMaxPages(3);
      setMaxAdsPerRun(50);
      setRateLimitSeconds(2);
      setFetchMode("http");
      setUserAgent("");
      setSolveCloudflare(false);
      setBlockWebrtc(false);
      setHideCanvas(false);
      setRealChrome(false);
      setBlockAds(false);
      setProxy("");
      setWaitSelector("");
      setWaitMs("");
      setFieldRows(EMPTY_FIELD_ROWS);
      setWatermarkEnabled(false);
      setWatermarkAuthorization("");
      setWatermarkRegion({ x: 0.7, y: 0.85, width: 0.25, height: 0.1 });
    }
    setFormError(null);
    setTestResult(null);
  }, [open, isEdit]);

  useEffect(() => {
    if (!isEdit || !detail.data) return;
    setName(detail.data.name);
    setBaseUrl(""); // base_url isn't part of Source (list shape); left blank unless re-typed
    setPriority(detail.data.priority);
    const cfg = detail.data.scrapeConfig;
    const watermark = detail.data.watermarkRemoval;
    setWatermarkEnabled(watermark.enabled);
    setWatermarkAuthorization(watermark.authorizationReference ?? "");
    setWatermarkRegion(watermark.regions[0] ?? { x: 0.7, y: 0.85, width: 0.25, height: 0.1 });
    if (cfg) {
      setStartUrlsText(cfg.startUrls.join("\n"));
      setAdLinkSelector(cfg.adLinkSelector);
      setNextPageSelector(cfg.nextPageSelector ?? "");
      setMaxPages(cfg.maxPages);
      setMaxAdsPerRun(cfg.maxAdsPerRun);
      setRateLimitSeconds(cfg.rateLimitSeconds);
      setFetchMode(cfg.fetchMode ?? (cfg.renderJs ? "dynamic" : "http"));
      setUserAgent(cfg.userAgent ?? "");
      setSolveCloudflare(cfg.solveCloudflare ?? false);
      setBlockWebrtc(cfg.blockWebrtc ?? false);
      setHideCanvas(cfg.hideCanvas ?? false);
      setRealChrome(cfg.realChrome ?? false);
      setBlockAds(cfg.blockAds ?? false);
      setProxy(cfg.proxy ?? "");
      setWaitSelector(cfg.waitSelector ?? "");
      setWaitMs(cfg.waitMs ?? "");
      setFieldRows(fieldsToRows(cfg.fields));
    } else {
      setStartUrlsText("");
      setAdLinkSelector("");
      setNextPageSelector("");
      setMaxPages(3);
      setMaxAdsPerRun(50);
      setRateLimitSeconds(2);
      setFetchMode("http");
      setUserAgent("");
      setSolveCloudflare(false);
      setBlockWebrtc(false);
      setHideCanvas(false);
      setRealChrome(false);
      setBlockAds(false);
      setProxy("");
      setWaitSelector("");
      setWaitMs("");
      setFieldRows(EMPTY_FIELD_ROWS);
    }
  }, [isEdit, detail.data]);

  function updateFieldRow(index: number, patch: Partial<FieldRow>) {
    setFieldRows((rows) => rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }

  function addFieldRow() {
    setFieldRows((rows) => [...rows, { name: "", selector: "", attribute: "text", multiple: false }]);
  }

  function removeFieldRow(index: number) {
    setFieldRows((rows) => rows.filter((_, i) => i !== index));
  }

  function buildScrapeConfig(): ScrapeConfig | null {
    const startUrls = startUrlsText
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
    if (startUrls.length === 0 && !adLinkSelector.trim()) {
      // Scraping configuration is entirely optional at creation time — a
      // source can be added first and configured for scraping later via
      // "Edit configuration".
      return null;
    }
    return {
      startUrls,
      adLinkSelector: adLinkSelector.trim(),
      nextPageSelector: nextPageSelector.trim() || null,
      maxPages,
      maxAdsPerRun,
      rateLimitSeconds,
      fetchMode,
      renderJs: fetchMode !== "http",
      userAgent: userAgent.trim() || null,
      solveCloudflare,
      blockWebrtc,
      hideCanvas,
      realChrome,
      blockAds,
      proxy: proxy.trim() || null,
      waitSelector: waitSelector.trim() || null,
      waitMs: waitMs === "" ? null : Number(waitMs),
      fields: rowsToFields(fieldRows),
    };
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    const scrapeConfig = buildScrapeConfig();

    try {
      const watermarkRemoval = {
        enabled: watermarkEnabled,
        authorizationReference: watermarkAuthorization.trim() || null,
        regions: watermarkEnabled ? [watermarkRegion] : [],
      };
      if (isEdit && editingSource) {
        await updateSource.mutateAsync({
          id: editingSource.id,
          input: { name, priority, scrapeConfig, watermarkRemoval, ...(baseUrl.trim() ? { baseUrl: baseUrl.trim() } : {}) },
        });
      } else {
        await createSource.mutateAsync({ name, slug, baseUrl, priority, scrapeConfig, watermarkRemoval });
      }
      onClose();
    } catch (err) {
      setFormError(describeError(err).description);
    }
  }

  async function handleTestConfig() {
    if (!editingSource) return;
    setTestResult(null);
    try {
      const result = await testConfig.mutateAsync(editingSource.id);
      setTestResult(result);
    } catch (err) {
      setTestResult({ adUrlsFound: 0, sampleUrl: null, extractedFields: null, error: describeError(err).description });
    }
  }

  const isSaving = createSource.isPending || updateSource.isPending;

  return (
    <Dialog open={open} onClose={onClose} title={isEdit ? "Edit source" : "Add source"}>
      <form onSubmit={handleSubmit} className="flex flex-col gap-4 max-h-[65vh] overflow-y-auto pr-1">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label htmlFor="source-name" className="text-label-sm text-on-surface-variant block mb-1">
              Name
            </label>
            <Input id="source-name" required value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div>
            <label htmlFor="source-priority" className="text-label-sm text-on-surface-variant block mb-1">
              Priority
            </label>
            <Select
              id="source-priority"
              className="w-full"
              value={priority}
              onChange={(e) => setPriority(e.target.value as SourcePriority)}
            >
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </Select>
          </div>
        </div>

        {!isEdit && (
          <div>
            <label htmlFor="source-slug" className="text-label-sm text-on-surface-variant block mb-1">
              Slug (unique identifier, lowercase/underscore only)
            </label>
            <Input
              id="source-slug"
              required
              mono
              pattern="[a-z0-9_]+"
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
              placeholder="my_new_source"
            />
          </div>
        )}

        <div>
          <label htmlFor="source-base-url" className="text-label-sm text-on-surface-variant block mb-1">
            Base URL {isEdit && <span className="text-outline">(leave blank to keep current)</span>}
          </label>
          <Input
            id="source-base-url"
            required={!isEdit}
            mono
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="https://example.com"
          />
        </div>

        <div className="border-t border-border pt-3">
          <h4 className="text-body-md font-semibold text-on-surface mb-1">Scrape configuration</h4>
          <p className="text-label-sm text-on-surface-variant mb-3">
            Optional at creation. The engine only knows what you configure here — CSS selectors for this
            specific site, supplied by you.
          </p>

          <div className="space-y-3">
            <div>
              <label htmlFor="source-start-urls" className="text-label-sm text-on-surface-variant block mb-1">
                Start URLs (one per line)
              </label>
              <textarea
                id="source-start-urls"
                rows={2}
                value={startUrlsText}
                onChange={(e) => setStartUrlsText(e.target.value)}
                className="w-full py-2 px-3 border border-outline-variant rounded bg-surface text-body-md font-mono text-on-surface focus:ring-2 focus:ring-primary-container focus:border-primary-container outline-none transition-colors"
                placeholder={"https://example.com/listing"}
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label htmlFor="source-ad-link-selector" className="text-label-sm text-on-surface-variant block mb-1">
                  Ad link selector (CSS)
                </label>
                <Input
                  id="source-ad-link-selector"
                  mono
                  value={adLinkSelector}
                  onChange={(e) => setAdLinkSelector(e.target.value)}
                  placeholder="a.ad-card"
                />
              </div>
              <div>
                <label htmlFor="source-next-page-selector" className="text-label-sm text-on-surface-variant block mb-1">
                  Next page selector (optional)
                </label>
                <Input
                  id="source-next-page-selector"
                  mono
                  value={nextPageSelector}
                  onChange={(e) => setNextPageSelector(e.target.value)}
                  placeholder="a.pagination-next"
                />
              </div>
            </div>

            <div className="grid grid-cols-3 gap-3">
              <div>
                <label htmlFor="source-max-pages" className="text-label-sm text-on-surface-variant block mb-1">
                  Max pages
                </label>
                <Input
                  id="source-max-pages"
                  type="number"
                  min={1}
                  max={20}
                  value={maxPages}
                  onChange={(e) => setMaxPages(Number(e.target.value))}
                />
              </div>
              <div>
                <label htmlFor="source-max-ads" className="text-label-sm text-on-surface-variant block mb-1">
                  Max ads/run
                </label>
                <Input
                  id="source-max-ads"
                  type="number"
                  min={1}
                  max={500}
                  value={maxAdsPerRun}
                  onChange={(e) => setMaxAdsPerRun(Number(e.target.value))}
                />
              </div>
              <div>
                <label htmlFor="source-rate-limit" className="text-label-sm text-on-surface-variant block mb-1">
                  Rate limit (s)
                </label>
                <Input
                  id="source-rate-limit"
                  type="number"
                  min={1}
                  max={60}
                  step={0.5}
                  value={rateLimitSeconds}
                  onChange={(e) => setRateLimitSeconds(Number(e.target.value))}
                />
              </div>
            </div>

            <div>
              <label htmlFor="source-user-agent" className="text-label-sm text-on-surface-variant block mb-1">
                User-Agent (optional)
              </label>
              <Input
                id="source-user-agent"
                mono
                value={userAgent}
                onChange={(e) => setUserAgent(e.target.value)}
                placeholder="LavoroEsternoBot/1.0 (+https://lavoro.internal/bot)"
              />
            </div>

            <div>
              <label htmlFor="source-fetch-mode" className="text-label-sm text-on-surface-variant block mb-1">
                Fetch mode
              </label>
              <Select
                id="source-fetch-mode"
                className="w-full"
                value={fetchMode}
                onChange={(e) => setFetchMode(e.target.value as ScrapeFetchMode)}
              >
                <option value="http">HTTP (Scrapling)</option>
                <option value="dynamic">Dynamic JS (Scrapling browser)</option>
                <option value="stealth">Stealth (Scrapling anti-bot)</option>
              </Select>
            </div>

            {fetchMode !== "http" && (
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label htmlFor="source-wait-selector" className="text-label-sm text-on-surface-variant block mb-1">
                    Wait selector (optional)
                  </label>
                  <Input
                    id="source-wait-selector"
                    mono
                    value={waitSelector}
                    onChange={(e) => setWaitSelector(e.target.value)}
                    placeholder=".loaded"
                  />
                </div>
                <div>
                  <label htmlFor="source-wait-ms" className="text-label-sm text-on-surface-variant block mb-1">
                    Extra wait (ms)
                  </label>
                  <Input
                    id="source-wait-ms"
                    type="number"
                    min={0}
                    max={120000}
                    step={500}
                    value={waitMs}
                    onChange={(e) => setWaitMs(e.target.value === "" ? "" : Number(e.target.value))}
                  />
                </div>
              </div>
            )}

            {fetchMode === "stealth" && (
              <div className="space-y-3 border border-border rounded p-3">
                <div>
                  <label htmlFor="source-proxy" className="text-label-sm text-on-surface-variant block mb-1">
                    Proxy (optional)
                  </label>
                  <Input
                    id="source-proxy"
                    mono
                    value={proxy}
                    onChange={(e) => setProxy(e.target.value)}
                    placeholder="http://user:password@host:8080"
                  />
                </div>
                <div className="grid grid-cols-2 gap-2">
                  {[
                    ["solveCloudflare", "Solve Cloudflare", solveCloudflare, setSolveCloudflare],
                    ["blockWebrtc", "Block WebRTC", blockWebrtc, setBlockWebrtc],
                    ["hideCanvas", "Hide canvas", hideCanvas, setHideCanvas],
                    ["realChrome", "Real Chrome", realChrome, setRealChrome],
                    ["blockAds", "Block ads", blockAds, setBlockAds],
                  ].map(([id, label, checked, setter]) => (
                    <label key={id as string} className="flex items-center gap-2 text-label-sm text-on-surface-variant">
                      <input
                        type="checkbox"
                        checked={checked as boolean}
                        onChange={(e) => (setter as (value: boolean) => void)(e.target.checked)}
                      />
                      {label as string}
                    </label>
                  ))}
                </div>
              </div>
            )}

            <div>
              <div className="flex items-center justify-between mb-1">
                <span className="text-label-sm text-on-surface-variant">
                  Fields to extract (a <code>phone</code> field is required)
                </span>
                <button type="button" onClick={addFieldRow} className="text-label-sm text-primary hover:underline">
                  + Add field
                </button>
              </div>
              <div className="space-y-2">
                {fieldRows.map((row, index) => (
                  <div key={index} className="grid grid-cols-[1fr_2fr_1fr_auto_auto] gap-2 items-center">
                    <Input
                      mono
                      placeholder="field name"
                      value={row.name}
                      onChange={(e) => updateFieldRow(index, { name: e.target.value })}
                    />
                    <Input
                      mono
                      placeholder="CSS selector"
                      value={row.selector}
                      onChange={(e) => updateFieldRow(index, { selector: e.target.value })}
                    />
                    <Select
                      value={row.attribute}
                      onChange={(e) => updateFieldRow(index, { attribute: e.target.value })}
                    >
                      <option value="text">text</option>
                      <option value="href">href</option>
                      <option value="src">src</option>
                    </Select>
                    <label className="flex items-center gap-1 text-label-sm text-on-surface-variant whitespace-nowrap">
                      <input
                        type="checkbox"
                        checked={row.multiple}
                        onChange={(e) => updateFieldRow(index, { multiple: e.target.checked })}
                      />
                      multi
                    </label>
                    <button
                      type="button"
                      onClick={() => removeFieldRow(index)}
                      className="text-on-surface-variant hover:text-error"
                      aria-label={`Remove field ${row.name || index + 1}`}
                    >
                      <Icon name="close" size={16} />
                    </button>
                  </div>
                ))}
              </div>
            </div>

            {isEdit && (
              <div className="border-t border-border pt-3">
                <Button type="button" variant="secondary" onClick={handleTestConfig} disabled={testConfig.isPending}>
                  {testConfig.isPending ? "Testing…" : "Test configuration"}
                </Button>
                {testResult && (
                  <div className="mt-2 text-label-sm bg-surface-container-low border border-border rounded p-2">
                    {testResult.error ? (
                      <p className="text-error">{testResult.error}</p>
                    ) : (
                      <>
                        <p className="text-on-surface">Found {testResult.adUrlsFound} ad link(s).</p>
                        {testResult.sampleUrl && (
                          <p className="font-mono text-on-surface-variant truncate">Sample: {testResult.sampleUrl}</p>
                        )}
                        {testResult.extractedFields && (
                          <pre className="mt-1 overflow-x-auto text-on-surface-variant">
                            {JSON.stringify(testResult.extractedFields, null, 2)}
                          </pre>
                        )}
                      </>
                    )}
                  </div>
                )}
              </div>
            )}
            {!isEdit && (
              <p className="text-label-sm text-outline">Save the source first to test its configuration.</p>
            )}
          </div>
        </div>

        <fieldset className="border border-border rounded-lg p-3 space-y-3">
          <legend className="px-1 text-label-sm text-on-surface">Authorized watermark removal</legend>
          <label className="flex items-center gap-2 text-body-md text-on-surface-variant">
            <input type="checkbox" checked={watermarkEnabled} onChange={(event) => setWatermarkEnabled(event.target.checked)} />
            Enable for this source (originals are always preserved)
          </label>
          {watermarkEnabled && (
            <>
              <Input
                required
                value={watermarkAuthorization}
                onChange={(event) => setWatermarkAuthorization(event.target.value)}
                placeholder="Contract/ticket/legal authorization reference"
              />
              <div className="grid grid-cols-4 gap-2">
                {(["x", "y", "width", "height"] as const).map((key) => (
                  <label key={key} className="text-label-sm text-on-surface-variant">
                    {key}
                    <Input
                      type="number"
                      min="0"
                      max="1"
                      step="0.01"
                      value={watermarkRegion[key]}
                      onChange={(event) => setWatermarkRegion((region) => ({ ...region, [key]: Number(event.target.value) }))}
                    />
                  </label>
                ))}
              </div>
            </>
          )}
        </fieldset>

        {formError && <p className="text-body-md text-error">{formError}</p>}

        <div className="flex justify-end gap-2 pt-2 border-t border-border">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={isSaving}>
            {isSaving ? "Saving…" : isEdit ? "Save changes" : "Add source"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

function DeleteSourceDialog({ source, onClose }: { source: Source | null; onClose: () => void }) {
  const deleteSource = useDeleteSource();

  function handleClose() {
    deleteSource.reset();
    onClose();
  }

  function handleConfirm() {
    if (!source) return;
    deleteSource.mutate(source.id, { onSuccess: handleClose });
  }

  return (
    <Dialog open={source !== null} onClose={handleClose} title="Delete source">
      <div className="flex flex-col gap-4">
        <p className="text-body-md text-on-surface">
          Are you sure you want to delete <span className="font-semibold">{source?.name}</span>? This is
          blocked if any advertisement is already linked to it.
        </p>
        {deleteSource.isError && (
          <p className="text-body-md text-error">{describeError(deleteSource.error).description}</p>
        )}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={handleClose}>
            Cancel
          </Button>
          <Button type="button" variant="danger" onClick={handleConfirm} disabled={deleteSource.isPending}>
            {deleteSource.isPending ? "Deleting…" : "Delete"}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

export default function SourcesPage() {
  const { user } = useAuth();
  const canManageSources = user?.role !== "viewer";
  const isAdmin = user?.role === "admin";
  const summary = useSourcesSummary();
  const sources = useSources();
  const runScan = useRunSourceScan();
  const pause = usePauseSource();
  const disable = useDisableSource();
  const checkRobots = useCheckSourceRobots();
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [formSource, setFormSource] = useState<Source | null | "new">(null);
  const [deleteTarget, setDeleteTarget] = useState<Source | null>(null);
  const [robotsResultBySource, setRobotsResultBySource] = useState<Record<string, string>>({});

  function toggleExpanded(id: string) {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function handleRunScan(id: string) {
    runScan.mutate(id);
    // Expand the row (if not already) so the runs panel is visible right
    // away and starts polling immediately, instead of requiring a manual
    // expand to see the just-queued run appear and settle.
    setExpandedIds((prev) => (prev.has(id) ? prev : new Set(prev).add(id)));
  }

  async function handleCheckRobots(source: Source) {
    try {
      const result = await checkRobots.mutateAsync(source.id);
      setRobotsResultBySource((prev) => ({
        ...prev,
        [source.id]: result.allowed ? "Allowed" : "Disallowed",
      }));
    } catch (err) {
      setRobotsResultBySource((prev) => ({ ...prev, [source.id]: describeError(err).title }));
    }
  }

  const cards: SummaryCardConfig[] = [
    { key: "total", label: "Total Sources", value: summary.data?.total, accent: "border-t-primary" },
    { key: "active", label: "Active", value: summary.data?.active, accent: "border-t-success" },
    { key: "degraded", label: "Degraded", value: summary.data?.degraded, accent: "border-t-warning" },
    { key: "offline", label: "Offline", value: summary.data?.offline, accent: "border-t-error" },
  ];

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-end">
        <div>
          <h2 className="text-headline-md text-on-surface">Data Sources</h2>
          <p className="text-body-md text-on-surface-variant mt-1">
            Manage, monitor, and configure active external data pipelines.
          </p>
        </div>
        {isAdmin && (
          <Button onClick={() => setFormSource("new")}>
            <Icon name="add" size={18} />
            Add Source
          </Button>
        )}
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-4 gap-gutter">
        {summary.isLoading &&
          Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="bg-surface-container-lowest border border-border rounded-lg p-4 h-[84px] animate-pulse" />
          ))}
        {summary.isError && (
          <div className="col-span-4 bg-error-container/20 border border-error/20 rounded-lg p-4 text-error text-body-md">
            Failed to load sources summary.
          </div>
        )}
        {summary.data &&
          cards.map((card) => (
            <div
              key={card.key}
              className={`bg-surface-container-lowest border border-border border-t-2 ${card.accent} rounded-lg p-4 shadow-[0_1px_2px_rgba(0,0,0,0.02)]`}
            >
              <h3 className="text-label-sm text-on-surface-variant uppercase tracking-wider mb-2">{card.label}</h3>
              <div className="text-headline-md text-on-surface">{card.value?.toLocaleString() ?? "-"}</div>
            </div>
          ))}
      </div>

      {/* Sources Table */}
      <div className="bg-surface-container-lowest border border-border rounded-lg shadow-[0_1px_2px_rgba(0,0,0,0.02)] flex flex-col min-h-[400px]">
        <div className="px-5 py-4 border-b border-border bg-surface-container-lowest">
          <h3 className="text-headline-sm text-on-surface flex items-center gap-2">
            <Icon name="source" className="text-primary" />
            Sources
          </h3>
        </div>
        <Table>
          <THead>
            <Tr className="hover:bg-transparent">
              <Th>Source Name</Th>
              <Th>Status</Th>
              <Th className="text-right">Priority</Th>
              <Th>Last Scan</Th>
              <Th className="text-right">Acquired Items</Th>
              <Th className="text-right">Error Rate</Th>
              <Th className="text-right">Actions</Th>
            </Tr>
          </THead>
          <TBody>
            {sources.isLoading && <LoadingRow colSpan={7} />}
            {sources.isError && <ErrorRow colSpan={7} error={sources.error} onRetry={() => sources.refetch()} />}
            {sources.data && sources.data.length === 0 && <EmptyRow colSpan={7} message="No sources configured." />}
            {sources.data?.map((source) => {
              const isExpanded = expandedIds.has(source.id);
              const isBroken = source.consecutiveFailures >= CONSECUTIVE_FAILURES_ALERT_THRESHOLD;
              return (
              <Fragment key={source.id}>
              <Tr className={isBroken ? "bg-error-container/10" : undefined}>
                <Td>
                  <div className="flex items-center gap-1.5">
                    <button
                      onClick={() => toggleExpanded(source.id)}
                      title={isExpanded ? "Hide run history" : "Show run history"}
                      className="p-0.5 text-on-surface-variant hover:text-primary rounded transition-colors"
                    >
                      <Icon name={isExpanded ? "expand_more" : "chevron_right"} size={18} />
                    </button>
                    <div>
                      <div className="font-medium text-on-surface flex items-center gap-1.5">
                        {source.name}
                        {isBroken && (
                          <span title={`${source.consecutiveFailures} consecutive failed runs`}>
                            <Badge tone="error">Connector broken?</Badge>
                          </span>
                        )}
                      </div>
                      <div className="text-label-sm text-on-surface-variant font-mono">{source.code}</div>
                    </div>
                  </div>
                </Td>
                <Td>
                  <Badge tone={STATUS_TONE[source.status]}>{STATUS_LABEL[source.status]}</Badge>
                </Td>
                <Td className="text-right">
                  <span className="font-mono text-mono-data text-on-surface bg-surface-container px-2 py-1 rounded">
                    {PRIORITY_LABEL[source.priority]}
                  </span>
                </Td>
                <Td className="text-on-surface-variant">{formatRelativeTime(source.lastRunAt)}</Td>
                <Td className="text-right font-mono text-on-surface">{source.itemsLast24h.toLocaleString()}</Td>
                <Td
                  className={`text-right font-mono ${
                    source.status === "offline" ? "text-error" : source.status === "degraded" ? "text-warning" : "text-success"
                  }`}
                >
                  {(source.errorRate * 100).toFixed(2)}%
                </Td>
                <Td className="text-right">
                  <div className="flex justify-end items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                    {robotsResultBySource[source.id] && (
                      <span className="text-label-sm text-on-surface-variant">{robotsResultBySource[source.id]}</span>
                    )}
                    <button
                      onClick={() => handleCheckRobots(source)}
                      disabled={checkRobots.isPending}
                      title="Check robots.txt"
                      className="p-1.5 text-on-surface-variant hover:text-primary hover:bg-primary/10 rounded transition-colors disabled:opacity-50"
                    >
                      <Icon name="policy" size={16} />
                    </button>
                    {canManageSources && source.hasScrapeConfig && (
                      <button
                        onClick={() => handleRunScan(source.id)}
                        disabled={runScan.isPending}
                        title="Run Scan"
                        className="p-1.5 text-on-surface-variant hover:text-primary hover:bg-primary/10 rounded transition-colors disabled:opacity-50"
                      >
                        <Icon name="play_arrow" size={16} />
                      </button>
                    )}
                    {canManageSources && (
                      <button
                        onClick={() => pause.mutate(source.id)}
                        disabled={pause.isPending}
                        title="Pause"
                        className="p-1.5 text-on-surface-variant hover:text-primary hover:bg-primary/10 rounded transition-colors disabled:opacity-50"
                      >
                        <Icon name="pause" size={16} />
                      </button>
                    )}
                    {isAdmin && (
                      <button
                        onClick={() => setFormSource(source)}
                        title={source.hasScrapeConfig ? "Edit configuration" : "Configure"}
                        className="p-1.5 text-on-surface-variant hover:text-primary hover:bg-primary/10 rounded transition-colors"
                      >
                        <Icon name="tune" size={16} />
                      </button>
                    )}
                    {canManageSources && (
                      <button
                        onClick={() => disable.mutate(source.id)}
                        disabled={disable.isPending}
                        title="Disable"
                        className="p-1.5 text-on-surface-variant hover:text-error hover:bg-error-container/30 rounded transition-colors disabled:opacity-50"
                      >
                        <Icon name="block" size={16} />
                      </button>
                    )}
                    {isAdmin && (
                      <button
                        onClick={() => setDeleteTarget(source)}
                        title="Delete"
                        className="p-1.5 text-on-surface-variant hover:text-error hover:bg-error-container/30 rounded transition-colors"
                      >
                        <Icon name="delete" size={16} />
                      </button>
                    )}
                  </div>
                </Td>
              </Tr>
              {isExpanded && <SourceRunsPanel sourceId={source.id} colSpan={7} />}
              </Fragment>
              );
            })}
          </TBody>
        </Table>
      </div>

      <SourceFormDialog
        open={formSource !== null}
        onClose={() => setFormSource(null)}
        editingSource={formSource === "new" ? null : formSource}
      />
      <DeleteSourceDialog source={deleteTarget} onClose={() => setDeleteTarget(null)} />
    </div>
  );
}
