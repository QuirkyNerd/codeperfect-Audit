import React from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../main.jsx';
import '../styles/sidebar.css';

const NAV_ITEMS_BY_ROLE = {
  ADMIN:    [
    { to: '/',          icon: '', label: 'Coding' },
    { to: '/cases',     icon: '', label: 'Case History' },
    { to: '/analytics', icon: '', label: 'Analytics' },
    { to: '/users',     icon: '', label: 'Users' },
  ],
  CODER:    [
    { to: '/',      icon: '', label: 'Coding' },
    { to: '/cases', icon: '', label: 'Case History' },
  ],
  REVIEWER: [
    { to: '/cases',     icon: '', label: 'Case History' },
    { to: '/analytics', icon: '', label: 'Coding' },
  ],
};

export default function Sidebar() {
  const { user } = useAuth();
  const role = user?.role || 'CODER';
  const navItems = NAV_ITEMS_BY_ROLE[role] || NAV_ITEMS_BY_ROLE.CODER;

  return (
    <aside className="sidebar" role="navigation" aria-label="Main navigation">
      <div className="sidebar-brand">
        <span className="brand-icon" aria-hidden="true">⚕️</span>
        <div>
          <div className="brand-name">CodePerfect Audit</div>
          <div className="brand-sub">Clinical Coding Auditor</div>
        </div>
      </div>
      
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
            aria-current={({ isActive }) => isActive ? 'page' : undefined}
          >
            <span className="nav-icon" aria-hidden="true">{item.icon}</span>
            <span>{item.label}</span>
          </NavLink>
        ))}
    </aside>
  );
}