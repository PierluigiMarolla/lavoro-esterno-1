import { useParams } from "react-router-dom";
import { useState } from "react";
import { useRecordMedia, useReprocessMedia, useReviewMedia } from "@/hooks/useRecords";
import { useAuth } from "@/context/AuthContext";
import Icon from "@/components/ui/Icon";
import ErrorState from "@/components/ui/ErrorState";
import type { RecordMedia } from "@/types";
import { formatDate } from "@/lib/format";

// Replicates desing/record_detail_media/code.html: a media gallery where
// items flagged "explicit" are blurred behind a warning overlay until the
// analyst explicitly opts in per item.

export default function RecordMediaTab() {
  const { id = "" } = useParams();
  const media = useRecordMedia(id);
  const review = useReviewMedia(id);
  const reprocess = useReprocessMedia(id);
  const { user } = useAuth();
  const canReview = user?.role === "admin" || user?.role === "operator";

  // Per-item, component-local reveal state (not persisted, not global). The
  // API already returns the media regardless of sensitivity — the blur is a
  // client-side UX affordance to avoid surprising an analyst with explicit
  // content on load, not an access-control boundary. Resetting on navigation
  // away is the desired behavior, so plain useState is sufficient.
  const [revealed, setRevealed] = useState<Set<string>>(new Set());

  function reveal(itemId: string) {
    setRevealed((prev) => new Set(prev).add(itemId));
  }

  if (media.isLoading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-64 bg-surface-container-low rounded-lg animate-pulse" />
        ))}
      </div>
    );
  }
  if (media.isError) {
    return <ErrorState error={media.error} onRetry={() => media.refetch()} />;
  }
  if (!media.data || media.data.length === 0) {
    return <p className="text-body-md text-on-surface-variant">Nessun media associato a questo record.</p>;
  }

  return (
    <div>
      <h3 className="text-headline-sm text-on-surface mb-4">Media Assets ({media.data.length})</h3>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {media.data.map((item) => (
          <MediaCard
            key={item.id}
            item={item}
            isRevealed={revealed.has(item.id)}
            onReveal={() => reveal(item.id)}
            canReview={canReview}
            onReview={(classification) => {
              const notes = window.prompt("Note di revisione (obbligatorie):");
              if (notes?.trim()) review.mutate({ mediaId: item.id, classification, notes: notes.trim() });
            }}
            onReprocess={() => reprocess.mutate(item.id)}
          />
        ))}
      </div>
    </div>
  );
}

function MediaCard({
  item,
  isRevealed,
  onReveal,
  canReview,
  onReview,
  onReprocess,
}: {
  item: RecordMedia;
  isRevealed: boolean;
  onReveal: () => void;
  canReview: boolean;
  onReview: (classification: "safe" | "explicit") => void;
  onReprocess: () => void;
}) {
  const isBlurred = item.sensitivity === "explicit" && !isRevealed;

  return (
    <div className="bg-surface-container-lowest border border-border rounded-lg overflow-hidden flex flex-col">
      <div className="relative h-48 bg-surface-container-low w-full overflow-hidden">
        <img
          src={item.thumbnailUrl}
          alt=""
          className={isBlurred ? "w-full h-full object-cover blur-xl scale-110" : "w-full h-full object-cover"}
        />
        {isBlurred && (
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-surface/40 backdrop-blur-sm p-4 text-center">
            <Icon name="visibility_off" size={32} className="text-error mb-2" />
            <span className="text-body-md font-semibold text-on-surface mb-1">Rilevato contenuto esplicito</span>
            <button
              type="button"
              onClick={onReveal}
              className="mt-2 px-3 py-1 bg-surface-container-lowest border border-border rounded text-label-sm text-on-surface hover:bg-surface-container-low transition-colors"
            >
              Mostra media
            </button>
          </div>
        )}
        <div className="absolute top-2 right-2 bg-surface-container-lowest/90 backdrop-blur-sm rounded-full px-2 py-1 flex items-center gap-1 border border-border/50">
          <Icon name={item.type === "video" ? "movie" : "image"} size={16} className="text-info" />
          <span className="text-label-sm text-on-surface">{item.type === "video" ? "VID" : "IMG"}</span>
        </div>
      </div>
      <div className="p-4 flex-1 flex flex-col justify-between">
        <div>
          <div className="flex justify-between items-start mb-2">
            <span
              className={
                item.sensitivity === "explicit"
                  ? "shrink-0 inline-flex items-center px-1.5 py-0.5 rounded text-label-sm bg-error/10 text-error border border-error/20"
                  : "shrink-0 inline-flex items-center px-1.5 py-0.5 rounded text-label-sm bg-success/10 text-success border border-success/20"
              }
            >
              {item.sensitivity === "explicit" ? "Esplicito" : "Sicuro"}
            </span>
            {item.reviewStatus === "required" && (
              <span className="shrink-0 inline-flex items-center px-1.5 py-0.5 rounded text-label-sm bg-warning/10 text-warning border border-warning/20">
                Da revisionare
              </span>
            )}
          </div>
          <div className="flex items-center gap-2 text-label-sm text-on-surface-variant mb-4">
            <Icon name="language" size={14} />
            <span>Fonte: {item.sourceName}</span>
            <span className="text-border">&bull;</span>
            <span>{formatDate(item.addedAt)}</span>
          </div>
        </div>
        <div className="flex justify-between border-t border-border pt-3 mt-auto">
          <a
            href={item.url}
            target="_blank"
            rel="noreferrer"
            className="text-label-sm text-on-surface-variant hover:text-primary transition-colors flex items-center gap-1"
          >
            <Icon name="open_in_new" size={16} />
            Visualizza
          </a>
          {canReview && item.reviewStatus === "required" && (
            <div className="flex gap-2">
              <button type="button" onClick={() => onReview("safe")} className="text-label-sm text-success">Segna come sicuro</button>
              <button type="button" onClick={() => onReview("explicit")} className="text-label-sm text-error">Segna come esplicito</button>
            </div>
          )}
          {canReview && item.processingStatus === "failed" && (
            <button type="button" onClick={onReprocess} className="text-label-sm text-primary">Rielabora</button>
          )}
        </div>
      </div>
    </div>
  );
}
