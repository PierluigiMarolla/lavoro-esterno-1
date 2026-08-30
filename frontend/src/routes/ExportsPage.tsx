import { useExportJobs, useCreateExportJob, useRetryExportJob } from "@/hooks/useExports";
import * as exportsApi from "@/api/exports";
import Icon from "@/components/ui/Icon";
import Badge, { type BadgeTone } from "@/components/ui/Badge";
import { EmptyRow, ErrorRow, LoadingRow, Table, TBody, Td, Th, THead, Tr } from "@/components/ui/Table";
import type { ExportJob, ExportStatus, ExportType } from "@/types";

// Replicates desing/exports_lavoro_esterno/code.html: 3 export-type cards
// that kick off a new job, plus a recent-jobs table with download/retry actions.

const STATUS_TONE: Record<ExportStatus, BadgeTone> = {
  ready: "success",
  processing: "warning",
  failed: "error",
};

const TYPE_LABEL: Record<ExportType, string> = {
  text_only: "Text Only",
  complete_media: "Complete (Media)",
  safe_complete: "Safe Complete",
};

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString([], { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

interface ExportTypeCardConfig {
  type: ExportType;
  icon: string;
  badge: string;
  title: string;
  description: string;
}

const EXPORT_TYPE_CARDS: ExportTypeCardConfig[] = [
  {
    type: "text_only",
    icon: "description",
    badge: "Fastest",
    title: "Text Only",
    description: "JSON/CSV payload containing structural data, classifications, and metadata without media files.",
  },
  {
    type: "complete_media",
    icon: "perm_media",
    badge: "Standard",
    title: "Complete (Media)",
    description: "Full data payload including all scraped images, videos, and associated media assets.",
  },
  {
    type: "safe_complete",
    icon: "filter_b_and_w",
    badge: "Filtered",
    title: "Safe Complete",
    description: "Full data payload with automated filtering to exclude explicit or sensitive media content.",
  },
];

export default function ExportsPage() {
  const jobs = useExportJobs();
  const createJob = useCreateExportJob();
  const retryJob = useRetryExportJob();

  async function handleDownload(job: ExportJob) {
    // Backend streams the file behind a signed URL; resolve it then open in a new tab.
    const { url } = await exportsApi.getExportDownloadUrl(job.id);
    window.open(url, "_blank", "noopener,noreferrer");
  }

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-headline-md text-on-surface mb-1">Export Management</h2>
        <p className="text-body-md text-on-surface-variant">Configure and monitor data extraction jobs.</p>
      </div>

      {/* New Export Job cards */}
      <section>
        <h3 className="text-headline-sm text-on-surface mb-4">New Export Job</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-gutter">
          {EXPORT_TYPE_CARDS.map((card) => {
            const isPrimary = card.type === "complete_media";
            return (
              <div
                key={card.type}
                data-testid={`export-card-${card.type}`}
                className={
                  isPrimary
                    ? "bg-surface-container-lowest rounded-lg border border-primary p-6 shadow-sm relative overflow-hidden"
                    : "bg-surface-container-lowest rounded-lg border border-border p-6 shadow-[0_1px_2px_rgba(0,0,0,0.02)] relative overflow-hidden"
                }
              >
                <div className="flex items-start justify-between mb-4">
                  <div className={isPrimary ? "p-2 bg-primary-container text-on-primary rounded shadow-sm" : "p-2 bg-surface-container-low text-primary rounded"}>
                    <Icon name={card.icon} />
                  </div>
                  <span
                    className={
                      isPrimary
                        ? "px-2 py-0.5 bg-primary-container text-on-primary rounded text-label-sm"
                        : "px-2 py-0.5 bg-surface-container-lowest border border-border rounded text-label-sm text-on-surface-variant"
                    }
                  >
                    {card.badge}
                  </span>
                </div>
                <h4 className="text-body-lg font-medium text-on-surface mb-2">{card.title}</h4>
                <p className="text-body-md text-on-surface-variant mb-4">{card.description}</p>
                <button
                  onClick={() => createJob.mutate({ type: card.type })}
                  disabled={createJob.isPending}
                  className={
                    isPrimary
                      ? "bg-primary text-on-primary hover:bg-primary-container transition-colors rounded px-4 py-1.5 text-label-sm font-medium w-full disabled:opacity-50"
                      : "text-primary text-label-sm font-medium flex items-center hover:underline disabled:opacity-50"
                  }
                >
                  {isPrimary ? (
                    "Create Export"
                  ) : (
                    <>
                      Create Export <Icon name="arrow_forward" size={16} className="ml-1" />
                    </>
                  )}
                </button>
              </div>
            );
          })}
        </div>
      </section>

      {/* Recent Jobs */}
      <section>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-headline-sm text-on-surface">Recent Jobs</h3>
          <button
            onClick={() => jobs.refetch()}
            className="p-1 text-on-surface-variant hover:bg-surface-container-low rounded border border-border"
            title="Refresh"
          >
            <Icon name="refresh" size={20} />
          </button>
        </div>
        <div className="bg-surface-container-lowest border border-border rounded-lg overflow-hidden">
          <Table>
            <THead>
              <Tr className="hover:bg-transparent">
                <Th>Type</Th>
                <Th>Requested By</Th>
                <Th>Requested At</Th>
                <Th className="text-right">Records</Th>
                <Th>Status</Th>
                <Th className="text-right">Actions</Th>
              </Tr>
            </THead>
            <TBody>
              {jobs.isLoading && <LoadingRow colSpan={6} />}
              {jobs.isError && <ErrorRow colSpan={6} error={jobs.error} onRetry={() => jobs.refetch()} />}
              {jobs.data && jobs.data.length === 0 && <EmptyRow colSpan={6} message="No export jobs yet." />}
              {jobs.data?.map((job) => (
                <Tr key={job.id}>
                  <Td className="text-on-surface-variant">{TYPE_LABEL[job.type]}</Td>
                  <Td className="text-on-surface-variant">{job.requestedBy}</Td>
                  <Td className="text-on-surface-variant">{formatDateTime(job.requestedAt)}</Td>
                  <Td className="text-right font-mono text-on-surface">{job.recordCount.toLocaleString()}</Td>
                  <Td>
                    <Badge tone={STATUS_TONE[job.status]}>
                      {job.status === "processing" ? `Processing (${job.progressPct}%)` : job.status === "ready" ? "Ready" : "Failed"}
                    </Badge>
                  </Td>
                  <Td className="text-right">
                    {job.status === "ready" && (
                      <button
                        onClick={() => handleDownload(job)}
                        className="text-primary hover:text-primary-container text-label-sm font-medium inline-flex items-center justify-end"
                      >
                        <Icon name="download" size={18} className="mr-1" /> Download
                      </button>
                    )}
                    {job.status === "processing" && (
                      <span className="text-on-surface-variant opacity-50 text-label-sm font-medium inline-flex items-center justify-end">
                        <Icon name="download" size={18} className="mr-1" /> Download
                      </span>
                    )}
                    {job.status === "failed" && (
                      <button
                        onClick={() => retryJob.mutate(job.id)}
                        disabled={retryJob.isPending}
                        className="text-on-surface-variant hover:text-on-surface text-label-sm font-medium inline-flex items-center justify-end disabled:opacity-50"
                      >
                        <Icon name="refresh" size={18} className="mr-1" /> Retry
                      </button>
                    )}
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
