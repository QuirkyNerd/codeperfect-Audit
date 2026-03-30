import React, { createContext, useContext, useState, useEffect, useCallback, Component } from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route, Navigate, useNavigate } from 'react-router-dom';
import LoginPage from './pages/LoginPage.jsx';
import Dashboard from './pages/Dashboard.jsx';
import CaseHistoryPage from './pages/CaseHistoryPage.jsx';
import AnalyticsPage from './pages/AnalyticsPage.jsx';
import UsersPage from './pages/UsersPage.jsx';
import './styles/index.css';

class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    console.error('[ErrorBoundary] Uncaught render error:', error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          display: 'flex', flexDirection: 'column', alignItems: 'center',
          justifyContent: 'center', minHeight: '100vh',
          background: 'var(--clr-bg)', color: 'var(--clr-text-primary)',
          fontFamily: 'inherit', gap: '1rem', padding: '2rem',
        }}>
          <div style={{ fontSize: '2.5rem' }}>⚕️</div>
          <h2 style={{ margin: 0, color: 'var(--clr-danger)' }}>Application Error</h2>
          <p style={{ color: 'var(--clr-text-muted)', margin: 0, maxWidth: '420px', textAlign: 'center', lineHeight: 1.7 }}>
            {this.state.error?.message || 'An unexpected error occurred. Please try refreshing the page.'}
          </p>
          <button
            onClick={() => { 
              this.setState({ hasError: false, error: null }); 
              if (this.props.navigate) {
                this.props.navigate('/login', { replace: true });
              } else {
                window.location.href = '/login'; 
              }
            }}
            style={{
              marginTop: '0.5rem', padding: '0.65rem 1.8rem',
              background: 'var(--clr-primary)', border: 'none', borderRadius: '10px',
              color: '#fff', cursor: 'pointer', fontSize: '0.9rem', fontWeight: 600,
              fontFamily: 'inherit',
            }}
          >
            Return to Login
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export const ThemeContext = createContext(null);
export function useTheme() { return useContext(ThemeContext); }

function applyTheme(theme) {
  const root = document.documentElement;
  root.setAttribute('data-theme', theme);
}

function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(() => {
    const stored = sessionStorage.getItem('theme');
    return (stored === 'light' || stored === 'dark') ? stored : 'dark';
  });

  useEffect(() => {
    applyTheme(theme);
    sessionStorage.setItem('theme', theme);
  }, [theme]);



  const cycleTheme = useCallback(() => {
    setTheme(prev => {
      const next = prev === 'dark' ? 'light' : 'dark';
      return next;
    });
  }, []);

  return (
    <ThemeContext.Provider value={{ theme, setTheme, cycleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export const AuthContext = createContext(null);
export function useAuth() { return useContext(AuthContext); }

function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try { return JSON.parse(sessionStorage.getItem('user')); } catch { return null; }
  });
  const [token, setToken] = useState(() => sessionStorage.getItem('access_token'));

  const login = useCallback((userData, newToken) => {
    sessionStorage.setItem('access_token', newToken);
    sessionStorage.setItem('user', JSON.stringify(userData));
    setUser(userData);
    setToken(newToken);
  }, []);

  const logout = useCallback(() => {
    sessionStorage.removeItem('access_token');
    sessionStorage.removeItem('user');
    sessionStorage.clear();
    setUser(null);
    setToken(null);
  }, []);

  const value = {
    user,
    token,
    login,
    logout,
    isAdmin: user?.role === 'ADMIN',
    isCoder: user?.role === 'CODER',
    isReviewer: user?.role === 'REVIEWER',
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

export const AuditContext = createContext(null);
export function useAudit() { return useContext(AuditContext); }

function AuditProvider({ children }) {
  const [noteText,      setNoteText]      = useState('');
  const [humanCodes,    setHumanCodes]    = useState([]);
  const [auditResult,   setAuditResult]   = useState(null);
  const [pipelineSteps, setPipelineSteps] = useState([]);
  const [isRunning,     setIsRunning]     = useState(false);
  const [auditError,    setAuditError]    = useState('');
  const [file,          setFile]          = useState(null);

  const resetAudit = useCallback(() => {
    setAuditResult(null);
    setPipelineSteps([]);
    setAuditError('');
    setNoteText('');
    setHumanCodes([]);
    setFile(null);
  }, []);

  const value = {
    noteText, setNoteText,
    humanCodes, setHumanCodes,
    auditResult, setAuditResult,
    pipelineSteps, setPipelineSteps,
    isRunning, setIsRunning,
    auditError, setAuditError,
    file, setFile,
    resetAudit,
  };

  return (
    <AuditContext.Provider value={value}>
      {children}
    </AuditContext.Provider>
  );
}

export const ROLE_HOME = {
  ADMIN:    '/',
  CODER:    '/',
  REVIEWER: '/cases',
};

function ProtectedRoute({ children }) {
  const { token } = useAuth();
  if (!token) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

function RoleRoute({ allowed, children }) {
  const { user, token } = useAuth();
  if (!token || !user) return <Navigate to="/login" replace />;
  if (!allowed.includes(user.role)) {
    return <Navigate to={ROLE_HOME[user.role] || '/login'} replace />;
  }
  return children;
}

function AppInner() {
  const navigate = useNavigate();
  return (
    <ErrorBoundary navigate={navigate}>
      <ThemeProvider>
        <AuthProvider>
          <AuditProvider>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route path="/" element={
                <ProtectedRoute>
                  <RoleRoute allowed={['ADMIN', 'CODER']}>
                    <Dashboard />
                  </RoleRoute>
                </ProtectedRoute>
              } />

              <Route path="/cases" element={
                <ProtectedRoute>
                  <RoleRoute allowed={['ADMIN', 'CODER', 'REVIEWER']}>
                    <CaseHistoryPage />
                  </RoleRoute>
                </ProtectedRoute>
              } />

              <Route path="/analytics" element={
                <ProtectedRoute>
                  <RoleRoute allowed={['ADMIN', 'REVIEWER']}>
                    <AnalyticsPage />
                  </RoleRoute>
                </ProtectedRoute>
              } />

              <Route path="/users" element={
                <ProtectedRoute>
                  <RoleRoute allowed={['ADMIN']}>
                    <UsersPage />
                  </RoleRoute>
                </ProtectedRoute>
              } />

              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </AuditProvider>
        </AuthProvider>
      </ThemeProvider>
    </ErrorBoundary>
  );
}

function App() {
  return (
    <BrowserRouter>
      <AppInner />
    </BrowserRouter>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
