import { useState } from "react";
import { Link } from "react-router-dom";
import { useRecordSearch } from "@/hooks/useRecords";
import Icon from "@/components/ui/Icon";
import Input from "@/components/ui/Input";
import Select from "@/components/ui/Select";
import Badge, { type BadgeTone } from "@/components/ui/Badge";
import { EmptyRow, ErrorRow, LoadingRow, Table, TBody, Td, Th, THead, Tr } from "@/components/ui/Table";
import type { RecordSearchFilters, RecordSearchResult } from "@/types";

// Replicates desing/search_lavoro_esterno/code.html: phone search bar,
// advanced filters (source/status/date range), results table and pagination.

const STATUS_TONE: Record<RecordSearchResult["status"], BadgeTone> = {
  verified: "success",
  flagged: "warning",
  unverified: "neutral",
};

const STATUS_LABEL: Record<RecordSearchResult["status"], string> = {
  verified: "Verified",
  flagged: "Flagged",
  unverified: "Unverified",
};

const PAGE_SIZE = 25;

function formatDate(iso: string): string {
  return iso.slice(0, 10);
}

export default function SearchPage() {
  const [phone, setPhone] = useState("");
  const [source, setSource] = useState("");
  const [status, setStatus] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [page, setPage] = useState(1);

  const filters: RecordSearchFilters = {
    phone: phone || undefined,
    source: source || undefined,
    status: status || undefined,
    dateFrom: dateFrom || undefined,
    dateTo: dateTo || undefined,
    page,
    pageSize: PAGE_SIZE,
  };

  const search = useRecordSearch(filters);
  // The hook is gated (enabled: only once a filter is set) — mirror that here
  // so we can show a distinct "type something" state before any query has run.
  const hasFilters = Boolean(phone || source || status || dateFrom);

  function clearAll() {
    setPhone("");
    setSource("");
    setStatus("");
    setDateFrom("");
    setDateTo("");
    setPage(1);
  }

  const total = search.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="space-y-6">
      {/* Search Header & Input */}
      <section className="space-y-4">
        <div>
          <h2 className="text-headline-md text-on-surface">Global Entity Search</h2>
          <p className="text-body-md text-on-surface-variant mt-1">
            Search records across all synchronized sources by phone number, canonical ID, or keyword.
          </p>
        </div>
        <div className="max-w-3xl">
          <Input
            icon="search"
            placeholder="e.g. +39 345 678 9012"
            value={phone}
            onChange={(e) => {
              setPhone(e.target.value);
              setPage(1);
            }}
            className="py-4 text-body-lg rounded-xl"
          />
        </div>
      </section>

      {/* Advanced Filters */}
      <section className="bg-white border border-border rounded-lg p-4 shadow-[0_1px_2px_rgba(0,0,0,0.02)]">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-body-md font-semibold text-on-surface flex items-center gap-2">
            <Icon name="tune" size={18} className="text-primary" />
            Advanced Filters
          </h3>
          <button onClick={clearAll} className="text-label-sm text-primary hover:text-primary-container transition-colors">
            Clear all
          </button>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="space-y-2">
            <label className="text-label-sm text-on-surface-variant block">Source Origin</label>
            <Select
              className="w-full"
              value={source}
              onChange={(e) => {
                setSource(e.target.value);
                setPage(1);
              }}
            >
              <option value="">All Sources</option>
              <option value="web">Web Scrape</option>
              <option value="forum">Forum Dump</option>
              <option value="manual">Manual Entry</option>
            </Select>
          </div>
          <div className="space-y-2">
            <label className="text-label-sm text-on-surface-variant block">Verification Status</label>
            <Select
              className="w-full"
              value={status}
              onChange={(e) => {
                setStatus(e.target.value);
                setPage(1);
              }}
            >
              <option value="">Any Status</option>
              <option value="verified">Verified</option>
              <option value="flagged">Flagged</option>
              <option value="unverified">Unverified</option>
            </Select>
          </div>
          <div className="space-y-2">
            <label className="text-label-sm text-on-surface-variant block">Last Seen Date</label>
            <div className="flex items-center gap-2">
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => {
                  setDateFrom(e.target.value);
                  setPage(1);
                }}
                className="w-full rounded border border-outline-variant bg-surface text-body-md text-on-surface focus:ring-2 focus:ring-primary-container focus:border-primary-container py-2 px-3 outline-none transition-colors"
              />
              <span className="text-outline">-</span>
              <input
                type="date"
                value={dateTo}
                onChange={(e) => {
                  setDateTo(e.target.value);
                  setPage(1);
                }}
                className="w-full rounded border border-outline-variant bg-surface text-body-md text-on-surface focus:ring-2 focus:ring-primary-container focus:border-primary-container py-2 px-3 outline-none transition-colors"
              />
            </div>
          </div>
        </div>
      </section>

      {/* Results */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h3 className="text-headline-sm text-on-surface">Search Results</h3>
            {search.data && (
              <span className="bg-surface-container-high text-on-surface-variant text-label-sm px-2 py-0.5 rounded-full border border-border">
                {total.toLocaleString()} found
              </span>
            )}
          </div>
        </div>

        <div className="bg-white border border-border rounded-lg shadow-[0_1px_2px_rgba(0,0,0,0.02)] flex flex-col min-h-[300px]">
          <Table>
            <THead>
              <Tr className="hover:bg-transparent">
                <Th>Phone Number</Th>
                <Th>Canonical Title</Th>
                <Th className="text-right">Sources</Th>
                <Th className="text-right">Occurrences</Th>
                <Th>Timeline (First / Last)</Th>
                <Th>Status</Th>
                <Th className="text-center">Action</Th>
              </Tr>
            </THead>
            <TBody>
              {!hasFilters && (
                <EmptyRow colSpan={7} message="Enter a phone number or apply a filter to search records." />
              )}
              {hasFilters && search.isLoading && <LoadingRow colSpan={7} />}
              {hasFilters && search.isError && <ErrorRow colSpan={7} message="Failed to load search results." />}
              {hasFilters && search.data && search.data.results.length === 0 && (
                <EmptyRow colSpan={7} message="No records match these filters." />
              )}
              {hasFilters &&
                search.data?.results.map((record) => (
                  <Tr key={record.id}>
                    <Td>
                      <div className="flex items-center gap-2">
                        <Icon name="call" size={16} className="text-outline" />
                        <span className="font-mono text-mono-data font-medium text-on-surface tracking-tight">
                          {record.phone}
                        </span>
                      </div>
                    </Td>
                    <Td className="text-on-surface font-medium truncate max-w-[220px]" title={record.canonicalTitle}>
                      {record.canonicalTitle || <span className="text-outline italic">No title found</span>}
                    </Td>
                    <Td className="text-right font-mono text-on-surface-variant">{record.sourcesCount}</Td>
                    <Td className="text-right font-mono text-on-surface-variant">{record.occurrencesCount}</Td>
                    <Td>
                      <div className="flex flex-col text-[11px] leading-tight font-mono text-on-surface-variant">
                        <span>{formatDate(record.firstSeenAt)}</span>
                        <span className="text-on-surface font-medium">{formatDate(record.lastSeenAt)}</span>
                      </div>
                    </Td>
                    <Td>
                      <Badge tone={STATUS_TONE[record.status]}>{STATUS_LABEL[record.status]}</Badge>
                    </Td>
                    <Td className="text-center">
                      <Link
                        to={`/records/${record.id}`}
                        className="inline-flex p-1 rounded text-on-surface-variant hover:text-primary hover:bg-surface-container-high transition-colors opacity-0 group-hover:opacity-100 focus:opacity-100"
                      >
                        <Icon name="visibility" size={18} />
                      </Link>
                    </Td>
                  </Tr>
                ))}
            </TBody>
          </Table>

          {hasFilters && search.data && total > 0 && (
            <div className="border-t border-border px-4 py-3 flex items-center justify-between">
              <div className="text-label-sm text-on-surface-variant">
                Showing {(page - 1) * PAGE_SIZE + 1} to {Math.min(page * PAGE_SIZE, total)} of {total.toLocaleString()} results
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1}
                  className="p-1 rounded border border-border text-on-surface-variant disabled:opacity-40 disabled:cursor-not-allowed hover:bg-surface-container-lowest transition-colors"
                >
                  <Icon name="chevron_left" size={16} />
                </button>
                <span className="px-2 text-label-sm text-on-surface-variant">
                  Page {page} of {totalPages}
                </span>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages}
                  className="p-1 rounded border border-border text-on-surface-variant disabled:opacity-40 disabled:cursor-not-allowed hover:bg-surface-container-lowest transition-colors"
                >
                  <Icon name="chevron_right" size={16} />
                </button>
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
