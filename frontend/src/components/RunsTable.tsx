/**
 * Dashboard — Runs Table / Card List
 *
 * Dual-view dashboard: Centered card list ↔ Table list.
 * Card view: single-column, centered, dynamic page size via ResizeObserver.
 * Table view: content-sized, no stretched empty box.
 */

import { useState, useEffect, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Loader2,
  RefreshCw,
  Trash2,
  CheckCircle,
  Clock,
  AlertCircle,
  ArrowUp,
  ArrowDown,
  Search,
  X,
  FileSearch,
  ChevronLeft,
  ChevronRight,
  LayoutGrid,
  List,
  Users,
  MessageSquare,
  FileText,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { listRuns, deleteRun } from '@/api/client';
import type { RunListItem } from '@/types/api';
import { formatDate } from '@/lib/utils';

import type { StatusFilter } from '@/components/Sidebar';

interface RunsTableProps {
  onSelectRun: (runId: string) => void;
  refreshTrigger?: number;
  statusFilter: StatusFilter;
  onCountsChange: (counts: Record<StatusFilter, number>) => void;
}

type SortDir = 'asc' | 'desc';
type ViewMode = 'cards' | 'list';

const STORAGE_KEY      = 'dashboard-view';
const PAGE_SIZE_LIST   = 10;
const PAGE_SIZE_CARDS  = 9;    // 3 rows × 3 cols

// ─── Animation variants ──────────────────────────────────────────────────────

const rowVariants = {
  hidden: { opacity: 0, y: 3 },
  visible: (i: number) => ({
    opacity: 1, y: 0,
    transition: { delay: i * 0.02, duration: 0.18, ease: 'easeOut' },
  }),
};

const cardVariants = {
  hidden: { opacity: 0, x: -6 },
  visible: (i: number) => ({
    opacity: 1, x: 0,
    transition: { delay: i * 0.03, duration: 0.2, ease: 'easeOut' },
  }),
};

// ─── Pagination helper ───────────────────────────────────────────────────────

function getPageNumbers(current: number, total: number): (number | '...')[] {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  if (current <= 3) return [1, 2, 3, 4, '...', total];
  if (current >= total - 2) return [1, '...', total - 3, total - 2, total - 1, total];
  return [1, '...', current - 1, current, current + 1, '...', total];
}

// ─── Status helpers ──────────────────────────────────────────────────────────

function StatusDot({ status }: { status: string }) {
  const cfg: Record<string, { dot: string; label: string; text: string }> = {
    completed: { dot: 'bg-emerald-500',              label: 'Completed',   text: 'text-emerald-700 dark:text-emerald-400' },
    running:   { dot: 'bg-blue-500 animate-pulse',   label: 'Running',     text: 'text-blue-700 dark:text-blue-400' },
    queued:    { dot: 'bg-amber-400',                label: 'Queued',      text: 'text-amber-700 dark:text-amber-400' },
    failed:    { dot: 'bg-red-500',                  label: 'Failed',      text: 'text-red-600 dark:text-red-400' },
  };
  const c = cfg[status] ?? { dot: 'bg-muted-foreground/40', label: status, text: 'text-muted-foreground' };
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${c.text}`}>
      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${c.dot}`} />
      {c.label}
    </span>
  );
}

function getStatusBadge(status: string) {
  switch (status) {
    case 'completed': return <Badge variant="success"><CheckCircle className="h-3 w-3 mr-1" />Completed</Badge>;
    case 'running':   return <Badge variant="default" className="animate-pulse-soft"><Loader2 className="h-3 w-3 mr-1 animate-spin" />Running</Badge>;
    case 'queued':    return <Badge variant="secondary"><Clock className="h-3 w-3 mr-1" />Queued</Badge>;
    case 'failed':    return <Badge variant="error"><AlertCircle className="h-3 w-3 mr-1" />Failed</Badge>;
    default:          return <Badge variant="outline">{status}</Badge>;
  }
}

function statusBorderClass(status: string): string {
  switch (status) {
    case 'completed': return 'border-l-emerald-500';
    case 'running':
    case 'queued':    return 'border-l-blue-400';
    case 'failed':    return 'border-l-red-500';
    default:          return 'border-l-border';
  }
}

// ─── Skeletons ───────────────────────────────────────────────────────────────

function SkeletonTableRows({ count }: { count: number }) {
  return (
    <>
      {Array.from({ length: count }).map((_, i) => (
        <tr key={i} className="border-b border-border/50">
          <td className="py-3 pr-4 w-8"><div className="h-3 skeleton-shimmer rounded w-4" /></td>
          <td className="py-3 pr-6"><div className="h-4 skeleton-shimmer rounded w-64" /></td>
          <td className="py-3 pr-6"><div className="h-3 skeleton-shimmer rounded w-20" /></td>
          <td className="py-3 pr-6"><div className="h-3 skeleton-shimmer rounded w-32" /></td>
          <td className="py-3 pr-4 text-right"><div className="h-4 skeleton-shimmer rounded w-6 ml-auto" /></td>
          <td className="py-3 pr-6 text-right"><div className="h-4 skeleton-shimmer rounded w-6 ml-auto" /></td>
          <td className="py-3 w-8" />
        </tr>
      ))}
    </>
  );
}

function SkeletonCardRow() {
  return (
    <div className="rounded-xl border border-border/40 bg-card p-4 space-y-3">
      <div className="flex items-start justify-between gap-2">
        <div className="h-4 skeleton-shimmer rounded w-3/4" />
        <div className="h-5 skeleton-shimmer rounded-full w-20 shrink-0" />
      </div>
      <div className="flex items-center gap-3">
        <div className="h-3 skeleton-shimmer rounded w-14" />
        <div className="h-3 skeleton-shimmer rounded w-14" />
      </div>
      <div className="h-3 skeleton-shimmer rounded w-28" />
    </div>
  );
}

// ─── RunCard (centered, horizontal, single-column) ───────────────────────────

interface RunCardProps {
  run: RunListItem;
  index: number;
  deleting: string | null;
  onSelect: (e: React.MouseEvent, run: RunListItem) => void;
  onDelete: (runId: string) => void;
}

function RunCard({ run, index, deleting, onSelect, onDelete }: RunCardProps) {
  return (
    <motion.div
      custom={index}
      initial="hidden"
      animate="visible"
      variants={cardVariants}
      onClick={(e) => onSelect(e, run)}
      className={`
        flex flex-col
        group rounded-xl border border-border/60 bg-card p-4
        border-l-[3px] ${statusBorderClass(run.status)}
        cursor-pointer transition-all duration-200
        hover:shadow-md hover:-translate-y-px hover:border-border
      `}
    >
      {/* Top row: filename + status */}
      <div className="flex items-start justify-between gap-2 mb-3">
        <div className="flex items-start gap-2 min-w-0">
          <FileText className="h-3.5 w-3.5 text-muted-foreground/50 shrink-0 mt-0.5" />
          <p className="text-sm font-medium text-foreground leading-snug line-clamp-2">
            {run.display_name || run.filename}
          </p>
        </div>
        <div className="shrink-0 mt-0.5">{getStatusBadge(run.status)}</div>
      </div>

      {/* Stats row */}
      <div className="flex items-center gap-4 text-xs text-muted-foreground mb-3">
        <span className="flex items-center gap-1">
          <Users className="h-3 w-3" />
          <span className="font-medium text-foreground tabular-nums">{run.speaker_count ?? '—'}</span>
          <span className="text-muted-foreground/60">spk</span>
        </span>
        <span className="flex items-center gap-1">
          <MessageSquare className="h-3 w-3" />
          <span className="font-medium text-foreground tabular-nums">{run.qa_count ?? '—'}</span>
          <span className="text-muted-foreground/60">Q&As</span>
        </span>
      </div>

      {/* Bottom row: date + delete */}
      <div className="flex items-center justify-between mt-auto pt-3">
        <span className="text-xs text-muted-foreground tabular-nums">{formatDate(run.started_at)}</span>
        <button
          onClick={(e) => { e.stopPropagation(); onDelete(run.run_id); }}
          disabled={deleting === run.run_id}
          className="h-6 w-6 inline-flex items-center justify-center rounded text-muted-foreground/30 hover:text-destructive hover:bg-destructive/10 opacity-0 group-hover:opacity-100 transition-all disabled:opacity-50"
        >
          {deleting === run.run_id
            ? <Loader2 className="h-3 w-3 animate-spin" />
            : <Trash2 className="h-3 w-3" />
          }
        </button>
      </div>

      {run.error_message && (
        <p className="text-xs text-destructive mt-2 truncate" title={run.error_message}>
          {run.error_message}
        </p>
      )}
    </motion.div>
  );
}

// ─── Main component ──────────────────────────────────────────────────────────

export function RunsTable({ onSelectRun, refreshTrigger, statusFilter, onCountsChange }: RunsTableProps) {
  const [runs, setRuns]               = useState<RunListItem[]>([]);
  const [loading, setLoading]         = useState(true);
  const [deleting, setDeleting]       = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [sortDir, setSortDir]         = useState<SortDir>('desc');
  const [searchQuery, setSearchQuery] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [viewMode, setViewMode]       = useState<ViewMode>(() =>
    (localStorage.getItem(STORAGE_KEY) as ViewMode) ?? 'list'
  );


  function switchView(mode: ViewMode) {
    setViewMode(mode);
    localStorage.setItem(STORAGE_KEY, mode);
    setCurrentPage(1);
  }

  useEffect(() => { loadRuns(); }, [refreshTrigger]);

  useEffect(() => {
    const hasRunning = runs.some(r => r.status === 'running' || r.status === 'queued');
    if (!hasRunning) return;
    const interval = setInterval(loadRuns, 3000);
    return () => clearInterval(interval);
  }, [runs]);

  useEffect(() => { setCurrentPage(1); }, [searchQuery, statusFilter]);

  const statusCounts = useMemo(() => ({
    all:       runs.length,
    completed: runs.filter(r => r.status === 'completed').length,
    running:   runs.filter(r => r.status === 'running' || r.status === 'queued').length,
    failed:    runs.filter(r => r.status === 'failed').length,
  }), [runs]);

  useEffect(() => { onCountsChange(statusCounts); }, [statusCounts, onCountsChange]);

  const filteredRuns = useMemo(() => {
    let result = [...runs];
    if (statusFilter === 'completed') result = result.filter(r => r.status === 'completed');
    else if (statusFilter === 'running') result = result.filter(r => r.status === 'running' || r.status === 'queued');
    else if (statusFilter === 'failed') result = result.filter(r => r.status === 'failed');
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      result = result.filter(r => r.filename.toLowerCase().includes(q));
    }
    result.sort((a, b) => {
      const da = new Date(a.started_at).getTime();
      const db = new Date(b.started_at).getTime();
      return sortDir === 'desc' ? db - da : da - db;
    });
    return result;
  }, [runs, statusFilter, searchQuery, sortDir]);

  const effectivePageSize = viewMode === 'cards' ? PAGE_SIZE_CARDS : PAGE_SIZE_LIST;
  const totalPages    = Math.max(1, Math.ceil(filteredRuns.length / effectivePageSize));
  const safePage      = Math.min(currentPage, totalPages);
  const startIndex    = (safePage - 1) * effectivePageSize;
  const paginatedRuns = filteredRuns.slice(startIndex, startIndex + effectivePageSize);
  const showingFrom   = filteredRuns.length > 0 ? startIndex + 1 : 0;
  const showingTo     = Math.min(startIndex + effectivePageSize, filteredRuns.length);

  async function loadRuns() {
    try {
      const response = await listRuns();
      setRuns(response.runs);
    } catch (err) {
      console.error('Failed to load runs:', err);
    } finally {
      setLoading(false);
    }
  }

  async function executeDelete(runId: string) {
    setDeleting(runId);
    try {
      await deleteRun(runId);
      setRuns(prev => prev.filter(r => r.run_id !== runId));
    } catch (err) {
      console.error('Failed to delete:', err);
    } finally {
      setDeleting(null);
    }
  }

  function handleRowClick(e: React.MouseEvent, run: RunListItem) {
    if ((e.target as HTMLElement).closest('button')) return;
    if (run.status === 'queued') return;
    onSelectRun(run.run_id);
  }

  // ── Toolbar ────────────────────────────────────────────────────────────────

  const toolbar = (
    <div className="flex items-center justify-between gap-4 shrink-0 mb-5 flex-wrap">
      {/* Left: title + count */}
      <div className="flex items-baseline gap-1.5">
        <h1 className="text-lg font-semibold tracking-tight text-foreground">Analysis Runs</h1>
        <span className="text-xs text-muted-foreground tabular-nums">({filteredRuns.length})</span>
      </div>

      {/* Right: search + view toggle + refresh */}
      <div className="flex items-center gap-2">
        <div className="relative w-48">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
          <Input
            placeholder="Search…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-8 pr-7 h-8 text-sm bg-muted/40 border-border/60"
            aria-label="Search runs"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>

        <div className="flex items-center border border-border rounded-md overflow-hidden">
          {(['cards', 'list'] as ViewMode[]).map((mode, i) => (
            <button
              key={mode}
              onClick={() => switchView(mode)}
              title={mode === 'cards' ? 'Card view' : 'List view'}
              className={`
                flex items-center justify-center h-8 w-8 transition-colors
                ${i > 0 ? 'border-l border-border' : ''}
                ${viewMode === mode
                  ? 'bg-foreground text-background'
                  : 'bg-transparent text-muted-foreground hover:bg-muted hover:text-foreground'
                }
              `}
            >
              {mode === 'cards'
                ? <LayoutGrid className="h-3.5 w-3.5" />
                : <List className="h-3.5 w-3.5" />
              }
            </button>
          ))}
        </div>

        <Button
          variant="ghost"
          size="sm"
          onClick={loadRuns}
          className="h-8 px-2.5 text-xs text-muted-foreground hover:text-foreground gap-1.5"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Refresh
        </Button>
      </div>
    </div>
  );

  // ── Pagination ─────────────────────────────────────────────────────────────

  const pagination = totalPages <= 1 && filteredRuns.length <= effectivePageSize ? null : (
    <div className="flex items-center justify-between shrink-0 pt-4 border-t border-border/50">
      <p className="text-xs text-muted-foreground">
        Showing <span className="font-medium text-foreground tabular-nums">{showingFrom}–{showingTo}</span> of{' '}
        <span className="font-medium text-foreground tabular-nums">{filteredRuns.length}</span>
      </p>

      <div className="flex items-center gap-1">
        <Button
          variant="outline"
          size="sm"
          onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
          disabled={safePage <= 1}
          className="h-7 w-7 p-0 border-border/60"
        >
          <ChevronLeft className="h-3.5 w-3.5" />
        </Button>

        {getPageNumbers(safePage, totalPages).map((page, i) =>
          page === '...' ? (
            <span key={`e${i}`} className="w-7 text-center text-xs text-muted-foreground">…</span>
          ) : (
            <Button
              key={page}
              variant={page === safePage ? 'default' : 'ghost'}
              size="sm"
              onClick={() => setCurrentPage(page)}
              className={`h-7 w-7 p-0 text-xs ${page === safePage ? '' : 'text-muted-foreground hover:text-foreground'}`}
            >
              {page}
            </Button>
          )
        )}

        <Button
          variant="outline"
          size="sm"
          onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
          disabled={safePage >= totalPages}
          className="h-7 w-7 p-0 border-border/60"
        >
          <ChevronRight className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  );

  // ══════════════════════════════════════════════════════════════════════
  //  SKELETON
  // ══════════════════════════════════════════════════════════════════════

  if (loading) {
    return (
      <div className="flex flex-col h-full">
        {/* toolbar skeleton */}
        <div className="flex items-center justify-between mb-5 shrink-0">
          <div className="flex items-center gap-3">
            <div className="h-5 skeleton-shimmer rounded w-28" />
            <div className="h-4 w-px bg-border" />
            {Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-7 skeleton-shimmer rounded w-20" />)}
          </div>
          <div className="flex items-center gap-2">
            <div className="h-8 skeleton-shimmer rounded w-48" />
            <div className="h-8 skeleton-shimmer rounded w-16" />
            <div className="h-8 skeleton-shimmer rounded w-20" />
          </div>
        </div>
        {viewMode === 'cards' ? (
          <div className="max-w-5xl mx-auto w-full grid grid-cols-2 lg:grid-cols-3 gap-4">
            {Array.from({ length: 6 }).map((_, i) => <SkeletonCardRow key={i} />)}
          </div>
        ) : (
          <div className="shrink-0">
            <table className="w-full">
              <thead>
                <tr className="border-b-2 border-border">
                  <th className="w-8 pb-3" />
                  {['Filename', 'Status', 'Started', 'Spk', 'Q&A', ''].map((_, i) => (
                    <th key={i} className="pb-3 text-left">
                      <div className="h-3 skeleton-shimmer rounded w-16" />
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <SkeletonTableRows count={6} />
              </tbody>
            </table>
          </div>
        )}
      </div>
    );
  }

  // ══════════════════════════════════════════════════════════════════════
  //  EMPTY STATE
  // ══════════════════════════════════════════════════════════════════════

  if (runs.length === 0) {
    return (
      <div className="flex flex-col h-full">
        {toolbar}
        <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground">
          <FileSearch className="h-12 w-12 mb-4 opacity-20" />
          <p className="text-base font-semibold mb-1 text-foreground">No analysis runs yet</p>
          <p className="text-sm">Upload a PDF transcript using the button above to get started</p>
        </div>
      </div>
    );
  }

  // ══════════════════════════════════════════════════════════════════════
  //  NO RESULTS (filter/search mismatch)
  // ══════════════════════════════════════════════════════════════════════

  if (filteredRuns.length === 0) {
    return (
      <div className="flex flex-col h-full">
        {toolbar}
        <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground">
          <Search className="h-10 w-10 mb-3 opacity-20" />
          <p className="text-sm font-medium mb-1 text-foreground">No runs match your filters</p>
          <button
            onClick={() => setSearchQuery('')}
            className="text-xs text-primary hover:underline mt-1"
          >
            Clear search
          </button>
        </div>
      </div>
    );
  }

  // ══════════════════════════════════════════════════════════════════════
  //  MAIN DASHBOARD
  // ══════════════════════════════════════════════════════════════════════

  const contentHeader = (
    <div className="max-w-5xl mx-auto w-full flex items-center gap-3 mb-4 shrink-0">
      <span className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground/50 shrink-0">
        {viewMode === 'cards' ? 'Card view' : 'List view'}
      </span>
      <div className="flex-1 h-px bg-border/40" />
      <span className="text-[11px] text-muted-foreground/50 tabular-nums shrink-0">
        {filteredRuns.length} {filteredRuns.length === 1 ? 'run' : 'runs'}
      </span>
    </div>
  );

  return (
    <div className="flex flex-col h-full">
      {toolbar}
      {contentHeader}

      <AnimatePresence mode="wait">

        {viewMode === 'list' ? (

          // ── TABLE ──────────────────────────────────────────────────────
          <motion.div
            key="list"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="flex-1 min-h-0 flex flex-col"
          >
            <div className="max-w-5xl mx-auto w-full pt-2">
            <table className="w-full border-collapse">
              <thead>
                <tr className="border-b-2 border-border">
                  <th className="w-8 pb-2.5 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground/40 select-none">
                    #
                  </th>
                  <th className="pb-2.5 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    Filename
                  </th>
                  <th className="pb-2.5 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground w-32">
                    Status
                  </th>
                  <th className="pb-2.5 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground w-44">
                    <button
                      onClick={() => setSortDir(d => d === 'desc' ? 'asc' : 'desc')}
                      className="inline-flex items-center gap-1 hover:text-foreground transition-colors"
                    >
                      Started
                      {sortDir === 'desc'
                        ? <ArrowDown className="h-2.5 w-2.5" />
                        : <ArrowUp className="h-2.5 w-2.5" />
                      }
                    </button>
                  </th>
                  <th className="pb-2.5 text-right text-xs font-semibold uppercase tracking-wider text-muted-foreground w-16 pr-4">
                    Spk
                  </th>
                  <th className="pb-2.5 text-right text-xs font-semibold uppercase tracking-wider text-muted-foreground w-16 pr-4">
                    Q&A
                  </th>
                  <th className="w-8 pb-2.5" />
                </tr>
              </thead>
              <tbody>
                {paginatedRuns.map((run, index) => (
                  <motion.tr
                    key={run.run_id}
                    custom={index}
                    initial="hidden"
                    animate="visible"
                    variants={rowVariants}
                    onClick={(e) => handleRowClick(e, run)}
                    className="group border-b border-border/50 cursor-pointer transition-colors hover:bg-muted/40 last:border-b-0"
                  >
                    <td className="py-4 pr-4 text-xs text-muted-foreground/70 tabular-nums select-none">
                      {startIndex + index + 1}
                    </td>
                    <td className="py-4 pr-6">
                      <div className="flex items-center gap-2 min-w-0">
                        <FileText className="h-3.5 w-3.5 text-muted-foreground/40 shrink-0" />
                        <div className="min-w-0">
                          <span className="text-sm font-medium text-foreground truncate block" title={run.filename}>
                            {run.display_name || run.filename}
                          </span>
                          {run.error_message && (
                            <span className="text-xs text-destructive truncate block mt-0.5" title={run.error_message}>
                              {run.error_message}
                            </span>
                          )}
                        </div>
                      </div>
                    </td>
                    <td className="py-4 pr-6">
                      <StatusDot status={run.status} />
                    </td>
                    <td className="py-4 pr-6 text-xs text-muted-foreground tabular-nums whitespace-nowrap">
                      {formatDate(run.started_at)}
                    </td>
                    <td className="py-4 pr-4 text-right text-sm font-semibold tabular-nums text-foreground">
                      {run.speaker_count ?? <span className="text-muted-foreground/40 font-normal">—</span>}
                    </td>
                    <td className="py-4 pr-4 text-right text-sm font-semibold tabular-nums text-foreground">
                      {run.qa_count ?? <span className="text-muted-foreground/40 font-normal">—</span>}
                    </td>
                    <td className="py-4 text-right">
                      <button
                        onClick={(e) => { e.stopPropagation(); setDeleteTarget(run.run_id); }}
                        disabled={deleting === run.run_id}
                        className="h-7 w-7 inline-flex items-center justify-center rounded text-muted-foreground/30 hover:text-destructive hover:bg-destructive/10 opacity-0 group-hover:opacity-100 transition-all disabled:opacity-50"
                      >
                        {deleting === run.run_id
                          ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          : <Trash2 className="h-3.5 w-3.5" />
                        }
                      </button>
                    </td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
            </div>
            <div className="flex-1" />
            {pagination && (
              <div className="max-w-5xl mx-auto w-full shrink-0">{pagination}</div>
            )}
          </motion.div>

        ) : (

          // ── CARDS — centered 3-col grid, 9 per page ──────────────────
          <motion.div
            key="cards"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="flex-1 min-h-0 flex flex-col"
          >
            <div className="max-w-5xl mx-auto w-full grid grid-cols-2 lg:grid-cols-3 gap-4 pt-2">
              {paginatedRuns.map((run, index) => (
                <RunCard
                  key={run.run_id}
                  run={run}
                  index={index}
                  deleting={deleting}
                  onSelect={handleRowClick}
                  onDelete={(id) => setDeleteTarget(id)}
                />
              ))}
            </div>

            {pagination && (
              <div className="max-w-5xl mx-auto w-full mt-4">{pagination}</div>
            )}
          </motion.div>

        )}

      </AnimatePresence>

      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => { if (!open) setDeleteTarget(null); }}
        title="Delete run"
        description="This action cannot be undone. Do you want to proceed?"
        confirmLabel="Delete"
        cancelLabel="Cancel"
        variant="destructive"
        onConfirm={() => { if (deleteTarget) executeDelete(deleteTarget); }}
      />
    </div>
  );
}
