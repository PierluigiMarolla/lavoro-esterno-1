import type { ReactNode } from "react";
import { createPortal } from "react-dom";
import Icon from "./Icon";

// Simple centered modal (no external deps). Used for export confirmations,
// AI summary regeneration confirmation, etc.
export default function Dialog({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
}) {
  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-on-surface/40" onClick={onClose} aria-hidden="true" />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="relative w-full max-w-md bg-surface-container-lowest border border-border rounded-lg shadow-[0_4px_24px_rgba(0,0,0,0.15)] overflow-hidden"
      >
        <div className="px-5 py-4 border-b border-border flex items-center justify-between bg-surface-container-lowest">
          <h3 className="text-headline-sm font-semibold text-on-surface">{title}</h3>
          <button
            onClick={onClose}
            className="p-1 rounded-full text-on-surface-variant hover:text-primary hover:bg-surface-container-low"
            aria-label="Close"
          >
            <Icon name="close" size={18} />
          </button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>,
    document.body,
  );
}
