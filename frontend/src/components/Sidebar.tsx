/**
 * Sidebar — collapsible left navigation with status filters, upload button,
 * and a Run Info Panel when viewing a run detail.
 */

import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import {
  LayoutDashboard,
  Upload,
  Loader2,
  LogOut,
  ChevronLeft,
  ChevronRight,
  FileText,
  Users,
  MessageCircle,
  Clock,
} from 'lucide-react';
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { useAuth } from '@/context/AuthContext';
import { getUserInitials, getUserColor, formatDuration } from '@/lib/utils';
import { getSpeakers, getRunSummary } from '@/api/client';
import type { RunSummaryResponse, SpeakerRegistryResponse } from '@/types/api';

export type StatusFilter = 'all' | 'completed' | 'running' | 'failed';

interface SidebarProps {
  statusFilter: StatusFilter;
  onStatusChange: (f: StatusFilter) => void;
  statusCounts: Record<StatusFilter, number>;
  onUpload: () => void;
  uploading: boolean;
  showRunDetail: boolean;
  onBack?: () => void;
  runId?: string;
}

const COLLAPSED_KEY = 'sidebar-collapsed';

const filterItems: { key: StatusFilter; label: string; dotClass: string }[] = [
  { key: 'all',       label: 'All Runs',    dotClass: 'bg-muted-foreground/50' },
  { key: 'completed', label: 'Completed',   dotClass: 'bg-emerald-500' },
  { key: 'running',   label: 'In Progress', dotClass: 'bg-blue-500' },
  { key: 'failed',    label: 'Failed',      dotClass: 'bg-red-500' },
];

const DONUT_COLORS: Record<string, string> = {
  Management: '#1e3a8a',
  Analysts: '#15803d',
  Moderators: '#7e22ce',
};

interface RunInfoState {
  summary: RunSummaryResponse | null;
  speakers: SpeakerRegistryResponse | null;
}

export function Sidebar({
  statusFilter,
  onStatusChange,
  statusCounts,
  onUpload,
  uploading,
  showRunDetail,
  runId,
}: SidebarProps) {
  const { user, logout } = useAuth();
  const [collapsed, setCollapsed] = useState<boolean>(() =>
    localStorage.getItem(COLLAPSED_KEY) === 'true'
  );
  const [showLogoutDialog, setShowLogoutDialog] = useState(false);
  const [runInfo, setRunInfo] = useState<RunInfoState>({ summary: null, speakers: null });

  // Fetch run info when in detail mode
  useEffect(() => {
    if (!showRunDetail || !runId) {
      setRunInfo({ summary: null, speakers: null });
      return;
    }

    let cancelled = false;

    Promise.all([
      getRunSummary(runId).catch(() => null),
      getSpeakers(runId).catch(() => null),
    ]).then(([summary, speakers]) => {
      if (!cancelled) {
        setRunInfo({ summary, speakers });
      }
    });

    return () => { cancelled = true; };
  }, [showRunDetail, runId]);

  function toggleCollapsed() {
    const next = !collapsed;
    setCollapsed(next);
    localStorage.setItem(COLLAPSED_KEY, String(next));
  }

  const initials = user ? getUserInitials(user.username) : '?';
  const avatarColor = user ? getUserColor(user.username) : 'bg-gray-500';

  // Build donut data
  const { summary, speakers } = runInfo;
  const donutData = speakers && summary?.status === 'completed'
    ? [
        { name: 'Management', value: speakers.management_count, fill: DONUT_COLORS.Management },
        { name: 'Analysts',   value: speakers.analyst_count,    fill: DONUT_COLORS.Analysts   },
        { name: 'Moderators', value: speakers.moderator_count,  fill: DONUT_COLORS.Moderators },
      ].filter((d) => d.value > 0)
    : [];

  return (
    <>
      <motion.aside
        animate={{ width: collapsed ? 64 : 240 }}
        transition={{ duration: 0.25, ease: [0.4, 0, 0.2, 1] }}
        className="relative flex-shrink-0 bg-card border-r border-border flex flex-col z-10"
      >
        {/* Toggle button */}
        <button
          onClick={toggleCollapsed}
          className="absolute -right-3 top-5 z-20 w-6 h-6 rounded-full bg-card border border-border flex items-center justify-center shadow-sm hover:bg-accent transition-colors"
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed
            ? <ChevronRight className="h-3 w-3 text-muted-foreground" />
            : <ChevronLeft className="h-3 w-3 text-muted-foreground" />
          }
        </button>

        {/* Inner wrapper */}
        <div className="flex flex-col flex-1 overflow-hidden min-w-0">

          {/* Nav section */}
          <div className="px-2 pt-4 pb-2">
            <div className="flex items-center gap-3 px-2 py-2 rounded-lg cursor-default text-primary bg-primary/8">
              <LayoutDashboard className="h-4 w-4 shrink-0" />
              {!collapsed && (
                <span className="text-sm font-medium truncate">Analysis Runs</span>
              )}
            </div>
          </div>

          {/* Divider */}
          <div className="mx-3 border-t border-border" />

          {/* Run Info Panel — shown when in run detail mode */}
          {showRunDetail && !collapsed && summary && (
            <>
              <div className="px-3 py-3 flex flex-col gap-3">
                {/* Filename + status */}
                <div>
                  <p
                    className="text-xs font-medium text-foreground truncate"
                    title={summary.display_name ?? summary.filename}
                  >
                    {summary.display_name ?? summary.filename}
                  </p>
                  <div className="mt-1">
                    <Badge
                      variant={
                        summary.status === 'completed' ? 'success'
                          : summary.status === 'failed' ? 'error'
                          : summary.status === 'running' ? 'default'
                          : 'warning'
                      }
                      className="text-[10px] px-1.5 py-0"
                    >
                      {summary.status}
                    </Badge>
                  </div>
                </div>

                {/* Compact stats */}
                <div className="grid grid-cols-2 gap-1.5">
                  <div className="flex items-center gap-1.5 px-2 py-1.5 rounded-md bg-muted/50">
                    <FileText className="h-3 w-3 text-muted-foreground shrink-0" />
                    <div>
                      <div className="text-xs font-semibold leading-none">{summary.page_count}</div>
                      <div className="text-[10px] text-muted-foreground leading-none mt-0.5">pages</div>
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5 px-2 py-1.5 rounded-md bg-muted/50">
                    <Users className="h-3 w-3 text-muted-foreground shrink-0" />
                    <div>
                      <div className="text-xs font-semibold leading-none">{summary.speaker_count}</div>
                      <div className="text-[10px] text-muted-foreground leading-none mt-0.5">speakers</div>
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5 px-2 py-1.5 rounded-md bg-muted/50">
                    <MessageCircle className="h-3 w-3 text-muted-foreground shrink-0" />
                    <div>
                      <div className="text-xs font-semibold leading-none">{summary.qa_count}</div>
                      <div className="text-[10px] text-muted-foreground leading-none mt-0.5">Q&amp;As</div>
                    </div>
                  </div>
                  {summary.duration_seconds !== null && (
                    <div className="flex items-center gap-1.5 px-2 py-1.5 rounded-md bg-muted/50">
                      <Clock className="h-3 w-3 text-muted-foreground shrink-0" />
                      <div>
                        <div className="text-xs font-semibold leading-none">
                          {formatDuration(summary.duration_seconds)}
                        </div>
                        <div className="text-[10px] text-muted-foreground leading-none mt-0.5">duration</div>
                      </div>
                    </div>
                  )}
                </div>

                {/* Compact speaker donut */}
                {donutData.length > 0 && (
                  <div>
                    <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/50 mb-1">
                      Speaker Roles
                    </p>
                    <div className="flex items-center gap-2">
                      <ResponsiveContainer width={80} height={80}>
                        <PieChart>
                          <Pie
                            data={donutData}
                            cx="50%"
                            cy="50%"
                            innerRadius={24}
                            outerRadius={38}
                            paddingAngle={3}
                            dataKey="value"
                          >
                            {donutData.map((entry, index) => (
                              <Cell key={`cell-${index}`} fill={entry.fill} />
                            ))}
                          </Pie>
                          <Tooltip
                            // eslint-disable-next-line @typescript-eslint/no-explicit-any
                            formatter={(value: any) => [value ?? '', '']}
                            contentStyle={{
                              fontSize: '11px',
                              borderRadius: '6px',
                              border: '1px solid hsl(var(--border))',
                            }}
                          />
                        </PieChart>
                      </ResponsiveContainer>
                      <div className="flex flex-col gap-1 flex-1 min-w-0">
                        {donutData.map((entry) => (
                          <div key={entry.name} className="flex items-center justify-between gap-1">
                            <div className="flex items-center gap-1 min-w-0">
                              <div
                                className="w-2 h-2 rounded-full shrink-0"
                                style={{ backgroundColor: entry.fill }}
                              />
                              <span className="text-[10px] text-muted-foreground truncate">
                                {entry.name}
                              </span>
                            </div>
                            <span className="text-[10px] font-semibold shrink-0">{entry.value}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>
              <div className="mx-3 border-t border-border" />
            </>
          )}

          {/* Collapsed run detail indicator */}
          {showRunDetail && collapsed && (
            <div className="px-2 py-3 flex flex-col gap-2">
              <div className="flex flex-col items-center gap-1" title="Run detail">
                <FileText className="h-4 w-4 text-primary" />
              </div>
            </div>
          )}

          {/* Filter section — only visible when not in run detail */}
          {!showRunDetail && (
            <div className="px-2 py-3 flex flex-col gap-0.5">
              {!collapsed && (
                <p className="px-2 mb-1 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/50">
                  Filter
                </p>
              )}
              {filterItems.map(({ key, label, dotClass }) => {
                const isActive = statusFilter === key;
                return (
                  <button
                    key={key}
                    onClick={() => onStatusChange(key)}
                    title={collapsed ? label : undefined}
                    className={`
                      flex items-center gap-2.5 px-2 py-1.5 rounded-lg text-sm transition-colors w-full text-left
                      ${isActive
                        ? 'bg-primary/8 text-primary font-medium'
                        : 'text-muted-foreground hover:bg-accent hover:text-foreground'
                      }
                    `}
                  >
                    <span className={`w-2 h-2 rounded-full shrink-0 ${dotClass} ${key === 'running' && 'animate-pulse'}`} />
                    {!collapsed && (
                      <>
                        <span className="flex-1 truncate">{label}</span>
                        <span className={`
                          text-[10px] font-semibold tabular-nums rounded px-1.5 py-0.5
                          ${isActive
                            ? 'bg-primary text-primary-foreground'
                            : 'bg-muted text-muted-foreground'
                          }
                        `}>
                          {statusCounts[key]}
                        </span>
                      </>
                    )}
                  </button>
                );
              })}
            </div>
          )}

          {/* Flex spacer */}
          <div className="flex-1" />

          {/* Divider */}
          <div className="mx-3 border-t border-border" />

          {/* Upload button */}
          <div className="px-2 py-3">
            <Button
              onClick={onUpload}
              disabled={uploading}
              size="sm"
              className={`w-full h-9 gap-2 ${collapsed ? 'px-0 justify-center' : ''}`}
              title={collapsed ? 'Upload PDF' : undefined}
            >
              {uploading
                ? <Loader2 className="h-4 w-4 shrink-0 animate-spin" />
                : <Upload className="h-4 w-4 shrink-0" />
              }
              {!collapsed && (
                <span>{uploading ? 'Uploading...' : 'Upload PDF'}</span>
              )}
            </Button>
          </div>

          {/* User block */}
          {user && (
            <>
              <div className="mx-3 border-t border-border" />
              <div className="px-2 py-3">
                <button
                  onClick={() => setShowLogoutDialog(true)}
                  title={collapsed ? `${user.username} — Log out` : 'Log out'}
                  className={`
                    flex items-center gap-2.5 w-full px-2 py-1.5 rounded-lg
                    hover:bg-destructive/10 hover:text-destructive transition-colors text-left
                    ${collapsed ? 'justify-center' : ''}
                  `}
                >
                  <div
                    className={`w-7 h-7 rounded-full flex items-center justify-center text-white text-xs font-semibold shrink-0 ${avatarColor}`}
                  >
                    {initials}
                  </div>
                  {!collapsed && (
                    <>
                      <div className="min-w-0 flex-1">
                        <p className="text-xs font-medium text-foreground truncate">{user.username}</p>
                        <p className="text-[10px] text-muted-foreground truncate">{user.role}</p>
                      </div>
                      <LogOut className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                    </>
                  )}
                </button>
              </div>
            </>
          )}
        </div>{/* end inner overflow wrapper */}
      </motion.aside>

      <ConfirmDialog
        open={showLogoutDialog}
        onOpenChange={setShowLogoutDialog}
        title="Log out"
        description="Are you sure you want to log out?"
        confirmLabel="Logout"
        cancelLabel="Cancel"
        variant="destructive"
        onConfirm={logout}
      />
    </>
  );
}
