import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { useRecordAiSummary, useRecordAiSummaryVersions, useRegenerateAiSummary } from "@/hooks/useRecords";
import Icon from "@/components/ui/Icon";
import Button from "@/components/ui/Button";
import ErrorState from "@/components/ui/ErrorState";
import { cn } from "@/lib/cn";
import type { RecordAiSummary, RecordAiSummaryVersion } from "@/types";

// Replicates desing/record_detail_ai_summary/code.html. The whole tab uses a
// tinted surface + explicit "AI-generated" framing per DESIGN.md, so this
// content is never mistaken for verified scraped data.

function formatDateTime(iso: string | null): string {
  if (!iso) return "Not yet generated";
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export default function RecordAiSummaryTab() {
  const { id = "" } = useParams();
  const summary = useRecordAiSummary(id);
  const versions = useRecordAiSummaryVersions(id);
  const regenerate = useRegenerateAiSummary(id);

  // null (the sentinel default) means "show the latest summary" — the
  // useRecordAiSummary query, not a versions list entry — so that a
  // Regenerate always lands back on the newest version even if the user had
  // a different one selected. Any other value pins the picker to that
  // version's own number.
  const [selectedVersion, setSelectedVersion] = useState<number | null>(null);

  // A regenerate call bumps the latest version — make sure the picker
  // doesn't stay pinned to what's now a stale, non-latest version.
  useEffect(() => {
    if (regenerate.isSuccess) setSelectedVersion(null);
  }, [regenerate.isSuccess, regenerate.data]);

  if (summary.isLoading) {
    return <div className="h-64 animate-pulse bg-surface-container-low rounded-lg" />;
  }
  if (summary.isError) {
    return <ErrorState error={summary.error} onRetry={() => summary.refetch()} />;
  }
  if (!summary.data) {
    return (
      <div className="space-y-4">
        <p className="text-body-md text-on-surface-variant">No AI summary available for this record.</p>
        <Button onClick={() => regenerate.mutate()} disabled={regenerate.isPending}>
          <Icon name="auto_awesome" size={18} className={regenerate.isPending ? "animate-spin" : undefined} />
          {regenerate.isPending ? "Generating asynchronously..." : "Generate Summary"}
        </Button>
        {regenerate.isError && <ErrorState error={regenerate.error} />}
      </div>
    );
  }

  const latestVersionNumber = versions.data && versions.data.length > 0 ? versions.data[0].version : null;
  const selected: RecordAiSummary | RecordAiSummaryVersion | undefined =
    selectedVersion === null ? summary.data : versions.data?.find((v) => v.version === selectedVersion);
  const data = selected ?? summary.data;
  const isViewingLatest = selectedVersion === null || selectedVersion === latestVersionNumber;

  return (
    <div className="bg-surface-container-low/40 -m-margin-page p-margin-page">
      <div className="flex justify-between items-end mb-6">
        <div>
          <h2 className="text-headline-lg text-on-surface mb-2 flex items-center gap-2">
            <Icon name="auto_awesome" className="text-info" />
            AI Synthesis
          </h2>
          <div className="flex items-center gap-2 text-body-md text-on-surface-variant">
            <Icon name="schedule" size={16} />
            <span>Generated: {formatDateTime(data.generatedAt)}</span>
          </div>
          <p className="text-label-sm text-on-surface-variant mt-1">
            Provider: {data.provider} · Model: <span className="font-mono">{data.model}</span>
          </p>
        </div>
        <Button onClick={() => regenerate.mutate()} disabled={regenerate.isPending}>
          <Icon name="autorenew" size={18} className={regenerate.isPending ? "animate-spin" : undefined} />
          {regenerate.isPending ? "Regenerating..." : "Regenerate Summary"}
        </Button>
      </div>
      {regenerate.isError && <ErrorState error={regenerate.error} className="mb-4" />}

      <div className="grid grid-cols-12 gap-gutter">
        <div className="col-span-12 lg:col-span-8 flex flex-col gap-gutter">
          {!isViewingLatest && (
            <div className="flex items-center gap-2 bg-info/10 border border-info/30 text-info rounded-lg px-4 py-2 text-body-md">
              <Icon name="history" size={18} />
              <span>You&apos;re viewing an older version of this summary. Regenerating will create a new latest version.</span>
            </div>
          )}

          <section className="bg-surface-container-lowest border border-border rounded-lg p-6 shadow-sm">
            <div className="flex items-center gap-2 mb-4 border-b border-border pb-3">
              <Icon name="psychology" className="text-primary" size={24} />
              <h3 className="text-headline-sm text-on-surface">Executive Synthesis</h3>
            </div>
            <p className="text-body-md text-on-surface-variant leading-relaxed whitespace-pre-line">
              {data.executiveSynthesis}
            </p>
          </section>

          <section className="bg-[#fffbeb] border border-warning rounded-lg p-6 shadow-sm relative overflow-hidden">
            <div className="absolute top-0 left-0 w-1 h-full bg-warning" />
            <div className="flex items-center gap-2 mb-4 border-b border-warning/30 pb-3">
              <Icon name="warning" className="text-warning" size={24} />
              <h3 className="text-headline-sm text-[#92400e]">Unverified Claims &amp; Anomalies</h3>
            </div>
            {data.unverifiedClaims.length === 0 ? (
              <p className="text-body-md text-[#92400e]">No unverified claims flagged.</p>
            ) : (
              <ul className="space-y-3">
                {data.unverifiedClaims.map((claim, i) => (
                  <li key={i} className="flex gap-3 items-start">
                    <Icon name="error_outline" size={18} className="text-warning mt-0.5" />
                    <p className="text-body-md text-[#92400e]">{claim}</p>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>

        <div className="col-span-12 lg:col-span-4 flex flex-col gap-gutter">
          <VersionPicker
            versions={versions.data}
            isLoading={versions.isLoading}
            error={versions.error}
            onRetry={() => versions.refetch()}
            latestVersionNumber={latestVersionNumber}
            selectedVersion={selectedVersion}
            onSelect={setSelectedVersion}
          />

          <section className="bg-surface-container-lowest border border-border rounded-lg p-6 shadow-sm">
            <div className="flex items-center gap-2 mb-4 border-b border-border pb-3">
              <Icon name="forum" className="text-secondary" size={24} />
              <h3 className="text-headline-sm text-on-surface">Forum Chatter</h3>
            </div>
            {data.forumChatter.length === 0 ? (
              <p className="text-body-md text-on-surface-variant">No forum chatter captured.</p>
            ) : (
              <div className="space-y-4">
                {data.forumChatter.map((entry, i) => (
                  <div key={i} className="border-l-2 border-border pl-3">
                    <p className="text-body-md text-on-surface text-sm italic">&quot;{entry}&quot;</p>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="bg-surface-container-lowest border border-border rounded-lg p-6 shadow-sm">
            <div className="flex items-center gap-2 mb-4 border-b border-border pb-3">
              <Icon name="dataset" className="text-secondary" size={24} />
              <h3 className="text-headline-sm text-on-surface">Sources Used</h3>
            </div>
            {data.sourcesUsed.length === 0 ? (
              <p className="text-body-md text-on-surface-variant">No sources recorded.</p>
            ) : (
              <ul className="space-y-2">
                {data.sourcesUsed.map((source) => (
                  <li key={source.url} className="flex items-center gap-2 text-body-md text-on-surface">
                    <Icon name="link" size={16} className="text-on-surface-variant" />
                    <a
                      href={source.url}
                      target="_blank"
                      rel="noreferrer"
                      className="hover:text-primary underline decoration-border underline-offset-2"
                    >
                      {source.name}
                    </a>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}

function VersionPicker({
  versions,
  isLoading,
  error,
  onRetry,
  latestVersionNumber,
  selectedVersion,
  onSelect,
}: {
  versions: RecordAiSummaryVersion[] | undefined;
  isLoading: boolean;
  error: unknown;
  onRetry: () => void;
  latestVersionNumber: number | null;
  selectedVersion: number | null;
  onSelect: (version: number | null) => void;
}) {
  return (
    <section className="bg-surface-container-lowest border border-border rounded-lg p-6 shadow-sm">
      <div className="flex items-center gap-2 mb-4 border-b border-border pb-3">
        <Icon name="history" className="text-secondary" size={24} />
        <h3 className="text-headline-sm text-on-surface">Version History</h3>
      </div>
      {isLoading && <p className="text-body-md text-on-surface-variant">Loading versions…</p>}
      {error !== undefined && error !== null && <ErrorState error={error} onRetry={onRetry} className="py-4" />}
      {versions && versions.length === 0 && (
        <p className="text-body-md text-on-surface-variant">No prior versions recorded.</p>
      )}
      {versions && versions.length > 0 && (
        <ul className="space-y-1.5 max-h-72 overflow-y-auto">
          {versions.map((version) => {
            const isLatest = version.version === latestVersionNumber;
            const isSelected = isLatest ? selectedVersion === null : selectedVersion === version.version;
            return (
              <li key={version.version}>
                <button
                  type="button"
                  onClick={() => onSelect(isLatest ? null : version.version)}
                  className={cn(
                    "w-full flex items-center justify-between gap-2 px-3 py-2 rounded text-left text-body-md transition-colors",
                    isSelected
                      ? "bg-primary/10 text-primary border border-primary/30"
                      : "text-on-surface-variant hover:bg-surface-container-low border border-transparent",
                  )}
                >
                  <span>
                    Version {version.version} — {formatDateTime(version.generatedAt)}
                  </span>
                  {isLatest && (
                    <span className="shrink-0 px-1.5 py-0.5 rounded text-[10px] font-bold tracking-wider uppercase bg-primary-container text-on-primary border border-primary/20">
                      Current
                    </span>
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
