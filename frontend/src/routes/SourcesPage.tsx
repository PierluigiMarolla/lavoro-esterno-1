import { Fragment, useEffect, useState, type FormEvent } from "react";
import {
  useSources,
  useSourcesSummary,
  useRunSourceScan,
  usePauseSource,
  useDisableSource,
  useEnableSource,
  useDuplicateSource,
  useSourceRuns,
  useSource,
  useCreateSource,
  useUpdateSource,
  useUpdateSourceSchedule,
  useDeleteSource,
  useCheckSourceRobots,
  useExportSources,
  useTestSourceConfig,
} from "@/hooks/useSources";
import { useProxyPools } from "@/hooks/useProxies";
import { useAuth } from "@/context/AuthContext";
import Icon from "@/components/ui/Icon";
import Badge, { type BadgeTone } from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import Input from "@/components/ui/Input";
import Select from "@/components/ui/Select";
import Dialog from "@/components/ui/Dialog";
import { EmptyRow, ErrorRow, LoadingRow, Table, TBody, Td, Th, THead, Tr } from "@/components/ui/Table";
import ErrorState from "@/components/ui/ErrorState";
import SourceImportDialog from "@/components/sources/SourceImportDialog";
import { describeError } from "@/lib/errors";
import { formatDateTime } from "@/lib/format";
import type {
  ScrapeConfig,
  ScrapeFetchMode,
  ScrapeFieldConfig,
  ScrapeFieldExtractionMode,
  Source,
  SourcePriority,
  SourceStatus,
  ScrapeRunStatus,
  ScrapeIntervalUnit,
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
  healthy: "Operativa",
  degraded: "Degradata",
  offline: "Fuori linea",
};

const PRIORITY_LABEL: Record<SourcePriority, string> = {
  high: "Alta",
  medium: "Media",
  low: "Bassa",
};

const RUN_STATUS_TONE: Record<ScrapeRunStatus, BadgeTone> = {
  pending: "neutral",
  running: "warning",
  completed: "success",
  failed: "error",
};

const RUN_STATUS_LABEL: Record<ScrapeRunStatus, string> = {
  pending: "In attesa",
  running: "In esecuzione",
  completed: "Completata",
  failed: "Non riuscita",
};

// Threshold mirrors backend/app/api/v1/sources.py:CONSECUTIVE_FAILURES_ALERT_THRESHOLD.
const CONSECUTIVE_FAILURES_ALERT_THRESHOLD = 3;

interface SummaryCardConfig {
  key: string;
  label: string;
  value: number | undefined;
  accent: string;
}

function formatInterval(minutes: number | null): string {
  if (!minutes) return "Non configurato";
  if (minutes % 1440 === 0) return `${minutes / 1440} ${minutes === 1440 ? "giorno" : "giorni"}`;
  if (minutes % 60 === 0) return `${minutes / 60} ${minutes === 60 ? "ora" : "ore"}`;
  return `${minutes} minuti`;
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
        {runs.isLoading && <p className="text-body-md text-on-surface-variant">Caricamento cronologia esecuzioni…</p>}
        {runs.isError && <ErrorState error={runs.error} onRetry={() => runs.refetch()} />}
        {runs.data && runs.data.length === 0 && (
          <p className="text-body-md text-on-surface-variant">Nessuna scansione ancora registrata.</p>
        )}
        {runs.data && runs.data.length > 0 && (
          <div className="space-y-3">
            {runs.data.map((run) => (
              <div key={run.id} className="bg-surface-container-lowest border border-border rounded-lg p-3">
                <div className="flex flex-wrap items-center gap-3 justify-between">
                  <div className="flex items-center gap-3">
                    <Badge tone={RUN_STATUS_TONE[run.status]}>{RUN_STATUS_LABEL[run.status]}</Badge>
                    <Badge tone="neutral">{run.triggerType === "scheduled" ? "Pianificata" : "Manuale"}</Badge>
                    <span className="text-body-md text-on-surface-variant">
                      {formatDateTime(run.startedAt ?? run.queuedAt)} → {formatDateTime(run.finishedAt)}
                    </span>
                  </div>
                  <div className="flex gap-4 text-label-sm text-on-surface-variant font-mono">
                    <span>Trovati: {run.itemsFound.toLocaleString("it-IT")}</span>
                    <span>Nuovi: {run.itemsNew.toLocaleString("it-IT")}</span>
                    <span>Aggiornati: {run.itemsUpdated.toLocaleString("it-IT")}</span>
                    <span>Invariati: {run.itemsUnchanged.toLocaleString("it-IT")}</span>
                    <span>Pagine: {run.pagesVisited.toLocaleString("it-IT")}</span>
                    <span>Pagination: {run.paginationMode}</span>
                    <span>Proxy attempts: {run.proxyAttemptsCount}</span>
                    <span>Rotations: {run.proxyRotationsCount}</span>
                    <span className={run.errorsCount > 0 ? "text-error" : undefined}>Errori: {run.errorsCount}</span>
                  </div>
                </div>
                {run.paginationStopReason && (
                  <p className="mt-1 text-label-sm text-on-surface-variant">
                    Stop reason: <span className="font-mono">{run.paginationStopReason}</span>
                  </p>
                )}
                {run.scheduledFor && (
                  <p className="mt-1 text-label-sm text-on-surface-variant">
                    Planned for: {formatDateTime(run.scheduledFor)}
                  </p>
                )}
                {run.proxyStopReason && (
                  <p className="mt-1 text-label-sm text-error">
                    Proxy stop: <span className="font-mono">{run.proxyStopReason}</span>
                  </p>
                )}
                {run.errorsCount > 0 && run.errors.length > 0 && (
                  <ul className="mt-2 space-y-1 border-t border-border pt-2">
                    {run.errors.map((err) => (
                      <li key={err.id} className="text-label-sm text-on-surface-variant">
                        <span className="font-mono text-error">{truncate(err.url, 60)}</span>
                        {" — "}
                        {err.errorCode && (
                          <span className="mr-2 rounded bg-error/10 px-1.5 py-0.5 font-mono text-error">
                            {err.errorCode}
                          </span>
                        )}
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
  if (!iso) return "Mai";
  const diffMs = Date.now() - new Date(iso).getTime();
  const minutes = Math.round(diffMs / 60000);
  if (minutes < 1) return "Adesso";
  if (minutes < 60) return `${minutes} min fa`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} ${hours === 1 ? "ora" : "ore"} fa`;
  const days = Math.round(hours / 24);
  return `${days} ${days === 1 ? "giorno" : "giorni"} fa`;
}

interface FieldRow {
  name: string;
  selector: string;
  attribute: string;
  multiple: boolean;
  extractionMode: ScrapeFieldExtractionMode;
  containerSelector: string;
  keySelector: string;
  keyAttribute: string;
  valueSelector: string;
  valueAttribute: string;
  posterSelector: string;
  posterAttribute: string;
  videoSelector: string;
  videoAttribute: string;
}

const emptyFieldRow = (name = ""): FieldRow => ({
  name,
  selector: "",
  attribute: "text",
  multiple: false,
  extractionMode: "value",
  containerSelector: "",
  keySelector: "",
  keyAttribute: "text",
  valueSelector: "",
  valueAttribute: "text",
  posterSelector: "",
  posterAttribute: "src",
  videoSelector: "",
  videoAttribute: "src",
});

function fieldsToRows(fields: Record<string, ScrapeFieldConfig>): FieldRow[] {
  return Object.entries(fields).map(([name, field]) => ({
    ...emptyFieldRow(name),
    ...field,
    selector: field.selector ?? "",
    containerSelector: field.containerSelector ?? "",
    keySelector: field.keySelector ?? "",
    valueSelector: field.valueSelector ?? "",
    posterSelector: field.posterSelector ?? "",
    videoSelector: field.videoSelector ?? "",
    extractionMode: field.extractionMode ?? "value",
  }));
}

function rowsToFields(rows: FieldRow[]): Record<string, ScrapeFieldConfig> {
  const fields: Record<string, ScrapeFieldConfig> = {};
  for (const row of rows) {
    const name = row.name.trim();
    if (!name) continue;
    if (row.extractionMode === "value" && row.selector.trim()) {
      fields[name] = {
        selector: row.selector.trim(),
        attribute: row.attribute,
        multiple: row.multiple,
        extractionMode: "value",
      };
    } else if (row.extractionMode === "keyValue" && row.containerSelector.trim()) {
      fields[name] = {
        attribute: "text",
        multiple: true,
        extractionMode: "keyValue",
        containerSelector: row.containerSelector.trim(),
        keySelector: row.keySelector.trim() || null,
        keyAttribute: row.keyAttribute,
        valueSelector: row.valueSelector.trim() || null,
        valueAttribute: row.valueAttribute,
      };
    } else if (row.extractionMode === "posterVideo" && row.containerSelector.trim()) {
      fields[name] = {
        attribute: "text",
        multiple: true,
        extractionMode: "posterVideo",
        containerSelector: row.containerSelector.trim(),
        posterSelector: row.posterSelector.trim() || null,
        posterAttribute: row.posterAttribute,
        videoSelector: row.videoSelector.trim() || null,
        videoAttribute: row.videoAttribute,
      };
    }
  }
  return fields;
}

const EMPTY_FIELD_ROWS: FieldRow[] = [emptyFieldRow("phone")];

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
  const proxyPools = useProxyPools(open);

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
  const [proxyPoolId, setProxyPoolId] = useState("");
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
      setProxyPoolId("");
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
    setProxyPoolId(detail.data.proxyPoolId ?? "");
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
      setProxyPoolId(detail.data.proxyPoolId ?? "");
      setWaitSelector("");
      setWaitMs("");
      setFieldRows(EMPTY_FIELD_ROWS);
    }
  }, [isEdit, detail.data]);

  function updateFieldRow(index: number, patch: Partial<FieldRow>) {
    setFieldRows((rows) => rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }

  function addFieldRow() {
    setFieldRows((rows) => [...rows, emptyFieldRow()]);
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
          input: { name, priority, scrapeConfig, watermarkRemoval, proxyPoolId: proxyPoolId || null, ...(baseUrl.trim() ? { baseUrl: baseUrl.trim() } : {}) },
        });
      } else {
        await createSource.mutateAsync({ name, slug, baseUrl, priority, scrapeConfig, watermarkRemoval, proxyPoolId: proxyPoolId || null });
      }
      onClose();
    } catch (err) {
      setFormError(describeError(err).description);
    }
  }

  async function handleTestConfig() {
    if (!editingSource) return;
    setTestResult(null);
    const scrapeConfig = buildScrapeConfig();
    if (!scrapeConfig) {
      setTestResult({
        adUrlsFound: 0,
        sampleUrl: null,
        extractedFields: null,
        warnings: [],
        error: "Completa la configurazione di acquisizione prima di provarla.",
        errorCode: null,
        httpStatus: null,
        recommendedActions: [],
        pagesVisited: 0,
        configuredMaxPages: 1,
        paginationMode: "none",
        paginationStopReason: "not_started",
        uniqueAdsFound: 0,
      });
      return;
    }
    try {
      const result = await testConfig.mutateAsync({ id: editingSource.id, scrapeConfig, proxyPoolId: proxyPoolId || null });
      setTestResult(result);
    } catch (err) {
      setTestResult({
        adUrlsFound: 0,
        sampleUrl: null,
        extractedFields: null,
        warnings: [],
        error: describeError(err).description,
        errorCode: "fetch_failed",
        httpStatus: null,
        recommendedActions: [],
        pagesVisited: 0,
        configuredMaxPages: scrapeConfig.maxPages,
        paginationMode: "none",
        paginationStopReason: "failed",
        uniqueAdsFound: 0,
      });
    }
  }

  const isSaving = createSource.isPending || updateSource.isPending;

  return (
    <Dialog open={open} onClose={onClose} title={isEdit ? "Modifica fonte" : "Aggiungi fonte"} size="xl">
      <form onSubmit={handleSubmit} className="flex flex-col gap-4 max-h-[65vh] overflow-y-auto pr-1">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label htmlFor="source-name" className="text-label-sm text-on-surface-variant block mb-1">
              Nome
            </label>
            <Input id="source-name" required value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div>
            <label htmlFor="source-priority" className="text-label-sm text-on-surface-variant block mb-1">
              Priorità
            </label>
            <Select
              id="source-priority"
              className="w-full"
              value={priority}
              onChange={(e) => setPriority(e.target.value as SourcePriority)}
            >
              <option value="high">Alta</option>
              <option value="medium">Media</option>
              <option value="low">Bassa</option>
            </Select>
          </div>
        </div>

        {!isEdit && (
          <div>
            <label htmlFor="source-slug" className="text-label-sm text-on-surface-variant block mb-1">
              Slug (identificatore univoco, solo minuscole e trattini bassi)
            </label>
            <Input
              id="source-slug"
              required
              mono
              pattern="[a-z0-9_]+"
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
              placeholder="mia_nuova_fonte"
            />
          </div>
        )}

        <div>
          <label htmlFor="source-base-url" className="text-label-sm text-on-surface-variant block mb-1">
            URL di base {isEdit && <span className="text-outline">(lascia vuoto per mantenere quello attuale)</span>}
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
          <h4 className="text-body-md font-semibold text-on-surface mb-1">Configurazione acquisizione</h4>
          <p className="text-label-sm text-on-surface-variant mb-3">
            Opzionale alla creazione. Il motore usa esclusivamente i selettori CSS configurati qui per il sito specifico.
          </p>

          <div className="space-y-3">
            <div>
              <label htmlFor="source-start-urls" className="text-label-sm text-on-surface-variant block mb-1">
                URL iniziali (uno per riga)
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
                  Selettore collegamento annuncio (CSS)
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
                  Selettore pagina successiva (opzionale)
                </label>
                <Input
                  id="source-next-page-selector"
                  mono
                  value={nextPageSelector}
                  onChange={(e) => setNextPageSelector(e.target.value)}
                  placeholder="a.pagination-next"
                />
                <p className="mt-1 text-xs text-on-surface-variant">
                  Deve identificare un solo controllo “Successiva”. I collegamenti usano automaticamente href; le modalità browser possono usare un controllo JavaScript.
                </p>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-3">
              <div>
                <label htmlFor="source-max-pages" className="text-label-sm text-on-surface-variant block mb-1">
                  Pagine massime
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
                  Annunci massimi per esecuzione
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
                  Intervallo richieste (s)
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
                User-Agent (opzionale)
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
                Modalità di acquisizione
              </label>
              <Select
                id="source-fetch-mode"
                className="w-full"
                value={fetchMode}
                onChange={(e) => setFetchMode(e.target.value as ScrapeFetchMode)}
              >
                <option value="http">HTTP (Scrapling)</option>
                <option value="dynamic">JavaScript dinamico (browser Scrapling)</option>
                <option value="stealth">Modalità discreta (anti-bot Scrapling)</option>
              </Select>
            </div>

            {fetchMode !== "http" && (
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label htmlFor="source-wait-selector" className="text-label-sm text-on-surface-variant block mb-1">
                    Selettore di attesa (opzionale)
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
                    Attesa aggiuntiva (ms)
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

            <div className="space-y-2 border border-border rounded p-3">
              <label htmlFor="source-proxy-pool" className="text-label-sm text-on-surface-variant block">
                Pool proxy
              </label>
              <Select id="source-proxy-pool" value={proxyPoolId} onChange={(e) => setProxyPoolId(e.target.value)}>
                <option value="">Connessione diretta</option>
                {proxyPools.data?.map((pool) => (
                  <option key={pool.id} value={pool.id} disabled={!pool.enabled}>
                    {pool.name} ({pool.healthyCount}/{pool.totalCount} disponibili)
                  </option>
                ))}
              </Select>
              {proxyPoolId && (
                <p className="text-label-sm text-warning">
                  Fail-closed: lo scan verrà bloccato se nessun proxy del pool è disponibile.
                </p>
              )}
            </div>

            {fetchMode === "stealth" && (
              <div className="space-y-3 border border-border rounded p-3">
                <div className="grid grid-cols-2 gap-2">
                  {[
                    ["solveCloudflare", "Gestisci Cloudflare", solveCloudflare, setSolveCloudflare],
                    ["blockWebrtc", "Blocca WebRTC", blockWebrtc, setBlockWebrtc],
                    ["hideCanvas", "Nascondi canvas", hideCanvas, setHideCanvas],
                    ["realChrome", "Chrome reale", realChrome, setRealChrome],
                    ["blockAds", "Blocca pubblicità", blockAds, setBlockAds],
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
                  Campi da estrarre (è obbligatorio un campo <code>phone</code>)
                </span>
                <button type="button" onClick={addFieldRow} className="text-label-sm text-primary hover:underline">
                  + Aggiungi campo
                </button>
              </div>
              <div className="space-y-2">
                {fieldRows.map((row, index) => (
                  <div key={index} className="border-b border-border pb-2 last:border-b-0">
                    <div className="grid grid-cols-1 gap-2 items-center lg:grid-cols-[minmax(8rem,1fr)_minmax(12rem,2fr)_minmax(6rem,0.7fr)_auto_minmax(10rem,1fr)_auto]">
                      <Input
                        mono
                        placeholder="nome campo"
                        value={row.name}
                        onChange={(e) => updateFieldRow(index, { name: e.target.value })}
                      />
                      <Input
                        mono
                        disabled={row.extractionMode !== "value"}
                        placeholder={row.extractionMode === "value" ? "selettore CSS" : "usa il container sotto"}
                        value={row.selector}
                        onChange={(e) => updateFieldRow(index, { selector: e.target.value })}
                      />
                      <Select
                        disabled={row.extractionMode !== "value"}
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
                          disabled={row.extractionMode !== "value"}
                          checked={row.extractionMode === "value" ? row.multiple : true}
                          onChange={(e) => updateFieldRow(index, { multiple: e.target.checked })}
                        />
                        multi
                      </label>
                      <Select
                        aria-label={`Tipo estrazione ${row.name || index + 1}`}
                        value={row.extractionMode}
                        onChange={(e) => updateFieldRow(index, { extractionMode: e.target.value as ScrapeFieldExtractionMode })}
                      >
                        <option value="value">Valore</option>
                        <option value="keyValue">Chiave + valore</option>
                        <option value="posterVideo">Poster + video</option>
                      </Select>
                      <button
                        type="button"
                        onClick={() => removeFieldRow(index)}
                        className="text-on-surface-variant hover:text-error"
                        aria-label={`Rimuovi campo ${row.name || index + 1}`}
                      >
                        <Icon name="close" size={16} />
                      </button>
                    </div>
                    {row.extractionMode === "keyValue" && (
                      <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-[1.4fr_1.4fr_0.7fr_1.4fr_0.7fr] lg:pl-2">
                        <Input mono placeholder="containerSelector" value={row.containerSelector} onChange={(e) => updateFieldRow(index, { containerSelector: e.target.value })} />
                        <Input mono placeholder="keySelector" value={row.keySelector} onChange={(e) => updateFieldRow(index, { keySelector: e.target.value })} />
                        <Select value={row.keyAttribute} onChange={(e) => updateFieldRow(index, { keyAttribute: e.target.value })}>
                          <option value="text">text</option><option value="href">href</option><option value="src">src</option>
                        </Select>
                        <Input mono placeholder="valueSelector" value={row.valueSelector} onChange={(e) => updateFieldRow(index, { valueSelector: e.target.value })} />
                        <Select value={row.valueAttribute} onChange={(e) => updateFieldRow(index, { valueAttribute: e.target.value })}>
                          <option value="text">text</option><option value="href">href</option><option value="src">src</option>
                        </Select>
                      </div>
                    )}
                    {row.extractionMode === "posterVideo" && (
                      <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-[1.4fr_1.4fr_0.7fr_1.4fr_0.7fr] lg:pl-2">
                        <Input mono placeholder="containerSelector" value={row.containerSelector} onChange={(e) => updateFieldRow(index, { containerSelector: e.target.value })} />
                        <Input mono placeholder="posterSelector" value={row.posterSelector} onChange={(e) => updateFieldRow(index, { posterSelector: e.target.value })} />
                        <Select value={row.posterAttribute} onChange={(e) => updateFieldRow(index, { posterAttribute: e.target.value })}>
                          <option value="src">src</option><option value="href">href</option>
                        </Select>
                        <Input mono placeholder="videoSelector" value={row.videoSelector} onChange={(e) => updateFieldRow(index, { videoSelector: e.target.value })} />
                        <Select value={row.videoAttribute} onChange={(e) => updateFieldRow(index, { videoAttribute: e.target.value })}>
                          <option value="src">src</option><option value="href">href</option>
                        </Select>
                      </div>
                    )}
                  </div>
                ))}
              </div>
              <div className="rounded border border-border bg-surface-container-low p-2 text-label-sm text-on-surface-variant">
                <p>
                  I campi media devono chiamarsi <code>images</code> o <code>videos</code> e avere <code>multi</code> abilitato.
                </p>
                <p className="mt-1 font-mono">Anteprima: img.full-image + src</p>
                <p className="font-mono">Originale: a:has(img.full-image) + href</p>
              </div>
            </div>

            {isEdit && (
              <div className="border-t border-border pt-3">
                <Button type="button" variant="secondary" onClick={handleTestConfig} disabled={testConfig.isPending}>
                  {testConfig.isPending ? "Verifica…" : "Prova configurazione"}
                </Button>
                {testResult && (
                  <div className="mt-2 text-label-sm bg-surface-container-low border border-border rounded p-2">
                    {testResult.error ? (
                      <div className="space-y-2 text-error">
                        <div className="flex flex-wrap items-center gap-2">
                          {testResult.errorCode && (
                            <span className="rounded bg-error/10 px-1.5 py-0.5 font-mono">
                              {testResult.errorCode}
                            </span>
                          )}
                          {testResult.httpStatus && (
                            <span className="font-mono">HTTP {testResult.httpStatus}</span>
                          )}
                        </div>
                        <p>{testResult.error}</p>
                        {testResult.recommendedActions.length > 0 && (
                          <ul className="list-disc space-y-1 pl-5 text-on-surface-variant">
                            {testResult.recommendedActions.map((action) => (
                              <li key={action}>{action}</li>
                            ))}
                          </ul>
                        )}
                      </div>
                    ) : (
                      <>
                        <p className="text-on-surface">Trovati {testResult.adUrlsFound} collegamenti ad annunci.</p>
                        <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 font-mono text-on-surface-variant">
                          <span>
                            Pagine: {testResult.pagesVisited}/{testResult.configuredMaxPages}
                          </span>
                          <span>Annunci unici: {testResult.uniqueAdsFound}</span>
                          <span>Modalità: {testResult.paginationMode}</span>
                          <span>Arresto: {testResult.paginationStopReason}</span>
                        </div>
                        {testResult.sampleUrl && (
                          <p className="font-mono text-on-surface-variant truncate">Esempio: {testResult.sampleUrl}</p>
                        )}
                        {testResult.warnings.length > 0 && (
                          <div className="mt-2 rounded border border-warning/40 bg-warning/10 p-2 text-warning">
                            {testResult.warnings.map((warning) => (
                              <p key={warning}>{warning}</p>
                            ))}
                          </div>
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
              <p className="text-label-sm text-outline">Salva prima la fonte per provarne la configurazione.</p>
            )}
          </div>
        </div>

        <fieldset className="border border-border rounded-lg p-3 space-y-3">
          <legend className="px-1 text-label-sm text-on-surface">Rimozione filigrana autorizzata</legend>
          <label className="flex items-center gap-2 text-body-md text-on-surface-variant">
            <input type="checkbox" checked={watermarkEnabled} onChange={(event) => setWatermarkEnabled(event.target.checked)} />
            Abilita per questa fonte (gli originali vengono sempre conservati)
          </label>
          {watermarkEnabled && (
            <>
              <Input
                required
                value={watermarkAuthorization}
                onChange={(event) => setWatermarkAuthorization(event.target.value)}
                placeholder="Riferimento del contratto, ticket o autorizzazione legale"
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
            Annulla
          </Button>
          <Button type="submit" disabled={isSaving}>
            {isSaving ? "Salvataggio…" : isEdit ? "Salva modifiche" : "Aggiungi fonte"}
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
    <Dialog open={source !== null} onClose={handleClose} title="Elimina fonte">
      <div className="flex flex-col gap-4">
        <p className="text-body-md text-on-surface">
          Eliminare la fonte <span className="font-semibold">{source?.name}</span>? L’operazione è bloccata se esistono annunci collegati.
        </p>
        {deleteSource.isError && (
          <p className="text-body-md text-error">{describeError(deleteSource.error).description}</p>
        )}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={handleClose}>
            Annulla
          </Button>
          <Button type="button" variant="danger" onClick={handleConfirm} disabled={deleteSource.isPending}>
            {deleteSource.isPending ? "Eliminazione…" : "Elimina"}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

function duplicateSlugSuggestion(source: Source, sources: Source[]): string {
  const used = new Set(sources.map((item) => item.code));
  for (let copyNumber = 1; ; copyNumber += 1) {
    const suffix = copyNumber === 1 ? "_copy" : `_copy_${copyNumber}`;
    const candidate = `${source.code.slice(0, 100 - suffix.length)}${suffix}`;
    if (!used.has(candidate)) return candidate;
  }
}

function DuplicateSourceDialog({
  source,
  sources,
  onClose,
}: {
  source: Source | null;
  sources: Source[];
  onClose: () => void;
}) {
  const duplicateSource = useDuplicateSource();
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");

  useEffect(() => {
    if (!source) return;
    setName(`${source.name} (copia)`);
    setSlug(duplicateSlugSuggestion(source, sources));
  }, [source, sources]);

  function handleClose() {
    duplicateSource.reset();
    onClose();
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!source) return;
    try {
      await duplicateSource.mutateAsync({ id: source.id, input: { name, slug } });
      handleClose();
    } catch {
      // The mutation error is rendered below and the dialog stays open.
    }
  }

  return (
    <Dialog open={source !== null} onClose={handleClose} title="Duplica fonte">
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <p className="text-body-md text-on-surface-variant">
          Verranno copiate tutte le impostazioni di acquisizione e filigrana. La copia nasce disabilitata e senza annunci o cronologia.
        </p>
        <div>
          <label htmlFor="duplicate-source-name" className="text-label-sm text-on-surface-variant block mb-1">
            Nome
          </label>
          <Input
            id="duplicate-source-name"
            data-dialog-initial-focus
            required
            maxLength={200}
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </div>
        <div>
          <label htmlFor="duplicate-source-slug" className="text-label-sm text-on-surface-variant block mb-1">
            Slug (identificatore univoco)
          </label>
          <Input
            id="duplicate-source-slug"
            required
            maxLength={100}
            pattern="[a-z0-9_]+"
            value={slug}
            onChange={(event) => setSlug(event.target.value)}
          />
        </div>
        {duplicateSource.isError && (
          <p className="text-body-md text-error">{describeError(duplicateSource.error).description}</p>
        )}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={handleClose}>Annulla</Button>
          <Button type="submit" disabled={duplicateSource.isPending}>
            {duplicateSource.isPending ? "Duplicazione…" : "Duplica"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

function intervalParts(minutes: number | null): { value: number; unit: ScrapeIntervalUnit } {
  if (!minutes) return { value: 1, unit: "hours" };
  if (minutes % 1440 === 0) return { value: minutes / 1440, unit: "days" };
  if (minutes % 60 === 0) return { value: minutes / 60, unit: "hours" };
  return { value: minutes, unit: "minutes" };
}

function SourceScheduleDialog({ source, onClose }: { source: Source | null; onClose: () => void }) {
  const updateSchedule = useUpdateSourceSchedule();
  const [enabled, setEnabled] = useState(false);
  const [intervalValue, setIntervalValue] = useState(1);
  const [intervalUnit, setIntervalUnit] = useState<ScrapeIntervalUnit>("hours");

  useEffect(() => {
    if (!source) return;
    const parts = intervalParts(source.scrapeIntervalMinutes);
    setEnabled(source.automaticScrapingEnabled);
    setIntervalValue(parts.value);
    setIntervalUnit(parts.unit);
    updateSchedule.reset();
  }, [source]); // eslint-disable-line react-hooks/exhaustive-deps

  const normalizedMinutes = intervalValue * ({ minutes: 1, hours: 60, days: 1440 }[intervalUnit]);
  const intervalValid = normalizedMinutes >= 15 && normalizedMinutes <= 43200;
  const canEnable = Boolean(source?.enabled && source.hasScrapeConfig);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!source || !intervalValid) return;
    try {
      await updateSchedule.mutateAsync({
        id: source.id,
        input: {
          enabled,
          intervalValue,
          intervalUnit,
          revision: source.scheduleRevision,
        },
      });
      onClose();
    } catch {
      // The safe API error remains visible in the dialog.
    }
  }

  return (
    <Dialog open={source !== null} onClose={onClose} title="Pianificazione acquisizione automatica">
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <p className="text-body-md text-on-surface-variant">
          L’intervallo parte soltanto al termine di una scansione. Anche una scansione manuale riavvia il timer, impedendo due esecuzioni contemporanee.
        </p>
        <label className="flex items-center gap-3 text-body-md text-on-surface">
          <input
            type="checkbox"
            checked={enabled}
            disabled={!canEnable}
            onChange={(event) => setEnabled(event.target.checked)}
            className="h-4 w-4 accent-primary"
          />
          Abilita acquisizione automatica
        </label>
        {!canEnable && (
          <p className="text-label-sm text-warning">
            Abilita la fonte e salva una configurazione di acquisizione prima di attivare la pianificazione.
          </p>
        )}
        {source?.proxyPoolStatus === "unavailable" && (
          <p className="text-label-sm text-warning">
            Il pool proxy selezionato non ha endpoint disponibili; le scansioni pianificate verranno bloccate senza connessione diretta.
          </p>
        )}
        <div className="grid grid-cols-[1fr_1fr] gap-3">
          <div>
            <label htmlFor="schedule-interval-value" className="text-label-sm text-on-surface-variant block mb-1">
              Intervallo
            </label>
            <Input
              id="schedule-interval-value"
              type="number"
              min={1}
              value={intervalValue}
              onChange={(event) => setIntervalValue(Number(event.target.value))}
              required
            />
          </div>
          <div>
            <label htmlFor="schedule-interval-unit" className="text-label-sm text-on-surface-variant block mb-1">
              Unità
            </label>
            <Select
              id="schedule-interval-unit"
              value={intervalUnit}
              onChange={(event) => setIntervalUnit(event.target.value as ScrapeIntervalUnit)}
            >
              <option value="minutes">Minuti</option>
              <option value="hours">Ore</option>
              <option value="days">Giorni</option>
            </Select>
          </div>
        </div>
        {!intervalValid && (
          <p className="text-label-sm text-error">L’intervallo deve essere compreso tra 15 minuti e 30 giorni.</p>
        )}
        {updateSchedule.isError && (
          <p role="alert" className="text-body-md text-error">
            {describeError(updateSchedule.error).description}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>Annulla</Button>
          <Button type="submit" disabled={!intervalValid || updateSchedule.isPending}>
            {updateSchedule.isPending ? "Salvataggio…" : "Salva pianificazione"}
          </Button>
        </div>
      </form>
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
  const enable = useEnableSource();
  const checkRobots = useCheckSourceRobots();
  const exportSources = useExportSources();
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [importOpen, setImportOpen] = useState(false);
  const [formSource, setFormSource] = useState<Source | null | "new">(null);
  const [deleteTarget, setDeleteTarget] = useState<Source | null>(null);
  const [duplicateTarget, setDuplicateTarget] = useState<Source | null>(null);
  const [scheduleTarget, setScheduleTarget] = useState<Source | null>(null);
  const [robotsResultBySource, setRobotsResultBySource] = useState<Record<string, string>>({});

  useEffect(() => {
    const visibleIds = new Set(sources.data?.map((source) => source.id) ?? []);
    setSelectedIds((current) => new Set([...current].filter((id) => visibleIds.has(id))));
  }, [sources.data]);

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

  async function handleExport(scope: "all" | "selected") {
    try {
      const document = await exportSources.mutateAsync({
        scope,
        sourceIds: scope === "selected" ? [...selectedIds] : [],
      });
      const blob = new Blob([JSON.stringify(document, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = window.document.createElement("a");
      const timestamp = new Date().toISOString().slice(0, 16).replace("T", "-").replace(":", "");
      link.href = url;
      link.download = `fonti-${timestamp}.json`;
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      // The mutation error is rendered in the page-level alert.
    }
  }

  const allSelected = Boolean(
    sources.data?.length && sources.data.every((source) => selectedIds.has(source.id)),
  );

  const cards: SummaryCardConfig[] = [
    { key: "total", label: "Fonti totali", value: summary.data?.total, accent: "border-t-primary" },
    { key: "active", label: "Attive", value: summary.data?.active, accent: "border-t-success" },
    { key: "degraded", label: "Degradate", value: summary.data?.degraded, accent: "border-t-warning" },
    { key: "offline", label: "Fuori linea", value: summary.data?.offline, accent: "border-t-error" },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:justify-between sm:items-end">
        <div>
          <h2 className="text-headline-md text-on-surface">Fonti dati</h2>
          <p className="text-body-md text-on-surface-variant mt-1">
            Manage, monitor, and configure active external data pipelines.
          </p>
        </div>
        {isAdmin && (
          <div className="flex flex-wrap justify-end gap-2">
            <Button variant="secondary" onClick={() => setImportOpen(true)}>
              <Icon name="upload" size={18} />
              Importa
            </Button>
            <Button
              variant="secondary"
              onClick={() => handleExport("selected")}
              disabled={selectedIds.size === 0 || exportSources.isPending}
            >
              <Icon name="download" size={18} />
              Esporta selezionate
            </Button>
            <Button
              variant="secondary"
              onClick={() => handleExport("all")}
              disabled={!sources.data?.length || exportSources.isPending}
            >
              <Icon name="download" size={18} />
              Esporta tutte
            </Button>
            <Button onClick={() => setFormSource("new")}>
              <Icon name="add" size={18} />
              Aggiungi fonte
            </Button>
          </div>
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
            Impossibile caricare il riepilogo delle fonti.
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
      {(enable.isError || runScan.isError || exportSources.isError) && (
        <div role="alert" className="bg-error-container/20 border border-error/20 rounded-lg p-4 text-error text-body-md">
          {describeError(enable.error ?? runScan.error ?? exportSources.error).description}
        </div>
      )}
      <div className="bg-surface-container-lowest border border-border rounded-lg shadow-[0_1px_2px_rgba(0,0,0,0.02)] flex flex-col min-h-[400px]">
        <div className="px-5 py-4 border-b border-border bg-surface-container-lowest">
          <h3 className="text-headline-sm text-on-surface flex items-center gap-2">
            <Icon name="source" className="text-primary" />
            Fonti
          </h3>
        </div>
        <Table>
          <THead>
            <Tr className="hover:bg-transparent">
              {isAdmin && (
                <Th className="w-10">
                  <input
                    type="checkbox"
                    aria-label="Seleziona tutte le fonti"
                    checked={allSelected}
                    onChange={(event) => setSelectedIds(
                      event.target.checked ? new Set(sources.data?.map((source) => source.id) ?? []) : new Set(),
                    )}
                  />
                </Th>
              )}
              <Th>Nome fonte</Th>
              <Th>Stato</Th>
              <Th className="text-right">Priorità</Th>
              <Th>Ultima scansione</Th>
              <Th>Acquisizione automatica</Th>
              <Th className="text-right">Elementi acquisiti</Th>
              <Th className="text-right">Tasso di errore</Th>
              <Th className="text-right">Azioni</Th>
            </Tr>
          </THead>
          <TBody>
            {sources.isLoading && <LoadingRow colSpan={isAdmin ? 9 : 8} />}
            {sources.isError && <ErrorRow colSpan={isAdmin ? 9 : 8} error={sources.error} onRetry={() => sources.refetch()} />}
            {sources.data && sources.data.length === 0 && <EmptyRow colSpan={isAdmin ? 9 : 8} message="Nessuna fonte configurata." />}
            {sources.data?.map((source) => {
              const isExpanded = expandedIds.has(source.id);
              const isBroken = source.consecutiveFailures >= CONSECUTIVE_FAILURES_ALERT_THRESHOLD;
              return (
              <Fragment key={source.id}>
              <Tr className={isBroken ? "bg-error-container/10" : undefined}>
                {isAdmin && (
                  <Td>
                    <input
                      type="checkbox"
                      aria-label={`Seleziona ${source.name}`}
                      checked={selectedIds.has(source.id)}
                      onChange={(event) => setSelectedIds((current) => {
                        const next = new Set(current);
                        if (event.target.checked) next.add(source.id);
                        else next.delete(source.id);
                        return next;
                      })}
                    />
                  </Td>
                )}
                <Td>
                  <div className="flex items-center gap-1.5">
                    <button
                      onClick={() => toggleExpanded(source.id)}
                      title={isExpanded ? "Nascondi cronologia esecuzioni" : "Mostra cronologia esecuzioni"}
                      className="p-0.5 text-on-surface-variant hover:text-primary rounded transition-colors"
                    >
                      <Icon name={isExpanded ? "expand_more" : "chevron_right"} size={18} />
                    </button>
                    <div>
                      <div className="font-medium text-on-surface flex items-center gap-1.5">
                        {source.name}
                        {isBroken && (
                          <span title={`${source.consecutiveFailures} esecuzioni consecutive non riuscite`}>
                            <Badge tone="error">Connettore non funzionante?</Badge>
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
                <Td>
                  <div className="space-y-1 min-w-[170px]">
                    <Badge
                      tone={
                        source.automaticScrapingState === "waiting" ? "success" :
                        source.automaticScrapingState === "running" ? "warning" :
                        source.automaticScrapingState === "pending" ? "neutral" : "neutral"
                      }
                    >
                      {source.automaticScrapingState === "waiting" ? "In attesa" : source.automaticScrapingState === "pending" ? "Pianificata" : source.automaticScrapingState === "running" ? "In esecuzione" : source.automaticScrapingState === "paused" ? "In pausa" : "Disabilitata"}
                    </Badge>
                    <div className="text-label-sm text-on-surface-variant">
                      {source.automaticScrapingEnabled
                        ? `Ogni ${formatInterval(source.scrapeIntervalMinutes)}`
                        : "Disabilitata"}
                    </div>
                    {(source.automaticScrapingState === "pending" || source.automaticScrapingState === "running") ? (
                      <div className="text-label-sm text-warning">Il timer parte al termine di questa scansione</div>
                    ) : source.nextScrapeAt ? (
                      <div className="text-label-sm text-on-surface-variant">
                        Prossima: {formatDateTime(source.nextScrapeAt)}
                      </div>
                    ) : null}
                  </div>
                </Td>
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
                      title="Controlla robots.txt"
                      className="p-1.5 text-on-surface-variant hover:text-primary hover:bg-primary/10 rounded transition-colors disabled:opacity-50"
                    >
                      <Icon name="policy" size={16} />
                    </button>
                    {canManageSources && source.enabled && source.hasScrapeConfig && (
                      <button
                        onClick={() => handleRunScan(source.id)}
                        disabled={runScan.isPending || source.automaticScrapingState === "pending" || source.automaticScrapingState === "running"}
                        title="Avvia scansione"
                        className="p-1.5 text-on-surface-variant hover:text-primary hover:bg-primary/10 rounded transition-colors disabled:opacity-50"
                      >
                        <Icon name="play_arrow" size={16} />
                      </button>
                    )}
                    {canManageSources && source.enabled && (
                      <button
                        onClick={() => pause.mutate(source.id)}
                        disabled={pause.isPending}
                        title="Metti in pausa"
                        className="p-1.5 text-on-surface-variant hover:text-primary hover:bg-primary/10 rounded transition-colors disabled:opacity-50"
                      >
                        <Icon name="pause" size={16} />
                      </button>
                    )}
                    {isAdmin && (
                      <button
                        onClick={() => setScheduleTarget(source)}
                        title="Pianificazione automatica"
                        aria-label={`Pianifica ${source.name}`}
                        className="p-1.5 text-on-surface-variant hover:text-primary hover:bg-primary/10 rounded transition-colors"
                      >
                        <Icon name="schedule" size={16} />
                      </button>
                    )}
                    {isAdmin && (
                      <button
                        onClick={() => setDuplicateTarget(source)}
                        title="Duplica"
                        aria-label={`Duplica ${source.name}`}
                        className="p-1.5 text-on-surface-variant hover:text-primary hover:bg-primary/10 rounded transition-colors"
                      >
                        <Icon name="content_copy" size={16} />
                      </button>
                    )}
                    {isAdmin && (
                      <button
                        onClick={() => setFormSource(source)}
                        title={source.hasScrapeConfig ? "Modifica configurazione" : "Configura"}
                        className="p-1.5 text-on-surface-variant hover:text-primary hover:bg-primary/10 rounded transition-colors"
                      >
                        <Icon name="tune" size={16} />
                      </button>
                    )}
                    {canManageSources && source.enabled && (
                      <button
                        onClick={() => disable.mutate(source.id)}
                        disabled={disable.isPending}
                        title="Disabilita"
                        className="p-1.5 text-on-surface-variant hover:text-error hover:bg-error-container/30 rounded transition-colors disabled:opacity-50"
                      >
                        <Icon name="block" size={16} />
                      </button>
                    )}
                    {canManageSources && !source.enabled && (
                      <button
                        onClick={() => enable.mutate(source.id)}
                        disabled={enable.isPending}
                        title="Abilita"
                        aria-label={`Abilita ${source.name}`}
                        className="p-1.5 text-on-surface-variant hover:text-success hover:bg-success/10 rounded transition-colors disabled:opacity-50"
                      >
                        <Icon name="power_settings_new" size={16} />
                      </button>
                    )}
                    {isAdmin && (
                      <button
                        onClick={() => setDeleteTarget(source)}
                        title="Elimina"
                        className="p-1.5 text-on-surface-variant hover:text-error hover:bg-error-container/30 rounded transition-colors"
                      >
                        <Icon name="delete" size={16} />
                      </button>
                    )}
                  </div>
                </Td>
              </Tr>
              {isExpanded && <SourceRunsPanel sourceId={source.id} colSpan={isAdmin ? 9 : 8} />}
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
      <DuplicateSourceDialog
        source={duplicateTarget}
        sources={sources.data ?? []}
        onClose={() => setDuplicateTarget(null)}
      />
      <SourceScheduleDialog source={scheduleTarget} onClose={() => setScheduleTarget(null)} />
      <SourceImportDialog open={importOpen} onClose={() => setImportOpen(false)} />
    </div>
  );
}
