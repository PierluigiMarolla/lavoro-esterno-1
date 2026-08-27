import { useDashboardKpis, useRecentActivity, useScrapingActivity, useSourceHealth } from "@/hooks/useDashboard";
import Icon from "@/components/ui/Icon";
import Badge, { type BadgeTone } from "@/components/ui/Badge";
import ProgressBar from "@/components/ui/ProgressBar";
import { EmptyRow, ErrorRow, LoadingRow, Table, TBody, Td, Th, THead, Tr } from "@/components/ui/Table";
import type { ScrapingRunStatus } from "@/types";

// Replicates desing/dashboard_lavoro_esterno/code.html: 5 KPI cards with a
// colored top border, a scraping activity table, a source health panel with
// 3 progress bars, and a recent activity timeline.

const STATUS_TONE: Record<ScrapingRunStatus, BadgeTone> = {
  running: "success",
  completed: "success",
  failed: "error",
  rate_limited: "warning",
  queued: "neutral",
};

const STATUS_LABEL: Record<ScrapingRunStatus, string> = {
  running: "Running",
  completed: "Completed",
  failed: "Failed",
  rate_limited: "Rate Limited",
  queued: "Queued",
};

function formatDuration(seconds: number | null): string {
  if (seconds === null) return "-";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m >= 60) return `${Math.floor(m / 60)}h ${m % 60}m`;
  return `${m}m ${s}s`;
}

function formatTime(iso: string | null): string {
  if (!iso) return "-";
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

interface KpiCardConfig {
  key: string;
  label: string;
  icon: string;
  accent: string; // top border + icon color utility
  value: string;
  trend?: { icon: string; label: string; tone: string };
}

export default function DashboardPage() {
  const kpis = useDashboardKpis();
  const activity = useScrapingActivity();
  const health = useSourceHealth();
  const recent = useRecentActivity();

  const cards: KpiCardConfig[] | null = kpis.data
    ? [
        {
          key: "total",
          label: "Total Records",
          icon: "database",
          accent: "bg-primary text-primary",
          value: kpis.data.totalRecords.toLocaleString(),
          trend: { icon: "trending_up", label: `+${kpis.data.totalRecordsDeltaPct}% this week`, tone: "text-success" },
        },
        {
          key: "sources",
          label: "Active Sources",
          icon: "source",
          accent: "bg-info text-info",
          value: kpis.data.activeSources.toLocaleString(),
          trend: { icon: "check_circle", label: `${kpis.data.activeSourcesHealthyPct}% healthy`, tone: "text-on-surface-variant" },
        },
        {
          key: "new-today",
          label: "New Today",
          icon: "add_box",
          accent: "bg-success text-success",
          value: kpis.data.newRecordsToday.toLocaleString(),
          trend: { icon: "trending_up", label: "On track", tone: "text-success" },
        },
        {
          key: "errors",
          label: "Scraping Errors",
          icon: "warning",
          accent: "bg-error text-error",
          value: kpis.data.scrapingErrors.toLocaleString(),
          trend: { icon: "trending_up", label: `${kpis.data.scrapingErrorsDelta >= 0 ? "+" : ""}${kpis.data.scrapingErrorsDelta} vs yesterday`, tone: "text-error" },
        },
        {
          key: "exports",
          label: "Active Exports",
          icon: "sync",
          accent: "bg-warning text-warning",
          value: kpis.data.activeExports.toLocaleString(),
          trend: { icon: "hourglass_empty", label: "Processing...", tone: "text-warning" },
        },
      ]
    : null;

  return (
    <div className="grid grid-cols-12 gap-gutter">
      <div className="col-span-12 mb-2 flex items-end justify-between">
        <div>
          <h2 className="text-headline-md text-on-surface">Operational Overview</h2>
          <p className="text-body-md text-on-surface-variant mt-1">Real-time telemetry and extraction metrics.</p>
        </div>
        <div className="flex gap-2">
          <button className="flex items-center gap-1 px-3 py-1.5 border border-border rounded text-label-sm text-on-surface-variant hover:bg-surface-container-lowest transition-colors bg-white">
            <Icon name="calendar_today" size={16} />
            Last 24 Hours
          </button>
          <button
            onClick={() => {
              kpis.refetch();
              activity.refetch();
              health.refetch();
              recent.refetch();
            }}
            className="flex items-center gap-1 px-3 py-1.5 bg-primary text-on-primary rounded text-label-sm hover:bg-primary-container transition-colors shadow-sm"
          >
            <Icon name="refresh" size={16} />
            Refresh Data
          </button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="col-span-12 grid grid-cols-5 gap-gutter mb-2">
        {kpis.isLoading &&
          Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="bg-white border border-border rounded-lg p-4 h-[104px] animate-pulse" />
          ))}
        {kpis.isError && (
          <div className="col-span-5 bg-error-container/20 border border-error/20 rounded-lg p-4 text-error text-body-md">
            Failed to load dashboard KPIs.
          </div>
        )}
        {cards?.map((card) => (
          <div
            key={card.key}
            className="bg-white border border-border rounded-lg p-4 flex flex-col justify-between shadow-[0_1px_2px_rgba(0,0,0,0.02)] relative overflow-hidden"
          >
            <div className={`absolute top-0 left-0 w-full h-1 opacity-80 ${card.accent.split(" ")[0]}`} />
            <div className="flex justify-between items-start mb-2">
              <span className="text-label-sm text-on-surface-variant uppercase tracking-wider">{card.label}</span>
              <Icon name={card.icon} className={`opacity-50 ${card.accent.split(" ")[1]}`} />
            </div>
            <div>
              <div className="text-headline-lg font-mono text-on-surface">{card.value}</div>
              {card.trend && (
                <div className={`flex items-center gap-1 mt-1 text-label-sm ${card.trend.tone}`}>
                  <Icon name={card.trend.icon} size={14} />
                  <span>{card.trend.label}</span>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Scraping Activity */}
      <div className="col-span-8 flex flex-col gap-gutter">
        <div className="bg-white border border-border rounded-lg shadow-[0_1px_2px_rgba(0,0,0,0.02)] flex flex-col h-[500px]">
          <div className="px-5 py-4 border-b border-border flex justify-between items-center bg-surface-container-lowest">
            <h3 className="text-headline-sm text-on-surface flex items-center gap-2">
              <Icon name="data_usage" className="text-primary" />
              Scraping Activity
            </h3>
          </div>
          <Table>
            <THead>
              <Tr className="hover:bg-transparent">
                <Th className="w-1/4">Source</Th>
                <Th>Status</Th>
                <Th>Started</Th>
                <Th className="text-right">Duration</Th>
                <Th className="text-right">Items</Th>
                <Th className="text-right">Errors</Th>
              </Tr>
            </THead>
            <TBody>
              {activity.isLoading && <LoadingRow colSpan={6} />}
              {activity.isError && <ErrorRow colSpan={6} message="Failed to load scraping activity." />}
              {activity.data && activity.data.length === 0 && <EmptyRow colSpan={6} message="No scraping runs yet." />}
              {activity.data?.map((run) => (
                <Tr key={run.id}>
                  <Td>
                    <div className="font-medium text-on-surface">{run.sourceName}</div>
                    <div className="text-label-sm text-on-surface-variant font-mono">{run.sourceCode}</div>
                  </Td>
                  <Td>
                    <Badge tone={STATUS_TONE[run.status]}>{STATUS_LABEL[run.status]}</Badge>
                  </Td>
                  <Td className="text-on-surface-variant">{formatTime(run.startedAt)}</Td>
                  <Td className="text-right font-mono">{formatDuration(run.durationSeconds)}</Td>
                  <Td className="text-right font-mono text-on-surface">{run.items?.toLocaleString() ?? "-"}</Td>
                  <Td className={`text-right font-mono ${run.errors ? "font-semibold text-error" : "text-on-surface-variant"}`}>
                    {run.errors ?? "-"}
                  </Td>
                </Tr>
              ))}
            </TBody>
          </Table>
        </div>
      </div>

      {/* Right column */}
      <div className="col-span-4 flex flex-col gap-gutter">
        <div className="bg-white border border-border rounded-lg shadow-[0_1px_2px_rgba(0,0,0,0.02)] p-5">
          <h3 className="text-headline-sm text-on-surface mb-4 flex items-center gap-2">
            <Icon name="monitor_heart" className="text-info" />
            Source Health
          </h3>
          {health.isLoading && <p className="text-body-md text-on-surface-variant">Loading…</p>}
          {health.isError && <p className="text-body-md text-error">Failed to load source health.</p>}
          {health.data && (
            <div className="space-y-4">
              <HealthRow label="Healthy" value={health.data.healthy} total={health.data.total} tone="success" />
              <HealthRow label="Rate Limited" value={health.data.rateLimited} total={health.data.total} tone="warning" />
              <HealthRow label="Error State" value={health.data.error} total={health.data.total} tone="error" />
            </div>
          )}
          <button className="w-full mt-5 py-2 border border-border rounded text-label-sm text-on-surface hover:bg-surface-container-lowest transition-colors flex items-center justify-center gap-2">
            View Detailed Diagnostics
            <Icon name="arrow_forward" size={16} />
          </button>
        </div>

        <div className="bg-white border border-border rounded-lg shadow-[0_1px_2px_rgba(0,0,0,0.02)] flex-1 flex flex-col min-h-[300px]">
          <div className="px-5 py-4 border-b border-border bg-surface-container-lowest">
            <h3 className="text-headline-sm text-on-surface flex items-center gap-2">
              <Icon name="history" className="text-outline" />
              Recent Activity
            </h3>
          </div>
          <div className="p-5 overflow-y-auto flex-1 space-y-5">
            {recent.isLoading && <p className="text-body-md text-on-surface-variant">Loading…</p>}
            {recent.isError && <p className="text-body-md text-error">Failed to load activity feed.</p>}
            {recent.data && recent.data.length === 0 && (
              <p className="text-body-md text-on-surface-variant">No recent activity.</p>
            )}
            {recent.data?.map((event, i) => (
              <div key={event.id} className="relative pl-6">
                {i !== recent.data!.length - 1 && (
                  <div className="absolute left-1.5 top-1.5 bottom-[-24px] w-px bg-border" />
                )}
                <div
                  className={`absolute left-0 top-1.5 w-3 h-3 rounded-full border-2 border-white shadow-sm ${actorDotColor(event.actor)}`}
                />
                <p className="text-label-sm text-on-surface-variant mb-0.5">{formatTime(event.occurredAt)}</p>
                <p className="text-body-md text-on-surface">
                  <span className="font-semibold">{event.actorLabel}</span> {event.message}
                </p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function HealthRow({ label, value, total, tone }: { label: string; value: number; total: number; tone: "success" | "warning" | "error" }) {
  const pct = total > 0 ? Math.round((value / total) * 100) : 0;
  const toneText = { success: "text-success", warning: "text-warning", error: "text-error" }[tone];
  return (
    <div>
      <div className="flex justify-between items-end mb-1">
        <span className="text-body-md font-medium text-on-surface">{label}</span>
        <span className={`text-label-sm font-mono ${toneText}`}>
          {value} / {total}
        </span>
      </div>
      <ProgressBar value={pct} tone={tone} />
    </div>
  );
}

function actorDotColor(actor: string): string {
  switch (actor) {
    case "system":
      return "bg-primary";
    case "admin":
      return "bg-tertiary";
    case "ai":
      return "bg-info";
    default:
      return "bg-success";
  }
}
