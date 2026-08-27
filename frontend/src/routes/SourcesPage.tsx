import { useSources, useSourcesSummary, useRunSourceScan, usePauseSource, useDisableSource } from "@/hooks/useSources";
import Icon from "@/components/ui/Icon";
import Badge, { type BadgeTone } from "@/components/ui/Badge";
import { EmptyRow, ErrorRow, LoadingRow, Table, TBody, Td, Th, THead, Tr } from "@/components/ui/Table";
import type { Source, SourceStatus } from "@/types";

// Replicates desing/sources_lavoro_esterno/code.html: 4 summary cards
// (Total/Active/Degraded/Offline) followed by a sources table with
// hover-revealed row actions.

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

interface SummaryCardConfig {
  key: string;
  label: string;
  value: number | undefined;
  accent: string;
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

export default function SourcesPage() {
  const summary = useSourcesSummary();
  const sources = useSources();
  const runScan = useRunSourceScan();
  const pause = usePauseSource();
  const disable = useDisableSource();

  const cards: SummaryCardConfig[] = [
    { key: "total", label: "Total Sources", value: summary.data?.total, accent: "border-t-primary" },
    { key: "active", label: "Active", value: summary.data?.active, accent: "border-t-success" },
    { key: "degraded", label: "Degraded", value: summary.data?.degraded, accent: "border-t-warning" },
    { key: "offline", label: "Offline", value: summary.data?.offline, accent: "border-t-error" },
  ];

  // No dedicated "configure source" endpoint exists in api/sources.ts yet;
  // the button is kept for visual/mockup parity but is currently a no-op.
  function handleConfigure(source: Source) {
    console.log("Configure source (not implemented):", source.id);
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-end">
        <div>
          <h2 className="text-headline-md text-on-surface">Data Sources</h2>
          <p className="text-body-md text-on-surface-variant mt-1">
            Manage, monitor, and configure active external data pipelines.
          </p>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-4 gap-gutter">
        {summary.isLoading &&
          Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="bg-white border border-border rounded-lg p-4 h-[84px] animate-pulse" />
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
              className={`bg-white border border-border border-t-2 ${card.accent} rounded-lg p-4 shadow-[0_1px_2px_rgba(0,0,0,0.02)]`}
            >
              <h3 className="text-label-sm text-on-surface-variant uppercase tracking-wider mb-2">{card.label}</h3>
              <div className="text-headline-md text-on-surface">{card.value?.toLocaleString() ?? "-"}</div>
            </div>
          ))}
      </div>

      {/* Sources Table */}
      <div className="bg-white border border-border rounded-lg shadow-[0_1px_2px_rgba(0,0,0,0.02)] flex flex-col min-h-[400px]">
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
            {sources.isError && <ErrorRow colSpan={7} message="Failed to load sources." />}
            {sources.data && sources.data.length === 0 && <EmptyRow colSpan={7} message="No sources configured." />}
            {sources.data?.map((source) => (
              <Tr key={source.id}>
                <Td>
                  <div className="font-medium text-on-surface">{source.name}</div>
                  <div className="text-label-sm text-on-surface-variant font-mono">{source.code}</div>
                </Td>
                <Td>
                  <Badge tone={STATUS_TONE[source.status]}>{STATUS_LABEL[source.status]}</Badge>
                </Td>
                <Td className="text-right">
                  <span className="font-mono text-mono-data text-on-surface bg-surface-container px-2 py-1 rounded">
                    {source.errorRate < 0.01 ? "High" : source.errorRate < 0.05 ? "Medium" : "Low"}
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
                  <div className="flex justify-end gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button
                      onClick={() => runScan.mutate(source.id)}
                      disabled={runScan.isPending}
                      title="Run Scan"
                      className="p-1.5 text-on-surface-variant hover:text-primary hover:bg-primary/10 rounded transition-colors disabled:opacity-50"
                    >
                      <Icon name="play_arrow" size={16} />
                    </button>
                    <button
                      onClick={() => pause.mutate(source.id)}
                      disabled={pause.isPending}
                      title="Pause"
                      className="p-1.5 text-on-surface-variant hover:text-primary hover:bg-primary/10 rounded transition-colors disabled:opacity-50"
                    >
                      <Icon name="pause" size={16} />
                    </button>
                    <button
                      onClick={() => handleConfigure(source)}
                      title="Configure"
                      className="p-1.5 text-on-surface-variant hover:text-primary hover:bg-primary/10 rounded transition-colors"
                    >
                      <Icon name="tune" size={16} />
                    </button>
                    <button
                      onClick={() => disable.mutate(source.id)}
                      disabled={disable.isPending}
                      title="Disable"
                      className="p-1.5 text-on-surface-variant hover:text-error hover:bg-error-container/30 rounded transition-colors disabled:opacity-50"
                    >
                      <Icon name="block" size={16} />
                    </button>
                  </div>
                </Td>
              </Tr>
            ))}
          </TBody>
        </Table>
      </div>
    </div>
  );
}
