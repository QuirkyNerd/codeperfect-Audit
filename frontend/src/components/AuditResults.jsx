import React, { useState } from 'react';
import { auditApi } from '../services/api.js';
import './AuditResults.css';


function ConfidenceBar({ value }) {
  const pct  = Math.round(value * 100);
  const color = pct >= 85 ? '#10b981' : pct >= 65 ? '#f59e0b' : '#ef4444';
  return (
    <div className="conf-bar-wrap">
      <div className="conf-bar" style={{ width: `${pct}%`, background: color }} />
      <span style={{ color }}>{pct}%</span>
    </div>
  );
}

function CodeCard({ code, noteHash }) {
  const [feedback, setFeedback] = useState(null);   
  const [sending, setSending]   = useState(false);

  const sendFeedback = async (decision) => {
    if (feedback || sending) return;
    setSending(true);
    try {
      await auditApi.submitFeedback({ note_hash: noteHash, ai_code: code.code, decision });
      setFeedback(decision);
    } catch {
      alert('Failed to send feedback. Please try again.');
    } finally {
      setSending(false);
    }
  };

  const typeColor = code.type === 'ICD-10' ? '#6366f1' : code.type === 'CPT' ? '#10b981' : '#f59e0b';

  return (
    <div className={`code-card ${feedback ? `feedback-${feedback}` : ''}`}>
      <div className="code-card-top">
        <div className="code-main">
          <span className="code-code">{code.code}</span>
          <span className="code-type" style={{ background: `${typeColor}22`, color: typeColor, border: `1px solid ${typeColor}44` }}>
            {code.type}
          </span>
          {code.source && (
            <span className={`code-source ${code.source}`}>{code.source}</span>
          )}
        </div>
        <div className="feedback-btns">
          {feedback ? (
            <span className="feedback-done">{feedback === 'accepted' ? 'Accepted' : 'Rejected'}</span>
          ) : (
            <>
              <button className="fb-btn accept" onClick={() => sendFeedback('accepted')} disabled={sending} title="Accept this code">✓</button>
              <button className="fb-btn reject" onClick={() => sendFeedback('rejected')} disabled={sending} title="Reject this code">✕</button>
            </>
          )}
        </div>
      </div>

      <div className="code-desc">{code.description}</div>
      <ConfidenceBar value={code.confidence} />

      {code.rationale && (
        <div className="code-rationale">
          <span className="rationale-label">Clinical rationale</span>
          <p>{code.rationale}</p>
        </div>
      )}
    </div>
  );
}

function DiscrepancyCard({ disc }) {
  const TYPE_MAP = {
    missed_code:     { label: 'MISSED CODE',     cls: 'disc-missed',     tip: 'Code identified by audit but not submitted by the human coder. Potential revenue leakage.' },
    unsupported_code:{ label: 'UNSUPPORTED',      cls: 'disc-unsupported', tip: 'Code submitted by the human coder without sufficient clinical documentation support.' },
    correct_code:    { label: 'CORRECT',          cls: 'disc-correct',    tip: 'Code correctly submitted by the human coder and confirmed by audit.' },
    extra_code:      { label: 'EXTRA CODE',       cls: 'disc-extra',      tip: 'Code added by audit engine but not submitted by the human coder.' },
  };

  const meta = TYPE_MAP[disc.type] || { label: disc.type?.toUpperCase(), cls: '', tip: '' };

  return (
    <div className={`disc-card ${meta.cls}`}>
      <div className="disc-header">
        <span className="disc-code">{disc.code}</span>
        <span className={`disc-badge ${meta.cls}`}>{meta.label}</span>
        {disc.severity && <span className={`disc-sev sev-${disc.severity}`}>{disc.severity.toUpperCase()}</span>}
      </div>
      <p className="disc-msg">{disc.message}</p>
      {meta.tip && <p className="disc-tip">{meta.tip}</p>}
    </div>
  );
}


export default function AuditResults({ result, noteHash }) {
  const [activeTab, setActiveTab] = useState('explanation');

  if (!result) return null;

  const ai_codes             = Array.isArray(result.ai_codes)             ? result.ai_codes             : [];
  const low_confidence_codes = Array.isArray(result.low_confidence_codes) ? result.low_confidence_codes : [];
  const discrepancies        = Array.isArray(result.discrepancies)        ? result.discrepancies        : [];
  const evidence             = Array.isArray(result.evidence)             ? result.evidence             : [];
  const summary              = result.summary       || '';
  const pipeline_log         = Array.isArray(result.pipeline_log)        ? result.pipeline_log        : [];
  const tokens_used          = result.tokens_used   || 0;
  const explanation          = result.explanation   || '';

  const missedCount    = discrepancies.filter(d => d.type === 'missed_code').length;
  const unsupported    = discrepancies.filter(d => d.type === 'unsupported_code').length;
  const correctCount   = discrepancies.filter(d => d.type === 'correct_code').length;
  const totalCodes     = ai_codes.length;
  const avgConfidence  = totalCodes > 0 ? Math.round(ai_codes.reduce((s, c) => s + c.confidence, 0) / totalCodes * 100) : 0;

  const TABS = [
    { id: 'explanation', label: `Clinical Justification` },
    { id: 'codes',       label: `Final Code Set (${totalCodes})` },
    { id: 'discrepancies', label: `Coding Adjustments (${discrepancies.length})` },
    { id: 'evidence',    label: `Evidence (${evidence.length})` },
    { id: 'pipeline',    label: `Pipeline (${pipeline_log.length})` },
  ];

  return (
    <div className="audit-results fadein">
      <div className="audit-banner">
        <div className="banner-title">Audit Complete</div>
        <p className="banner-summary">{summary}</p>
        <div className="banner-metrics">
          <div className="metric">
            <span className="metric-val">{totalCodes}</span>
            <span className="metric-lbl">AI Codes</span>
          </div>
          <div className="metric">
            <span className="metric-val text-success">{correctCount}</span>
            <span className="metric-lbl">Correct</span>
          </div>
          <div className="metric">
            <span className="metric-val text-danger">{missedCount}</span>
            <span className="metric-lbl">Missed</span>
          </div>
          <div className="metric">
            <span className="metric-val text-warning">{unsupported}</span>
            <span className="metric-lbl">Unsupported</span>
          </div>
          <div className="metric">
            <span className="metric-val text-info">{avgConfidence}%</span>
            <span className="metric-lbl">Avg Confidence</span>
          </div>
        </div>
      </div>

      {missedCount > 0 && (
        <div className="missed-alert">
          <strong>{missedCount} code(s) were missed by the human coder.</strong> Review these to prevent revenue leakage.
        </div>
      )}

      <div className="audit-tabs">
        {TABS.map(t => (
          <button key={t.id} className={`audit-tab ${activeTab === t.id ? 'active' : ''}`} onClick={() => setActiveTab(t.id)}>
            {t.label}
          </button>
        ))}
      </div>

      <div className="tab-content">

        {activeTab === 'explanation' && (
          <div className="explanation-panel">
            <div className="explanation-header">
              <span>Clinical Coding Audit Explanation</span>
              <span className="explanation-badge">CDI Analysis</span>
            </div>
            {explanation ? (
              <div className="explanation-body">
                {explanation.split('\n').filter(Boolean).map((para, i) => (
                  <p key={i}>{para}</p>
                ))}
              </div>
            ) : (
              <p className="empty-state">Clinical explanation not available for this audit.</p>
            )}
          </div>
        )}

        {activeTab === 'codes' && (
          <div>
            {ai_codes.length === 0 && <p className="empty-state">No codes were generated. Try a more detailed clinical note.</p>}
            {ai_codes.map((c, i) => <CodeCard key={i} code={c} noteHash={noteHash} />)}
            {low_confidence_codes.length > 0 && (
              <>
                <div className="section-divider">Low Confidence Codes (below threshold)</div>
                {low_confidence_codes.map((c, i) => <CodeCard key={i} code={c} noteHash={noteHash} />)}
              </>
            )}
          </div>
        )}

        {activeTab === 'discrepancies' && (
          <div>
            {discrepancies.length === 0 && <p className="empty-state">No discrepancies found. All codes match.</p>}
            {discrepancies.map((d, i) => <DiscrepancyCard key={i} disc={d} />)}
          </div>
        )}

        {activeTab === 'evidence' && (
          <div>
            {evidence.length === 0 && <p className="empty-state">No evidence spans extracted.</p>}
            {evidence.map((ev, i) => (
              <div key={i} className="evidence-card">
                <div className="ev-code">{ev.code}</div>
                <blockquote className="ev-text">{ev.sentence_text}</blockquote>
                {ev.start_char != null && (
                  <span className="ev-span">Characters {ev.start_char}–{ev.end_char}</span>
                )}
              </div>
            ))}
          </div>
        )}

        {activeTab === 'pipeline' && (
          <div>
            {pipeline_log.map((step, i) => (
              <div key={i} className={`pipeline-step ${step.status}`}>
                <span className="pstep-icon">{step.status === 'success' ? '[OK]' : step.status === 'partial' ? '[PARTIAL]' : '[FAIL]'}</span>
                <span className="pstep-name">{step.label || step.step}</span>
                <span className="pstep-time">{step.duration_ms?.toFixed(0)}ms</span>
                {step.error && <span className="pstep-error">{step.error}</span>}
              </div>
            ))}
            {tokens_used > 0 && (
              <div className="tokens-info">
                Tokens used: <strong>{tokens_used.toLocaleString()}</strong>
                {' · '}Estimated cost: <strong>${(tokens_used * 0.075 / 1_000_000).toFixed(5)}</strong>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
