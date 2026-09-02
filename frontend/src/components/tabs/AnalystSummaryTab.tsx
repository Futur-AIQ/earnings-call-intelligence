/**
 * Analyst Summary Tab
 *
 * Groups questions by questioner name (the only source of truth).
 * No role inference, no AI generation, no backend changes.
 */

import { useState, useEffect, useMemo } from 'react';
import { Loader2, AlertCircle, User, MessageSquare, Users, TrendingUp } from 'lucide-react';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';
import { getQAUnits } from '@/api/client';
import type { QAUnit, QAResponse } from '@/types/api';

interface AnalystSummaryTabProps {
  runId: string;
}

interface QuestionerGroup {
  name: string;
  company: string | null;
  questions: { text: string; sequence: number }[];
}

function groupByQuestioner(qaUnits: QAUnit[]): QuestionerGroup[] {
  const map = new Map<string, QuestionerGroup>();

  for (const qa of qaUnits) {
    const key = qa.questioner_name;
    if (!map.has(key)) {
      map.set(key, {
        name: qa.questioner_name,
        company: qa.questioner_company,
        questions: [],
      });
    }
    map.get(key)!.questions.push({
      text: qa.question_text,
      sequence: qa.sequence,
    });
  }

  // Sort: most questions first, then alphabetically
  return Array.from(map.values()).sort((a, b) => {
    if (b.questions.length !== a.questions.length) {
      return b.questions.length - a.questions.length;
    }
    return a.name.localeCompare(b.name);
  });
}

export function AnalystSummaryTab({ runId }: AnalystSummaryTabProps) {
  const [data, setData] = useState<QAResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedName, setSelectedName] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    setSelectedName(null);

    getQAUnits(runId)
      .then(setData)
      .catch((err) =>
        setError(err instanceof Error ? err.message : 'Failed to load Q&A data')
      )
      .finally(() => setLoading(false));
  }, [runId]);

  const groups = useMemo(() => {
    if (!data) return [];
    return groupByQuestioner(data.qa_units);
  }, [data]);

  useEffect(() => {
    if (groups.length > 0 && !selectedName) {
      setSelectedName(groups[0].name);
    }
  }, [groups, selectedName]);

  const selectedGroup = useMemo(
    () => groups.find((g) => g.name === selectedName) ?? null,
    [groups, selectedName]
  );

  // Loading state
  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3 text-destructive">
        <AlertCircle className="h-10 w-10" />
        <p className="text-sm">{error}</p>
      </div>
    );
  }

  // Empty state — no QA data at all
  if (groups.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-muted-foreground gap-2">
        <User className="h-10 w-10 opacity-50" />
        <p className="text-sm">No questioners found in this transcript</p>
      </div>
    );
  }

  const totalQuestions = groups.reduce((sum, g) => sum + g.questions.length, 0);

  const mostActive = groups[0] ?? null;
  const avgQuestions = groups.length > 0
    ? (totalQuestions / groups.length).toFixed(1)
    : '0';

  return (
    <div className="h-full flex flex-col">
      {/* Stats Bar */}
      <div className="flex-shrink-0 px-6 py-3 border-b bg-muted/20 flex items-center gap-6 flex-wrap">
        <div className="flex items-center gap-1.5">
          <Users className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm text-muted-foreground">Analysts:</span>
          <span className="text-sm font-semibold">{groups.length}</span>
        </div>
        <div className="w-px h-4 bg-border" />
        <div className="flex items-center gap-1.5">
          <MessageSquare className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm text-muted-foreground">Questions:</span>
          <span className="text-sm font-semibold">{totalQuestions}</span>
        </div>
        <div className="w-px h-4 bg-border" />
        {mostActive && (
          <>
            <div className="flex items-center gap-1.5">
              <TrendingUp className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm text-muted-foreground">Most Active:</span>
              <span className="text-sm font-semibold truncate max-w-[140px]" title={mostActive.name}>
                {mostActive.name} ({mostActive.questions.length} Qs)
              </span>
            </div>
            <div className="w-px h-4 bg-border" />
          </>
        )}
        <div className="flex items-center gap-1.5">
          <span className="text-sm text-muted-foreground">Avg Qs/Analyst:</span>
          <span className="text-sm font-semibold">{avgQuestions}</span>
        </div>
      </div>

      {/* Split Layout */}
      <div className="flex flex-1 overflow-hidden min-h-0">
        {/* Sidebar - Questioner List */}
        <div className="w-72 border-r flex flex-col flex-shrink-0">
          <ScrollArea className="flex-1">
            <div className="p-2">
              {groups.map((group) => (
                <button
                  key={group.name}
                  onClick={() => setSelectedName(group.name)}
                  className={cn(
                    'w-full text-left p-3 rounded-lg mb-1 transition-all',
                    'hover:bg-accent/50',
                    selectedName === group.name && 'bg-accent shadow-sm'
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <div className="font-medium text-sm truncate" title={group.name}>
                        {group.name}
                      </div>
                      {group.company && (
                        <div className="text-xs text-muted-foreground truncate mt-0.5">
                          {group.company}
                        </div>
                      )}
                    </div>
                    <span className="flex-shrink-0 text-xs font-medium text-muted-foreground bg-muted px-2 py-0.5 rounded-full">
                      {group.questions.length}
                    </span>
                  </div>
                </button>
              ))}
            </div>
          </ScrollArea>
        </div>

        {/* Main - Question List */}
        <div className="flex-1 overflow-hidden flex flex-col">
          {selectedGroup ? (
            <>
              <div className="px-6 py-4 border-b flex-shrink-0">
                <h2 className="text-lg font-semibold">{selectedGroup.name}</h2>
                <p className="text-sm text-muted-foreground mt-0.5">
                  {selectedGroup.questions.length} question
                  {selectedGroup.questions.length !== 1 ? 's' : ''}
                  {selectedGroup.company ? ` · ${selectedGroup.company}` : ''}
                </p>
              </div>
              <ScrollArea className="flex-1">
                <div className="px-6 py-4 space-y-3">
                  {selectedGroup.questions.map((q, idx) => (
                    <div
                      key={q.sequence}
                      className="flex gap-3 p-4 rounded-lg border border-border/50 bg-muted/20 hover:bg-muted/40 transition-colors"
                    >
                      <div className="flex-shrink-0 mt-0.5">
                        <span className="flex items-center justify-center h-7 w-7 rounded-full bg-primary/10 text-primary text-xs font-semibold">
                          {idx + 1}
                        </span>
                      </div>
                      <p className="text-sm leading-relaxed pt-1">{q.text}</p>
                    </div>
                  ))}
                </div>
              </ScrollArea>
            </>
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-muted-foreground gap-3">
              <MessageSquare className="h-10 w-10 opacity-40" />
              <p className="text-sm">Select a questioner to view their questions</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
