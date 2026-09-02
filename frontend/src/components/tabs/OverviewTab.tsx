/**
 * Overview Tab
 *
 * Shows high-level summary stats, data visualisation charts,
 * and a real-time pipeline stage stepper.
 */

import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import {
  FileText,
  Users,
  MessageCircle,
  AlertCircle,
  CheckCircle,
  Clock,
  Loader2,
  AlertTriangle,
  XCircle,
} from 'lucide-react';
import {
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { formatDate, formatDuration, cn } from '@/lib/utils';
import { getSpeakers } from '@/api/client';
import type { RunSummaryResponse, PipelineStageStatus, StageStatus } from '@/types/api';

// All 6 expected pipeline stages in execution order
const EXPECTED_STAGES = [
  'extraction',
  'metadata',
  'boundary',
  'speakers',
  'qa',
  'strategic',
] as const;

// Human-readable labels for stage names
const STAGE_LABELS: Record<string, string> = {
  extraction: 'PDF Extraction',
  metadata: 'Metadata',
  boundary: 'Boundary Detection',
  speakers: 'Speaker Registry',
  qa: 'Q&A Extraction',
  strategic: 'Strategic Statements',
};

interface OverviewTabProps {
  summary: RunSummaryResponse;
  runId: string;
}

interface SpeakerRoles {
  management: number;
  analyst: number;
  moderator: number;
}

const SPEAKER_PIE_COLORS: Record<string, string> = {
  management: '#1e3a8a',
  analyst: '#15803d',
  moderator: '#7e22ce',
};

export function OverviewTab({ summary, runId }: OverviewTabProps) {
  const [speakerRoles, setSpeakerRoles] = useState<SpeakerRoles | null>(null);

  // Fetch speaker breakdown when run completes
  useEffect(() => {
    if (summary.status !== 'completed' || !runId) return;
    getSpeakers(runId)
      .then((d) =>
        setSpeakerRoles({
          management: d.management_count,
          analyst: d.analyst_count,
          moderator: d.moderator_count,
        })
      )
      .catch(() => {});
  }, [summary.status, runId]);

  const containerVariants = {
    hidden: { opacity: 0 },
    show: {
      opacity: 1,
      transition: { staggerChildren: 0.1 },
    },
  };

  const itemVariants = {
    hidden: { opacity: 0, y: 20 },
    show: { opacity: 1, y: 0 },
  };

  // Build stage map from summary, filling in "pending" for any missing stages
  const stageMap = new Map(summary.stages.map((s) => [s.stage_name, s]));
  const allStages: PipelineStageStatus[] = EXPECTED_STAGES.map(
    (name) =>
      stageMap.get(name) ?? {
        stage_name: name,
        status: 'pending' as StageStatus,
        started_at: null,
        completed_at: null,
        error_message: null,
        warnings: [],
      }
  );

  // Chart: Speaker role donut
  const speakerPieData = speakerRoles
    ? [
        { name: 'Management', value: speakerRoles.management, fill: SPEAKER_PIE_COLORS.management },
        { name: 'Analysts', value: speakerRoles.analyst, fill: SPEAKER_PIE_COLORS.analyst },
        { name: 'Moderators', value: speakerRoles.moderator, fill: SPEAKER_PIE_COLORS.moderator },
      ].filter((d) => d.value > 0)
    : [];

  // Chart: Q&A composition bar
  const originalQA = Math.max(0, (summary.qa_count ?? 0) - (summary.follow_up_count ?? 0));
  const followUpQA = summary.follow_up_count ?? 0;
  const qaBarData = [
    { name: 'Original', value: originalQA, fill: '#1e3a8a' },
    { name: 'Follow-ups', value: followUpQA, fill: '#f59e0b' },
  ];
  const showCharts =
    summary.status === 'completed' &&
    (speakerPieData.length > 0 || summary.qa_count > 0);

  function getStageIcon(status: string) {
    switch (status) {
      case 'completed':
        return <CheckCircle className="h-4 w-4 text-green-500 flex-shrink-0" />;
      case 'running':
        return <Loader2 className="h-4 w-4 text-blue-500 animate-spin flex-shrink-0" />;
      case 'failed':
        return <XCircle className="h-4 w-4 text-red-500 flex-shrink-0" />;
      case 'skipped':
        return <Clock className="h-4 w-4 text-muted-foreground flex-shrink-0" />;
      default: // pending
        return (
          <div className="h-4 w-4 rounded-full border-2 border-muted-foreground/30 flex-shrink-0" />
        );
    }
  }

  function getStageSubtext(stage: PipelineStageStatus) {
    if (stage.status === 'running') return 'Running…';
    if (stage.status === 'completed' && stage.completed_at) {
      return formatDate(stage.completed_at);
    }
    if (stage.status === 'failed' && stage.error_message) {
      return stage.error_message;
    }
    if (stage.status === 'skipped') return 'Skipped';
    return 'Waiting…';
  }

  return (
    <ScrollArea className="h-full">
      <motion.div
        variants={containerVariants}
        initial="hidden"
        animate="show"
        className="p-6 space-y-6"
      >
        {/* Stats Cards */}
        <motion.div
          variants={itemVariants}
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4"
        >
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center gap-4">
                <div className="p-3 rounded-lg bg-blue-100 dark:bg-blue-900">
                  <FileText className="h-6 w-6 text-blue-600 dark:text-blue-400" />
                </div>
                <div>
                  <div className="text-2xl font-bold">{summary.page_count}</div>
                  <div className="text-sm text-muted-foreground">Pages</div>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center gap-4">
                <div className="p-3 rounded-lg bg-purple-100 dark:bg-purple-900">
                  <Users className="h-6 w-6 text-purple-600 dark:text-purple-400" />
                </div>
                <div>
                  <div className="text-2xl font-bold">{summary.speaker_count}</div>
                  <div className="text-sm text-muted-foreground">Speakers</div>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center gap-4">
                <div className="p-3 rounded-lg bg-green-100 dark:bg-green-900">
                  <MessageCircle className="h-6 w-6 text-green-600 dark:text-green-400" />
                </div>
                <div>
                  <div className="text-2xl font-bold">{summary.qa_count}</div>
                  <div className="text-sm text-muted-foreground">Q&A Units</div>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center gap-4">
                <div className="p-3 rounded-lg bg-amber-100 dark:bg-amber-900">
                  <MessageCircle className="h-6 w-6 text-amber-600 dark:text-amber-400" />
                </div>
                <div>
                  <div className="text-2xl font-bold">{summary.follow_up_count}</div>
                  <div className="text-sm text-muted-foreground">Follow-ups</div>
                </div>
              </div>
            </CardContent>
          </Card>
        </motion.div>

        {/* Insights Charts — shown only when run is completed and data exists */}
        {showCharts && (
          <motion.div
            variants={itemVariants}
            className="grid grid-cols-1 lg:grid-cols-2 gap-6"
          >
            {/* Speaker Role Distribution Donut */}
            {speakerPieData.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">Speaker Roles</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="flex items-center gap-6">
                    <ResponsiveContainer width={160} height={160}>
                      <PieChart>
                        <Pie
                          data={speakerPieData}
                          cx="50%"
                          cy="50%"
                          innerRadius={45}
                          outerRadius={72}
                          paddingAngle={3}
                          dataKey="value"
                        >
                          {speakerPieData.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={entry.fill} />
                          ))}
                        </Pie>
                        <Tooltip
                          formatter={(value: number | string | Array<number | string> | undefined) => [Array.isArray(value) ? value.join(', ') : value ?? '', '']}
                          contentStyle={{
                            fontSize: '12px',
                            borderRadius: '6px',
                            border: '1px solid hsl(var(--border))',
                          }}
                        />
                      </PieChart>
                    </ResponsiveContainer>
                    <div className="flex flex-col gap-2 flex-1">
                      {speakerPieData.map((entry) => (
                        <div key={entry.name} className="flex items-center justify-between gap-3">
                          <div className="flex items-center gap-2">
                            <div
                              className="w-3 h-3 rounded-full flex-shrink-0"
                              style={{ backgroundColor: entry.fill }}
                            />
                            <span className="text-sm text-muted-foreground">{entry.name}</span>
                          </div>
                          <span className="text-sm font-semibold">{entry.value}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Q&A Composition Bar Chart */}
            {summary.qa_count > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">Q&A Composition</CardTitle>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={160}>
                    <BarChart
                      data={qaBarData}
                      layout="vertical"
                      margin={{ top: 4, right: 16, bottom: 4, left: 8 }}
                    >
                      <XAxis type="number" tick={{ fontSize: 12 }} allowDecimals={false} />
                      <YAxis
                        type="category"
                        dataKey="name"
                        tick={{ fontSize: 12 }}
                        width={72}
                      />
                      <Tooltip
                        formatter={(value: number | string | Array<number | string> | undefined) => [Array.isArray(value) ? value.join(', ') : value ?? '', '']}
                        contentStyle={{
                          fontSize: '12px',
                          borderRadius: '6px',
                          border: '1px solid hsl(var(--border))',
                        }}
                      />
                      <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                        {qaBarData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.fill} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                  <div className="mt-3 flex items-center gap-4 text-xs text-muted-foreground">
                    <div className="flex items-center gap-1.5">
                      <div className="w-2.5 h-2.5 rounded-full bg-[#1e3a8a]" />
                      <span>{originalQA} original</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <div className="w-2.5 h-2.5 rounded-full bg-[#f59e0b]" />
                      <span>{followUpQA} follow-up{followUpQA !== 1 ? 's' : ''}</span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}
          </motion.div>
        )}

        {/* Status and Pipeline */}
        <motion.div
          variants={itemVariants}
          className="grid grid-cols-1 lg:grid-cols-2 gap-6"
        >
          {/* Run Status */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Run Status</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Status</span>
                <Badge
                  variant={
                    summary.status === 'completed'
                      ? 'success'
                      : summary.status === 'failed'
                      ? 'error'
                      : summary.status === 'running'
                      ? 'default'
                      : 'warning'
                  }
                >
                  {summary.status}
                </Badge>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Started</span>
                <span className="font-mono text-sm">{formatDate(summary.started_at)}</span>
              </div>

              {summary.completed_at && (
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Completed</span>
                  <span className="font-mono text-sm">{formatDate(summary.completed_at)}</span>
                </div>
              )}

              {summary.duration_seconds !== null && (
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Duration</span>
                  <span className="font-mono text-sm">
                    {formatDuration(summary.duration_seconds)}
                  </span>
                </div>
              )}

              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Text Length</span>
                <span className="font-mono text-sm">
                  {summary.total_text_length.toLocaleString()} chars
                </span>
              </div>
            </CardContent>
          </Card>

          {/* Pipeline Stages — real-time stepper */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Pipeline Stages</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {allStages.map((stage) => (
                  <div
                    key={stage.stage_name}
                    className={cn(
                      'flex items-center gap-3 px-3 py-2.5 rounded-lg',
                      stage.status === 'completed' && 'bg-green-50 dark:bg-green-950/30',
                      stage.status === 'running' && 'bg-blue-50 dark:bg-blue-950/30',
                      stage.status === 'failed' && 'bg-red-50 dark:bg-red-950/30',
                      (stage.status === 'pending' || stage.status === 'skipped') && 'bg-muted/50'
                    )}
                  >
                    {getStageIcon(stage.status)}
                    <div className="flex-1 min-w-0">
                      <div
                        className={cn(
                          'text-sm font-medium',
                          stage.status === 'running' && 'text-blue-700 dark:text-blue-300',
                          stage.status === 'completed' && 'text-green-700 dark:text-green-300',
                          stage.status === 'failed' && 'text-red-700 dark:text-red-300',
                          (stage.status === 'pending' || stage.status === 'skipped') &&
                            'text-muted-foreground'
                        )}
                      >
                        {STAGE_LABELS[stage.stage_name] ?? stage.stage_name.replace(/_/g, ' ')}
                      </div>
                      <div className="text-xs text-muted-foreground truncate">
                        {getStageSubtext(stage)}
                      </div>
                    </div>
                    <Badge
                      variant="outline"
                      className={cn(
                        'text-xs flex-shrink-0',
                        stage.status === 'running' && 'border-blue-400 text-blue-600',
                        stage.status === 'completed' && 'border-green-400 text-green-600',
                        stage.status === 'failed' && 'border-red-400 text-red-600'
                      )}
                    >
                      {stage.status}
                    </Badge>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </motion.div>

        {/* Errors and Warnings */}
        {(summary.errors.length > 0 || summary.warnings.length > 0) && (
          <motion.div variants={itemVariants}>
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Issues</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {summary.errors.map((error, i) => (
                  <div
                    key={i}
                    className="flex items-start gap-3 p-3 rounded-lg bg-red-50 dark:bg-red-950/30"
                  >
                    <AlertCircle className="h-5 w-5 text-red-500 flex-shrink-0 mt-0.5" />
                    <span className="text-sm text-red-800 dark:text-red-200">{error}</span>
                  </div>
                ))}

                {summary.warnings.map((warning, i) => (
                  <div
                    key={i}
                    className="flex items-start gap-3 p-3 rounded-lg bg-yellow-50 dark:bg-yellow-950/30"
                  >
                    <AlertTriangle className="h-5 w-5 text-yellow-600 flex-shrink-0 mt-0.5" />
                    <span className="text-sm text-yellow-800 dark:text-yellow-200">{warning}</span>
                  </div>
                ))}
              </CardContent>
            </Card>
          </motion.div>
        )}
      </motion.div>
    </ScrollArea>
  );
}
