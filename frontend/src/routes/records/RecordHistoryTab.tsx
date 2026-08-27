import { useParams } from "react-router-dom";
import { useRecordHistory } from "@/hooks/useRecords";
import Icon from "@/components/ui/Icon";
import type { ActivityActor } from "@/types";

// Replicates desing/record_detail_history/code.html: a vertical audit
// timeline, dot-and-line style borrowed from DashboardPage's "Recent
// Activity" panel. The actor->color mapping is intentionally duplicated
// here (rather than imported from DashboardPage, which doesn't export it)
// so this tab stays self-contained and doesn't couple to dashboard internals.

function actorDotColor(actor: ActivityActor): string {
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

function actorIcon(actor: ActivityActor): string {
  switch (actor) {
    case "system":
      return "dns";
    case "admin":
      return "admin_panel_settings";
    case "ai":
      return "smart_toy";
    default:
      return "download_for_offline";
  }
}

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export default function RecordHistoryTab() {
  const { id = "" } = useParams();
  const history = useRecordHistory(id);

  return (
    <div className="max-w-4xl mx-auto bg-white border border-border rounded-xl p-8 shadow-sm">
      <h3 className="text-headline-sm text-on-surface flex items-center gap-2 mb-8">
        <Icon name="history" className="text-primary" />
        Audit Trail
      </h3>

      {history.isLoading && <p className="text-body-md text-on-surface-variant">Loading…</p>}
      {history.isError && <p className="text-body-md text-error">Failed to load history.</p>}
      {history.data && history.data.length === 0 && (
        <p className="text-body-md text-on-surface-variant">No history events recorded for this record.</p>
      )}

      {history.data && history.data.length > 0 && (
        <div className="relative space-y-6">
          {history.data.map((event, i) => (
            <div key={event.id} className="relative pl-12">
              {i !== history.data!.length - 1 && (
                <div className="absolute left-5 top-10 bottom-[-24px] w-px bg-border" />
              )}
              <div className="absolute left-0 top-0 w-10 h-10 rounded-full bg-surface-container-low border border-border flex items-center justify-center z-10">
                <Icon name={actorIcon(event.actor)} size={20} className={actorDotColor(event.actor).replace("bg-", "text-")} />
              </div>
              <div className="bg-surface-container-lowest border border-border rounded-lg p-4">
                <div className="flex justify-between items-start mb-2 gap-4">
                  <div className="flex items-center gap-2">
                    <span className="text-body-md text-on-surface font-semibold">{event.action}</span>
                    <span className="px-2 py-0.5 rounded-full bg-surface-container-high text-on-surface-variant text-[10px] font-mono font-semibold uppercase tracking-wider">
                      {event.actorLabel}
                    </span>
                  </div>
                  <span className="text-mono-data font-mono text-on-surface-variant text-sm whitespace-nowrap">
                    {formatDateTime(event.occurredAt)}
                  </span>
                </div>
                <p className="text-body-md text-on-surface-variant">{event.detail}</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
