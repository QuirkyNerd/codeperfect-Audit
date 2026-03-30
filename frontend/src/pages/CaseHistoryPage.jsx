import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import Sidebar from '../components/Sidebar.jsx';
import TopBar from '../components/TopBar.jsx';
import { caseApi } from '../services/api.js';
import { useAuth } from '../main.jsx';
import { generatePdf } from '../utils/generatePdfReport.js';
import { Download } from 'lucide-react';
import '../styles/dashboard.css';

const STATUS_COLORS = {
  pending:  '#f59e0b',
  reviewed: '#6366f1',
  approved: '#10b981',
  rejected: '#ef4444',
};

function StatusSelect({ caseId, currentStatus, onUpdate }) {
  const [busy, setBusy] = useState(false);
  const handleChange = async (e) => {
    const newStatus = e.target.value;
    if (newStatus === currentStatus) return;
    setBusy(true);
    await onUpdate(caseId, newStatus);
    setBusy(false);
  };
  return (
    <select
      className="status-select"
      value={currentStatus}
      onChange={handleChange}
      disabled={busy}
      aria-label={`Change case ${caseId} status`}
    >
      <option value="pending">Pending</option>
      <option value="reviewed">Reviewed</option>
      <option value="approved">Approved</option>
      <option value="rejected">Rejected</option>
    </select>
  );
}

export default function CaseHistoryPage() {
  const { user } = useAuth();
  const isReviewer = user?.role === 'REVIEWER';
  const navigate = useNavigate();

  const [cases,   setCases]   = useState([]);
  const [total,   setTotal]   = useState(0);
  const [page,    setPage]    = useState(1);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState('');
  const [selected, setSelected] = useState(null);

  const [status,  setStatus]  = useState('');
  const [minRisk, setMinRisk] = useState('');
  const [fromDate, setFrom]   = useState('');
  const [toDate,  setTo]      = useState('');

  const pageSize = 15;

  const fetchCases = useCallback(async () => {
    setLoading(true);
    setError('');
    setCases([]);
    try {
      const params = { page, page_size: pageSize };
      if (status)  params.status   = status;
      if (minRisk) params.min_risk = Number(minRisk);
      if (fromDate) params.from_date = fromDate;
      if (toDate)   params.to_date   = toDate;
      const res = await caseApi.list(params);
      // Debug: log backend response shape
      console.warn('[CaseHistory] API response:', res.status, res.data);
      setCases(Array.isArray(res.data?.cases) ? res.data.cases : []);
      setTotal(res.data?.total || 0);
    } catch (e) {
      const status_code = e.response?.status;
      console.warn('[CaseHistory] API error:', status_code, e.message);
      if (status_code === 401) {
        setError('Session expired or unauthorised. Please log in again.');
      } else if (status_code === 403) {
        setError('Access denied. You do not have permission to view cases.');
      } else if (status_code >= 500) {
        setError('The case history service is temporarily unavailable. Please try again shortly.');
      } else {
        setError(e.response?.data?.detail || 'Unable to load cases. Please check your network and try again.');
      }
    } finally {
      setLoading(false);
    }
  }, [page, status, minRisk, fromDate, toDate]);

  useEffect(() => { fetchCases(); }, [fetchCases]);

  const handleStatusChange = useCallback(async (caseId, newStatus) => {
    const comment = (newStatus === 'approved' || newStatus === 'rejected')
      ? (window.prompt(`Enter reviewer comment for "${newStatus}":`) || '')
      : '';
    try {
      await caseApi.update(caseId, { status: newStatus, comment });
      fetchCases();
    } catch (e) {
      alert('Failed to update status: ' + (e.response?.data?.detail || e.message));
    }
  }, [fetchCases]);

  const clearFilters = useCallback(() => {
    setStatus(''); setMinRisk(''); setFrom(''); setTo(''); setPage(1);
  }, []);

  const totalPages = Math.ceil(total / pageSize);

  const headerActions = (
    <button className="new-analysis-btn" onClick={fetchCases} disabled={loading} aria-label="Refresh case list">
      ↻ Refresh
    </button>
  );

  const renderContent = () => {
    if (loading) {
      return (
        <div className="loading-center" role="status" aria-live="polite">
          <div className="big-spinner" aria-hidden="true" />
          Loading cases…
        </div>
      );
    }

    if (error) {
      return (
        <div className="error-banner" role="alert">
          <span aria-hidden="true">⚠</span>
          <div style={{ flex: 1 }}>
            <strong>Failed to load cases</strong>
            <p style={{ margin: '0.25rem 0 0', fontSize: '0.8rem', opacity: 0.85 }}>{error}</p>
          </div>
          <button className="error-banner-retry" onClick={fetchCases} aria-label="Retry loading cases">
            Retry
          </button>
        </div>
      );
    }

    if (cases.length === 0) {
      return (
        <div className="empty-state-card" role="status">
          <div className="empty-state-icon" aria-hidden="true" style={{ fontSize: '2rem', lineHeight: 1 }}>--</div>
          <div className="empty-state-title">No cases available</div>
          <p className="empty-state-desc">
            {status || minRisk || fromDate || toDate
              ? 'No cases match the current filters. Try adjusting or clearing the filters.'
              : 'No audit cases have been submitted yet. Run an analysis from the Analyse tab to create your first case.'}
          </p>
          {(status || minRisk || fromDate || toDate) && (
            <button className="new-analysis-btn" onClick={clearFilters} style={{ marginTop: '0.5rem' }}>
              Clear Filters
            </button>
          )}
        </div>
      );
    }

    return (
      <>
        <div className="cases-table-wrapper">
          <table className="cases-table" aria-label="Case history table">
            <thead>
              <tr>
                <th scope="col">#</th>
                <th scope="col">Date</th>
                <th scope="col">Summary</th>
                <th scope="col">AI Codes</th>
                <th scope="col">Risk</th>
                <th scope="col">Revenue</th>
                <th scope="col">Accuracy</th>
                <th scope="col">Status</th>
                {isReviewer && <th scope="col">Update</th>}
                <th scope="col">Report</th>
              </tr>
            </thead>
            <tbody>
              {cases.map((c, index) => (
                <tr
                  key={c.id}
                  onClick={() => setSelected(c)}
                  className="case-row"
                  tabIndex={0}
                  onKeyDown={e => e.key === 'Enter' && setSelected(c)}
                  aria-label={`Case ${c.id}: ${c.summary || 'No summary'}`}
                >
                  <td>{(page - 1) * pageSize + index + 1}</td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    {c.created_at ? new Date(c.created_at).toLocaleDateString() : '—'}
                  </td>
                  <td className="case-summary">{c.summary || '—'}</td>
                  <td style={{ fontFamily: 'monospace', fontSize: '0.78rem' }}>
                    {(c.ai_codes || []).map(x => x.code).join(', ') || '—'}
                  </td>
                  <td>
                    <span className={`risk-badge ${c.risk_score >= 70 ? 'high' : c.risk_score >= 40 ? 'medium' : 'low'}`}>
                      {c.risk_score?.toFixed(0) ?? '0'}
                    </span>
                  </td>
                  <td>${(c.revenue_impact || 0).toFixed(0)}</td>
                  <td>{c.coding_accuracy?.toFixed(1) ?? '—'}%</td>
                  <td>
                    <span
                      className="status-badge"
                      style={{ background: STATUS_COLORS[c.status] || '#64748b' }}
                    >
                      {c.status}
                    </span>
                  </td>
                  {isReviewer && (
                    <td onClick={e => e.stopPropagation()}>
                      <StatusSelect
                        caseId={c.id}
                        currentStatus={c.status}
                        onUpdate={handleStatusChange}
                      />
                    </td>
                  )}
                  <td onClick={e => e.stopPropagation()}>
                    <button
                      className="download-report-btn"
                      title="Download Report"
                      aria-label={`Download PDF report for case ${c.id}`}
                      onClick={() => generatePdf(c)}
                    >
                      <Download size={18} strokeWidth={2} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {totalPages > 1 && (
          <nav className="pagination" aria-label="Case list pagination">
            <button disabled={page <= 1} onClick={() => setPage(p => p - 1)} aria-label="Previous page">← Prev</button>
            <span aria-current="page">Page {page} of {totalPages}</span>
            <button disabled={page >= totalPages} onClick={() => setPage(p => p + 1)} aria-label="Next page">Next →</button>
          </nav>
        )}
      </>
    );
  };

  return (
    <div className="dashboard-layout">
      <Sidebar />

      <main className="dashboard-main" id="main-content">
        <TopBar
          pageTitle="Case History"
          pageSubtitle={!loading && !error && `${total} case${total !== 1 ? 's' : ''} found`}
          actions={headerActions}
        />

        <div className="dashboard-content">
          {/* Filter bar */}
          <div className="filter-bar" role="group" aria-label="Case filters">
            {['', 'pending', 'reviewed', 'approved', 'rejected'].map(s => (
              <button
                key={s || 'all'}
                style={{
                  padding: '0.45rem 1rem', borderRadius: '6px', cursor: 'pointer',
                  border: status === s ? '2px solid #6366f1' : '1px solid var(--clr-border)',
                  background: status === s ? '#6366f1' : 'transparent',
                  color: status === s ? '#fff' : 'var(--clr-text-secondary)',
                  fontSize: '0.8rem', fontFamily: 'inherit', fontWeight: status === s ? 600 : 400,
                  transition: 'all 0.15s',
                }}
                onClick={() => { setStatus(s); setPage(1); }}
                aria-pressed={status === s}
              >
                {s ? s.charAt(0).toUpperCase() + s.slice(1) : 'All'}
              </button>
            ))}
            <input
              type="number" placeholder="Min risk %" value={minRisk} min="0" max="100"
              aria-label="Minimum risk score filter"
              style={{ width: '110px', padding: '0.45rem 0.75rem', borderRadius: '6px', border: '1px solid var(--clr-border)', background: 'var(--clr-surface)', color: 'var(--clr-text-primary)', fontFamily: 'inherit' }}
              onChange={e => { setMinRisk(e.target.value); setPage(1); }}
            />
            <input type="date" value={fromDate} aria-label="From date filter"
              style={{ padding: '0.45rem 0.75rem', borderRadius: '6px', border: '1px solid var(--clr-border)', background: 'var(--clr-surface)', color: 'var(--clr-text-primary)', fontFamily: 'inherit' }}
              onChange={e => { setFrom(e.target.value); setPage(1); }}
            />
            <input type="date" value={toDate} aria-label="To date filter"
              style={{ padding: '0.45rem 0.75rem', borderRadius: '6px', border: '1px solid var(--clr-border)', background: 'var(--clr-surface)', color: 'var(--clr-text-primary)', fontFamily: 'inherit' }}
              onChange={e => { setTo(e.target.value); setPage(1); }}
            />
            {(status || minRisk || fromDate || toDate) && (
              <button className="new-analysis-btn" style={{ background: 'rgba(100,116,139,0.2)', fontSize: '0.78rem', padding: '0.45rem 0.85rem' }} onClick={clearFilters}>
                ✕ Clear
              </button>
            )}
          </div>

          {renderContent()}
        </div>
      </main>

      {selected && (
        <div className="drawer-overlay" onClick={() => setSelected(null)} role="dialog" aria-modal="true" aria-label={`Case ${selected.id} details`}>
          <div className="drawer" onClick={e => e.stopPropagation()}>
            <div className="drawer-header">
              <h3>Case #{selected.id}</h3>
              <button onClick={() => setSelected(null)} aria-label="Close case detail">✕</button>
            </div>
            <div className="drawer-body">
              <p><strong>Summary:</strong> {selected.summary || '—'}</p>
              <p><strong>Input Note:</strong> {selected.input_text ? selected.input_text.slice(0, 300) + (selected.input_text.length > 300 ? '…' : '') : '—'}</p>
              <p><strong>AI Codes:</strong> {(selected.ai_codes || []).map(c => `${c.code} (${(c.confidence * 100).toFixed(0)}%)`).join(', ') || '—'}</p>
              <p><strong>Human Codes:</strong> {(selected.human_codes || []).join(', ') || '—'}</p>
              <p><strong>Risk Score:</strong> {selected.risk_score?.toFixed(1) ?? '—'}</p>
              <p><strong>Est. Revenue Impact:</strong> ${(selected.revenue_impact || 0).toFixed(0)}</p>
              <p><strong>Coding Accuracy:</strong> {selected.coding_accuracy?.toFixed(1) ?? '—'}%</p>
              <p><strong>Processing Time:</strong> {selected.processing_time?.toFixed(2) ?? '—'}s</p>
              {selected.reviewer_comment && (
                <div style={{ marginTop: '0.75rem', padding: '0.9rem', background: 'var(--clr-surface-2)', borderRadius: '8px', borderLeft: '3px solid #6366f1' }}>
                  <p style={{ color: 'var(--clr-text-muted)', marginBottom: '0.25rem', fontSize: '0.75rem' }}>
                    Reviewer Comment {selected.reviewed_at ? `(${new Date(selected.reviewed_at).toLocaleDateString()})` : ''}
                  </p>
                  <p style={{ color: 'var(--clr-text-primary)' }}>{selected.reviewer_comment}</p>
                </div>
              )}
              
              <button
                className="new-analysis-btn"
                style={{ marginTop: 'auto', alignSelf: 'flex-start' }}
                onClick={() => navigate('/', { state: { caseData: selected } })}
              >
                Re-open in editor
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
