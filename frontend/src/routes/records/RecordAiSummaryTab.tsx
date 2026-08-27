import { useParams } from "react-router-dom";
import { useRecordAiSummary, useRegenerateAiSummary } from "@/hooks/useRecords";
import Icon from "@/components/ui/Icon";
import Button from "@/components/ui/Button";

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
  const regenerate = useRegenerateAiSummary(id);

  if (summary.isLoading) {
    return <div className="h-64 animate-pulse bg-surface-container-low rounded-lg" />;
  }
  if (summary.isError) {
    return <p className="text-body-md text-error">Failed to load AI summary.</p>;
  }
  if (!summary.data) {
    return <p className="text-body-md text-on-surface-variant">No AI summary available for this record.</p>;
  }

  const data = summary.data;

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
        </div>
        <Button onClick={() => regenerate.mutate()} disabled={regenerate.isPending}>
          <Icon name="autorenew" size={18} className={regenerate.isPending ? "animate-spin" : undefined} />
          {regenerate.isPending ? "Regenerating..." : "Regenerate Summary"}
        </Button>
      </div>

      <div className="grid grid-cols-12 gap-gutter">
        <div className="col-span-12 lg:col-span-8 flex flex-col gap-gutter">
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
