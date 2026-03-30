import React, { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../main.jsx';
import { ROLE_HOME } from '../main.jsx';
import { authApi } from '../services/api.js';
import { Eye, EyeOff } from 'lucide-react';
import '../styles/auth.css';

export default function LoginPage() {
  const [form, setForm] = useState({ email: '', password: '' });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const { login, token } = useAuth();
  const navigate = useNavigate();

  React.useEffect(() => {
    if (token) {
      navigate("/", { replace: true });
    }
  }, [token, navigate]);

  const handleChange = useCallback((e) => {
    setForm((f) => ({ ...f, [e.target.name]: e.target.value }));
    if (error) setError('');
  }, [error]);

  const performLogin = async (emailToUse, passwordToUse) => {
    if (!emailToUse || !passwordToUse) {
      setError('Please enter your email and password.');
      return;
    }

    setLoading(true);
    setError('');

    try {
      const res = await authApi.login({
        email: emailToUse,
        password: passwordToUse,
      });

      login(res.data.user, res.data.access_token);
      navigate(ROLE_HOME[res.data.user.role] || '/', { replace: true });
    } catch (err) {
      const msg =
        err.response?.data?.detail ||
        'Authentication failed. Please check your credentials.';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    await performLogin(form.email, form.password);
  };

  const handleDemoLogin = async (e) => {
    e.preventDefault();
    const demoEmail = 'admin@gmail.com';
    const demoPassword = 'admin2481';
    setForm({ email: demoEmail, password: demoPassword });
    await performLogin(demoEmail, demoPassword);
  };

  return (
    <div className="auth-bg">
  <div className="auth-card">
    <div className="auth-header">
      <h1 className="auth-title">CodePerfect Audit</h1>
      <p className="auth-tagline">Clinical Coding Auditor</p>
      <p className="auth-subtitle">Sign in to your account</p>
    </div>

    {error && (
      <div className="auth-error" role="alert">
        {error}
      </div>
    )}

        <form onSubmit={handleSubmit} className="auth-form" noValidate>
          <div className="form-group">
            <label htmlFor="auth-email">Email Address</label>
            <input
              id="auth-email"
              name="email"
              type="email"
              value={form.email}
              onChange={handleChange}
              autoComplete="email"
              disabled={loading}
              required
            />
          </div>

          <div className="form-group">
            <label htmlFor="auth-password">Password</label>

            <div className="password-input-wrapper">
              <input
                id="auth-password"
                name="password"
                type={showPassword ? 'text' : 'password'}
                value={form.password}
                onChange={handleChange}
                autoComplete="current-password"
                disabled={loading}
                required
              />

              <button
                type="button"
                className="pw-toggle-btn"
                onClick={() => setShowPassword((v) => !v)}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
              >
                {showPassword ? (
                  <EyeOff size={18} strokeWidth={1.8} />
                ) : (
                  <Eye size={18} strokeWidth={1.8} />
                )}
              </button>
            </div>
          </div>

          <button
            type="submit"
            className="auth-submit"
            disabled={loading}
          >
            {loading ? (
              <>
                <span className="spinner" />
                Authenticating...
              </>
            ) : (
              'Sign In'
            )}
          </button>

          <div className="auth-divider">
            <span>or continue with demo access</span>
          </div>

          <button
            type="button"
            className="auth-submit demo-btn"
            onClick={handleDemoLogin}
            disabled={loading}
          >
            Use Demo Account
          </button>
        </form>

        <p className="auth-note">
          Demo credentials are provided in the project README.<br />
          Access is provided by your system administrator.
        </p>
      </div>
    </div>
  );
}