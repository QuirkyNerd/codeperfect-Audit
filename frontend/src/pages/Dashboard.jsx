import React, { useRef, useCallback, memo, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import Sidebar from '../components/Sidebar.jsx';
import TopBar from '../components/TopBar.jsx';
import UploadNote from '../components/UploadNote.jsx';
import CodeInput from '../components/CodeInput.jsx';
import AuditResults from '../components/AuditResults.jsx';
import { useAudit } from '../main.jsx';
import '../styles/dashboard.css';

const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

const StepBadge = memo(function StepBadge({ step }) {
  const statusLabel =
    step.status === 'success' ? 'Completed' :
    step.status === 'failed' ? 'Failed' :
    'In progress';

  return (
    <div className={`step-badge ${step.status || ''}`}>
      <span>{statusLabel}</span>
      {step.label || step.step}
      {step.duration_ms > 0 && (
        <span>
          {(step.duration_ms / 1000).toFixed(1)}s
        </span>
      )}
    </div>
  );
});

export default function Dashboard() {
  const {
    noteText, setNoteText,
    humanCodes, setHumanCodes,
    auditResult, setAuditResult,
    pipelineSteps, setPipelineSteps,
    isRunning, setIsRunning,
    auditError, setAuditError,
    file, setFile,
    resetAudit,
  } = useAudit();

  const resultsRef = useRef(null);
  const location = useLocation();
  const caseData = location.state?.caseData;

  const isInitialMount = useRef(true);

  // Initialize state based on navigation state or restore from sessionStorage
  useEffect(() => {
    if (!isInitialMount.current) return;
    isInitialMount.current = false;

    if (caseData) {
      setNoteText(caseData.input_text || '');
      setHumanCodes(Array.isArray(caseData.human_codes) ? caseData.human_codes : []);
      setPipelineSteps(Array.isArray(caseData.pipeline_log) ? caseData.pipeline_log : []);
      setAuditResult(caseData);
      setFile(null);
    } else {
      try {
        const stored = sessionStorage.getItem("audit_state");
        if (stored) {
          const parsed = JSON.parse(stored);
          if (parsed.noteText) setNoteText(parsed.noteText);
          if (parsed.humanCodes) setHumanCodes(parsed.humanCodes);
          if (parsed.auditResult) setAuditResult(parsed.auditResult);
          if (parsed.pipelineSteps) setPipelineSteps(parsed.pipelineSteps);
        }
      } catch (e) {
        sessionStorage.removeItem("audit_state");
      }
    }
  }, [caseData, setNoteText, setHumanCodes, setPipelineSteps, setAuditResult, setFile]);

  // Persist state to sessionStorage on every update
  useEffect(() => {
    if (noteText || humanCodes.length > 0 || auditResult || pipelineSteps.length > 0) {
      sessionStorage.setItem("audit_state", JSON.stringify({
        noteText,
        humanCodes,
        pipelineSteps,
        auditResult
      }));
    }
  }, [noteText, humanCodes, pipelineSteps, auditResult]);

  const handleRunAudit = useCallback(() => {
    if (!noteText.trim() && !file) return;
    setAuditResult(null);
    setPipelineSteps([]);
    setAuditError('');
    setIsRunning(true);

    const token = sessionStorage.getItem('access_token');
    let fetchConfig = {};
    let url = `${BASE}/audit`;

    if (file) {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('human_codes', JSON.stringify(Array.isArray(humanCodes) ? humanCodes : []));
      url = `${BASE}/audit/file`;
      fetchConfig = {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: formData,
      };
    } else {
      fetchConfig = {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          note_text: noteText,
          human_codes: Array.isArray(humanCodes) ? humanCodes : [],
        }),
      };
    }

    fetch(url, fetchConfig).then(async (res) => {
      if (!res.ok) {
        const errBody = await res.json().catch(() => ({}));
        throw new Error(errBody?.detail || `Server error (HTTP ${res.status})`);
      }
      if (!res.body) throw new Error('No response body from server.');

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (!line.startsWith('data:')) continue;
          try {
            const msg = JSON.parse(line.slice(5).trim());
            if (msg.event === 'step_end') {
              setPipelineSteps(prev => {
                const idx = prev.findIndex(s => s.step === msg.data?.step);
                if (idx >= 0) {
                  const n = [...prev];
                  n[idx] = msg.data;
                  return n;
                }
                return [...prev, msg.data];
              });
            }
            if (msg.event === 'complete') {
              setAuditResult(msg.data ?? null);
              setIsRunning(false);
              setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 150);
            }
            if (msg.event === 'error') {
              setIsRunning(false);
              setAuditError('Pipeline error: ' + (msg.data ?? 'Unknown error'));
            }
          } catch {}
        }
      }
    }).catch(err => {
      setIsRunning(false);
      setAuditError('Connection error: ' + (err?.message ?? 'Unknown error'));
    });
  }, [noteText, file, humanCodes, setAuditResult, setPipelineSteps, setAuditError, setIsRunning]);

  const headerActions = (
    <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
      {caseData && (
        <span style={{ fontSize: '0.78rem', color: 'var(--clr-text-muted)', background: 'var(--clr-surface-2)', padding: '0.35rem 0.75rem', borderRadius: '6px', border: '1px solid var(--clr-border)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
          <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#f59e0b', display: 'inline-block' }} />
          Editing previous case #{caseData.id}
        </span>
      )}
      <button
        className="new-analysis-btn"
        onClick={() => {
          resetAudit();
          setNoteText('');
          setHumanCodes([]);
          setPipelineSteps([]);
          setFile(null);
          sessionStorage.removeItem("audit_state");
          window.history.replaceState({}, document.title);
        }}
        disabled={isRunning}
        aria-label="Start a new session"
      >
        New Session
      </button>
    </div>
  );

  return (
    <div className="dashboard-layout">
      <Sidebar />

      <main className="dashboard-main" id="main-content">
        <TopBar
          pageTitle="CodePerfect Audit"
          pageSubtitle="Clinical Coding Auditor"
          actions={headerActions}
        />

        <div className="dashboard-content">
          {isRunning && (
            <div className="pipeline-progress" role="status" aria-live="polite">
              {pipelineSteps.map(s => <StepBadge key={s.step} step={s} />)}
              {pipelineSteps.length === 0 && (
                <div className="pipeline-waiting">Processing pipeline</div>
              )}
            </div>
          )}

          {auditError && (
            <div className="error-banner" role="alert">
              {auditError}
              <button className="error-banner-retry" onClick={() => setAuditError('')}>
                Dismiss
              </button>
            </div>
          )}

          <div className="input-section">
            <UploadNote
              value={noteText}
              onChange={setNoteText}
              file={file}
              onFileSelected={setFile}
            />

            <CodeInput
              codes={humanCodes}
              onChange={setHumanCodes}
              noteText={noteText}
            />

            <button
              className={`run-btn ${isRunning ? 'running' : ''}`}
              onClick={handleRunAudit}
              disabled={isRunning || (!noteText.trim() && !file)}
              aria-busy={isRunning}
              aria-label={isRunning ? 'Processing note' : 'Process clinical note'}
            >
              {isRunning ? (
                <>
                  <span className="spinner" />
                  Processing note...
                </>
              ) : (
                'Process Note'
              )}
            </button>
          </div>

          {auditResult && (
            <div ref={resultsRef} className="fadein">
              <AuditResults result={auditResult} noteHash={auditResult.note_hash || ''} />
            </div>
          )}
        </div>
      </main>
    </div>
  );
}