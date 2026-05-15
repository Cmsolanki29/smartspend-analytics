import React from "react";
import { Moon, Sun } from "lucide-react";
import { apiUtils } from "../../services/api";

const monthNames = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

const formatIncomeBadge = (income) => {
  const value = Number(income || 0);
  if (value >= 100000) return apiUtils.formatINR(value).replace(".00", "");
  return apiUtils.formatINR(value).replace(".00", "");
};

const Navbar = ({
  users,
  selectedUserId,
  onUserChange,
  activeTab,
  setActiveTab,
  month,
  year,
  onMonthChange,
  onYearChange,
  darkMode,
  onToggleTheme,
  userLabel,
  onLogout,
}) => {
  const tabs = [
    { id: "dashboard", label: "Dashboard", icon: "🏠" },
    { id: "emi", label: "EMI Tracker", icon: "💳" },
    { id: "subscriptions", label: "Subscriptions", icon: "🗑️" },
    { id: "dark-patterns", label: "Dark Patterns", icon: "🔍" },
    { id: "fraud", label: "Fraud Shield", icon: "🛡️" },
    { id: "purchase", label: "Purchase Planner", icon: "🛵" },
    { id: "festival", label: "Festival Planner", icon: "🪔" },
    { id: "settings", label: "Settings", icon: "⚙️" },
  ];

  return (
    <header className="navbar glass-card">
      <div className="brand-wrap">
        <div className="brand-logo">SS</div>
        <div>
          <h1 className="brand-title">SmartSpend Analytics</h1>
          <p className="brand-subtitle">AI-driven financial intelligence</p>
        </div>
      </div>

      <div>
        <div className="nav-tabs">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              className={activeTab === tab.id ? "tab-active" : "tab-inactive"}
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.icon} {tab.label}
            </button>
          ))}
        </div>
        <div className="user-switcher">
          {users.map((user) => (
            <button
              key={user.id}
              type="button"
              className={`user-pill ${selectedUserId === user.id ? "active" : ""}`}
              onClick={() => onUserChange(user.id)}
            >
              <span className="avatar">{user.name?.[0]?.toUpperCase() || "U"}</span>
              <span>{user.name}</span>
              <span className="income-badge">{formatIncomeBadge(user.monthly_income)}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="nav-controls">
        {userLabel ? (
          <span className="auth-user-label" title={userLabel}>
            {userLabel}
          </span>
        ) : null}
        {onLogout ? (
          <button type="button" className="btn-outline btn-small" onClick={onLogout}>
            Log out
          </button>
        ) : null}
        <select value={month} onChange={(e) => onMonthChange(Number(e.target.value))}>
          {monthNames.map((label, idx) => (
            <option key={label} value={idx + 1}>
              {label}
            </option>
          ))}
        </select>

        <select value={year} onChange={(e) => onYearChange(Number(e.target.value))}>
          {[2025, 2026].map((y) => (
            <option key={y} value={y}>
              {y}
            </option>
          ))}
        </select>

        <button type="button" className="theme-btn" onClick={onToggleTheme} aria-label="Toggle theme">
          {darkMode ? <Sun size={18} /> : <Moon size={18} />}
        </button>
      </div>
    </header>
  );
};

export default Navbar;
