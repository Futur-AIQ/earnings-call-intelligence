/**
 * Main Application Component
 *
 * Layout: header + sidebar + main content area.
 * Status filter state is lifted to App and passed down to RunsTable via props.
 */

import { useState, useRef } from 'react';
import { ArrowLeft, Loader2 } from 'lucide-react';

import { Header } from '@/components/Header';
import { Sidebar } from '@/components/Sidebar';
import { RunsTable } from '@/components/RunsTable';
import { RunDetail } from '@/components/RunDetail';
import { LoginPage } from '@/components/LoginPage';
import { Button } from '@/components/ui/button';
import { uploadPDF, analyzePDF } from '@/api/client';
import { useAuth } from '@/context/AuthContext';
import type { StatusFilter } from '@/components/Sidebar';

export default function App() {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="h-screen flex items-center justify-center bg-background">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <LoginPage />;
  }

  return <AuthenticatedApp />;
}

function AuthenticatedApp() {
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [statusCounts, setStatusCounts] = useState<Record<StatusFilter, number>>({
    all: 0, completed: 0, running: 0, failed: 0,
  });
  const fileInputRef = useRef<HTMLInputElement>(null);

  function handleUploadClick() {
    fileInputRef.current?.click();
  }

  async function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;

    setUploading(true);
    try {
      const uploadResponse = await uploadPDF(file);
      const analyzeResponse = await analyzePDF(uploadResponse.file_id);

      setRefreshTrigger(prev => prev + 1);
      setSelectedRunId(analyzeResponse.run_id);
    } catch (err) {
      console.error('Upload failed:', err);
      alert('Upload failed: ' + (err instanceof Error ? err.message : 'Unknown error'));
    } finally {
      setUploading(false);
      event.target.value = '';
    }
  }

  function handleBack() {
    setSelectedRunId(null);
    setRefreshTrigger(prev => prev + 1);
  }

  return (
    <div className="h-screen flex flex-col bg-background overflow-hidden">
      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf"
        className="hidden"
        onChange={handleFileChange}
        disabled={uploading}
      />

      {/* Header */}
      <Header onLogoClick={handleBack} />

      {/* Body: sidebar + main */}
      <div className="flex flex-1 overflow-hidden">
        <Sidebar
          statusFilter={statusFilter}
          onStatusChange={setStatusFilter}
          statusCounts={statusCounts}
          onUpload={handleUploadClick}
          uploading={uploading}
          showRunDetail={!!selectedRunId}
          onBack={handleBack}
          runId={selectedRunId ?? undefined}
        />

        <main className="flex-1 overflow-hidden grid-bg">
          {selectedRunId ? (
            <div className="flex flex-col h-full">
              <div className="px-6 py-3 border-b bg-card/80 backdrop-blur-sm flex-shrink-0">
                <Button variant="ghost" size="sm" onClick={handleBack} className="h-8 text-muted-foreground hover:text-foreground">
                  <ArrowLeft className="h-4 w-4 mr-2" />
                  Back to all runs
                </Button>
              </div>
              <div className="flex-1 overflow-hidden bg-background">
                <RunDetail runId={selectedRunId} />
              </div>
            </div>
          ) : (
            <div className="h-full p-5 overflow-hidden flex flex-col">
              <div className="bg-card rounded-xl border border-border/40 shadow-sm flex-1 overflow-hidden flex flex-col p-6">
                <RunsTable
                  onSelectRun={setSelectedRunId}
                  refreshTrigger={refreshTrigger}
                  statusFilter={statusFilter}
                  onCountsChange={setStatusCounts}
                />
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
