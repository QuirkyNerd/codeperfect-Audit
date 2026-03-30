import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../main.jsx';
import { useTheme } from '../main.jsx';
import { Sun, Moon, ChevronDown, ChevronUp, LogOut } from 'lucide-react';

const ROLE_LABELS = { ADMIN: 'Admin', CODER: 'Coder', REVIEWER: 'Reviewer' };

const AVATAR_COLORS = {
  ADMIN: 'linear-gradient(135deg, #ef4444, #dc2626)',
  CODER: 'linear-gradient(135deg, #6366f1, #4f46e5)',
  REVIEWER: 'linear-gradient(135deg, #10b981, #059669)',
};

export default function TopBar({ pageTitle, pageSubtitle, actions }) {
  const { user, logout } = useAuth();
  const { theme, cycleTheme } = useTheme();
  const navigate = useNavigate();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef(null);

  const handleLogout = useCallback(() => {
    logout();
    navigate('/login');
  }, [logout, navigate]);

  useEffect(() => {
    function handleClickOutside(e) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setDropdownOpen(false);
      }
    }
    if (dropdownOpen) document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [dropdownOpen]);

  useEffect(() => {
    function handleKey(e) {
      if (e.key === 'Escape') setDropdownOpen(false);
    }
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, []);

  const initials = (user?.name || 'U')
    .split(' ')
    .map(w => w[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);

  const role = user?.role || 'CODER';

  const ThemeIcon = theme === 'dark' ? Moon : Sun;

  return (
    <div className="topbar" role="banner">
      <div className="topbar-left">
        {pageTitle && <h1 className="main-title topbar-title">{pageTitle}</h1>}
        {pageSubtitle && <p className="topbar-subtitle">{pageSubtitle}</p>}
      </div>

      <div className="topbar-right">
        {actions && <div className="topbar-actions">{actions}</div>}

        <button
          className="theme-toggle"
          onClick={cycleTheme}
          aria-label="Toggle theme"
        >
          <ThemeIcon size={18} strokeWidth={1.8} />
        </button>

        <div className="user-dropdown-wrapper" ref={dropdownRef}>
          <button
            className="user-chip"
            onClick={() => setDropdownOpen(o => !o)}
            aria-haspopup="true"
            aria-expanded={dropdownOpen}
          >
            <div
              className="user-chip-avatar"
              style={{ background: AVATAR_COLORS[role] || AVATAR_COLORS.CODER }}
            >
              {initials}
            </div>

            <div className="user-chip-info">
              <span className="user-chip-name">{user?.name || 'User'}</span>
              <span className="role-badge">
                {ROLE_LABELS[role]}
              </span>
            </div>

            {dropdownOpen ? (
              <ChevronUp size={16} />
            ) : (
              <ChevronDown size={16} />
            )}
          </button>

          {dropdownOpen && (
            <div className="user-dropdown" role="menu">
              <div className="user-dropdown-header">
                <div className="user-dropdown-name">{user?.name}</div>
                <div className="user-dropdown-email">{user?.email}</div>
              </div>

              <div className="user-dropdown-divider" />

              <button
                className="user-dropdown-item"
                role="menuitem"
                onClick={() => {
                  setDropdownOpen(false);
                  handleLogout();
                }}
              >
                <LogOut size={16} />
                Sign Out
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}