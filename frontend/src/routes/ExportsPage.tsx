import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useExportJobs, useCreateExportJob, useRetryExportJob } from "@/hooks/useExports";
import * as exportsApi from "@/api/exports";
import Icon from "@/components/ui/Icon";
import Badge, { type BadgeTone } from "@/components/ui/Badge";
import { EmptyRow, ErrorRow, LoadingRow, Table, TBody, Td, Th, THead, Tr } from "@/components/ui/Table";
import type { ExportFilters, ExportJob, ExportStatus, ExportType } from "@/types";

const STATUS_TONE: Record<ExportStatus, BadgeTone> = {
  pending: "neutral",
  ready: "success",
  processing: "warning",
  failed: "error",
};

const TYPE_LABEL: Record<ExportType, string> = {
  text_only: "Text Only",
  complete_media: "Complete (Media)",
  safe_complete: "Safe Complete",
};

const CARDS: { type: ExportType; icon: string; description: string }[] = [
  { type: "text_only", icon: "description", description: "JSON and CSV, without media files." },
  { type: "complete_media", icon: "perm_media", description: "Data plus display and thumbnail variants." },
  { type: "safe_complete", icon: "filter_b_and_w", description: "Only ready, definitively safe media." },
];

function formatDateTime(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString() : "—";
}

function formatBytes(value: number | null): string {
  if (value === null) return "—";
  if (value < 1024) return `${value} B`;
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`;
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(1)} MB`;
  return `${(value / 1024 ** 3).toFixed(2)} GB`;
}

export default function ExportsPage() {
  const [params] = useSearchParams();
  const jobs = useExportJobs();
  const createJob = useCreateExportJob();
  const retryJob = useRetryExportJob();
  const [manualIds, setManualIds] = useState("");
  const [phone, setPhone] = useState("");
  const [source, setSource] = useState("");
  const [status, setStatus] = useState<ExportFilters["status"]>();

  const inboundIds = useMemo(
    () => (params.get("recordIds") ?? "").split(",").map((value) => value.trim()).filter(Boolean),
    [params],
  );
  const inboundFilters = useMemo<ExportFilters | undefined>(() => {
    if (params.get("scope") !== "filters") return undefined;
    return {
      phone: params.get("phone") || undefined,
      source: params.get("source") || undefined,
      status: (params.get("status") as ExportFilters["status"]) || undefined,
      dateFrom: params.get("dateFrom") || undefined,
      dateTo: params.get("dateTo") || undefined,
    };
  }, [params]);

  const typedIds = manualIds.split(/[\s,]+/).map((value) => value.trim()).filter(Boolean);
  const localFilters: ExportFilters | undefined = phone || source || status ? { phone: phone || undefined, source: source || undefined, status } : undefined;
  const recordIds = inboundIds.length ? inboundIds : typedIds.length ? typedIds : undefined;
  const filters = recordIds ? undefined : inboundFilters ?? localFilters;
  const hasScope = Boolean(recordIds?.length || filters);
  const scopeLabel = recordIds?.length
    ? `${recordIds.length} selected record${recordIds.length === 1 ? "" : "s"}`
    : filters
      ? "all records matching the explicit filters"
      : "no scope selected";

  async function handleDownload(job: ExportJob) {
    const { url } = await exportsApi.getExportDownloadUrl(job.id);
    window.open(url, "_blank", "noopener,noreferrer");
  }

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-headline-md text-on-surface mb-1">Export Management</h2>
        <p className="text-body-md text-on-surface-variant">Exports require selected records or explicit filters. Limits: 1,000 records and 2 GB.</p>
      </div>

      <section className="bg-surface-container-lowest border border-border rounded-lg p-5 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-headline-sm">Export scope</h3>
          <Badge tone={hasScope ? "success" : "warning"}>{scopeLabel}</Badge>
        </div>
        {!inboundIds.length && !inboundFilters && (
          <div className="grid md:grid-cols-2 gap-4">
            <div>
              <label className="text-label-sm block mb-1">Record IDs (comma or line separated)</label>
              <textarea value={manualIds} onChange={(event) => setManualIds(event.target.value)} rows={3} className="w-full rounded border border-border bg-surface p-2 font-mono text-sm" />
            </div>
            <div className="grid gap-2">
              <input value={phone} onChange={(event) => setPhone(event.target.value)} placeholder="Exact phone filter" disabled={typedIds.length > 0} className="rounded border border-border bg-surface p-2" />
              <input value={source} onChange={(event) => setSource(event.target.value)} placeholder="Source slug or name" disabled={typedIds.length > 0} className="rounded border border-border bg-surface p-2" />
              <select value={status ?? ""} onChange={(event) => setStatus((event.target.value || undefined) as ExportFilters["status"])} disabled={typedIds.length > 0} className="rounded border border-border bg-surface p-2">
                <option value="">Any status</option><option value="verified">Verified</option><option value="unverified">Unverified</option><option value="flagged">Flagged</option>
              </select>
            </div>
          </div>
        )}
      </section>

      <section>
        <h3 className="text-headline-sm text-on-surface mb-4">New Export Job</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-gutter">
          {CARDS.map((card) => (
            <div key={card.type} data-testid={`export-card-${card.type}`} className="bg-surface-container-lowest rounded-lg border border-border p-6">
              <Icon name={card.icon} className="text-primary mb-3" />
              <h4 className="text-body-lg font-medium mb-2">{TYPE_LABEL[card.type]}</h4>
              <p className="text-body-md text-on-surface-variant mb-4">{card.description}</p>
              <button
                onClick={() => createJob.mutate({ type: card.type, recordIds, filters })}
                disabled={!hasScope || createJob.isPending}
                className="bg-primary text-on-primary rounded px-4 py-2 text-label-sm w-full disabled:opacity-40"
              >
                {createJob.isPending ? "Creating…" : "Create Export"}
              </button>
            </div>
          ))}
        </div>
        {createJob.isError && <p className="text-error text-body-md mt-3">{createJob.error instanceof Error ? createJob.error.message : "Export request failed."}</p>}
      </section>

      <section>
        <h3 className="text-headline-sm text-on-surface mb-4">Recent Jobs</h3>
        <div className="bg-surface-container-lowest border border-border rounded-lg overflow-hidden">
          <Table><THead><Tr><Th>Type</Th><Th>Requested</Th><Th>Records</Th><Th>Size</Th><Th>Phone</Th><Th>Status</Th><Th className="text-right">Actions</Th></Tr></THead>
            <TBody>
              {jobs.isLoading && <LoadingRow colSpan={7} />}
              {jobs.isError && <ErrorRow colSpan={7} error={jobs.error} onRetry={() => jobs.refetch()} />}
              {jobs.data?.length === 0 && <EmptyRow colSpan={7} message="No export jobs yet." />}
              {jobs.data?.map((job) => (
                <Tr key={job.id}>
                  <Td>{TYPE_LABEL[job.type]}</Td><Td>{formatDateTime(job.requestedAt)}<div className="text-xs text-on-surface-variant">{job.requestedBy}</div></Td>
                  <Td>{job.recordCount}</Td><Td>{formatBytes(job.archiveSizeBytes ?? job.estimatedUncompressedBytes)}</Td><Td>{job.phoneVisibility}</Td>
                  <Td><Badge tone={STATUS_TONE[job.status]}>{job.status === "processing" ? `Processing ${job.progressPct}%` : job.status}</Badge>{job.errorMessage && <div className="text-xs text-error mt-1 max-w-xs">{job.errorMessage}</div>}</Td>
                  <Td className="text-right">
                    {job.status === "ready" && <button onClick={() => handleDownload(job)} className="text-primary">Download</button>}
                    {job.status === "failed" && <button onClick={() => retryJob.mutate(job.id)} className="text-primary">Retry</button>}
                  </Td>
                </Tr>
              ))}
            </TBody>
          </Table>
        </div>
      </section>
    </div>
  );
}
