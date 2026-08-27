import { useParams } from "react-router-dom";
import { useRecordOccurrences } from "@/hooks/useRecords";
import Icon from "@/components/ui/Icon";
import ProgressBar from "@/components/ui/ProgressBar";
import { EmptyRow, ErrorRow, LoadingRow, Table, TBody, Td, Th, THead, Tr } from "@/components/ui/Table";

// Replicates desing/record_detail_occurrences/code.html: every scraped
// occurrence that was merged into this record, with the canonical one
// (the source picked as "truth" for the merged fields) tinted primary/10
// and tagged "Canonical" — a positive highlight, unlike the error-tinted
// rows used elsewhere in the app for offline sources.

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export default function RecordOccurrencesTab() {
  const { id = "" } = useParams();
  const occurrences = useRecordOccurrences(id);

  return (
    <div className="bg-white border border-border rounded-lg shadow-sm flex flex-col">
      <div className="p-4 border-b border-border flex justify-between items-center bg-surface-container-lowest rounded-t-lg">
        <span className="text-label-sm text-on-surface font-semibold">
          {occurrences.data ? `${occurrences.data.length} Occurrences Found` : "Occurrences"}
        </span>
      </div>
      <Table>
        <THead>
          <Tr className="hover:bg-transparent">
            <Th>Source</Th>
            <Th>Title</Th>
            <Th>Source URL</Th>
            <Th>Scraped At</Th>
            <Th>Match Confidence</Th>
          </Tr>
        </THead>
        <TBody>
          {occurrences.isLoading && <LoadingRow colSpan={5} />}
          {occurrences.isError && <ErrorRow colSpan={5} message="Failed to load occurrences." />}
          {occurrences.data && occurrences.data.length === 0 && (
            <EmptyRow colSpan={5} message="No occurrences found for this record." />
          )}
          {occurrences.data?.map((occ) => (
            <Tr key={occ.id} className={occ.isCanonical ? "bg-primary/5" : undefined}>
              <Td>
                <div className="flex items-center gap-2">
                  <div className="w-6 h-6 rounded bg-surface-container flex items-center justify-center text-primary shrink-0">
                    <Icon name="public" size={14} />
                  </div>
                  <div>
                    <div className="font-medium text-on-surface">{occ.sourceName}</div>
                    <div className="text-label-sm text-on-surface-variant font-mono">{occ.sourceCode}</div>
                  </div>
                </div>
              </Td>
              <Td>
                <div className="flex items-center gap-2">
                  <span className="text-on-surface truncate max-w-[220px] inline-block">{occ.title}</span>
                  {occ.isCanonical && (
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-bold tracking-wider uppercase bg-primary-container text-on-primary border border-primary/20">
                      Canonical
                    </span>
                  )}
                </div>
              </Td>
              <Td>
                <a
                  href={occ.url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-mono-data font-mono text-primary hover:underline truncate max-w-[200px] inline-block"
                >
                  {occ.url}
                </a>
              </Td>
              <Td className="text-on-surface-variant">
                <span className="font-mono text-sm">{formatDateTime(occ.scrapedAt)}</span>
              </Td>
              <Td>
                <div className="flex items-center gap-2">
                  <ProgressBar
                    value={occ.matchConfidence}
                    tone={occ.matchConfidence >= 80 ? "success" : occ.matchConfidence >= 60 ? "warning" : "error"}
                    className="w-16"
                  />
                  <span className="text-label-sm text-on-surface">{occ.matchConfidence}%</span>
                </div>
              </Td>
            </Tr>
          ))}
        </TBody>
      </Table>
    </div>
  );
}
