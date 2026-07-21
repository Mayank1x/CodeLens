/**
 * AdminPage — System-wide admin dashboard
 *
 * Fixed: Hooks are now called before any conditional returns (React rules).
 * Expanded: Now shows daily breakdown, issue categories, LLM health, guest/auth split.
 */

import { useState, useEffect } from 'react';
import { getAdminStats } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { Navigate } from 'react-router-dom';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import './AdminPage.css';

export default function AdminPage() {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const { user } = useAuth();

  const adminList = (import.meta.env.VITE_ADMIN_USERS || '').split(',');
  const isAdmin = user && adminList.includes(user.username);

  // All hooks MUST be called before any conditional returns
  useEffect(() => {
    if (!isAdmin) return;
    getAdminStats()
      .then((data) => {
        setStats(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, [isAdmin]);

  // Now it's safe to conditionally return
  if (!isAdmin) {
    return <Navigate to="/review" replace />;
  }

  if (loading) {
    return (
      <div className="admin-page">
        <div className="admin-page__loading">
          <div className="spinner" />
          <p>Loading system statistics...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="admin-page">
        <div className="toast toast--error">{error}</div>
      </div>
    );
  }

  const healthClass =
    stats.average_health_score >= 80
      ? 'health--good'
      : stats.average_health_score >= 50
      ? 'health--fair'
      : 'health--poor';

  const llm = stats.llm_health || {};
  const totalLlm = (llm.gemini_success || 0) + (llm.groq_fallback || 0) + (llm.llm_failure || 0);
  const totalUsage = stats.total_reviews || 1;
  const authPct = Math.round(((stats.auth_reviews || 0) / totalUsage) * 100);
  const guestPct = 100 - authPct;

  return (
    <div className="admin-page fade-in">
      <div className="admin-header">
        <h1>Admin Dashboard</h1>
        <p>System-wide usage statistics and health metrics.</p>
      </div>

      {/* --- Stat Cards --- */}
      <div className="admin-grid">
        <div className="stat-card">
          <div className="stat-card__title">Users</div>
          <div className="stat-card__value">{stats.total_users}</div>
        </div>
        <div className="stat-card">
          <div className="stat-card__title">Reviews</div>
          <div className="stat-card__value">{stats.total_reviews}</div>
        </div>
        <div className="stat-card">
          <div className="stat-card__title">Health Avg</div>
          <div className={`stat-card__value ${healthClass}`}>
            {stats.average_health_score}
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-card__title">LLM Calls</div>
          <div className="stat-card__value">{totalLlm}</div>
        </div>
      </div>

      {/* --- Reviews by Day --- */}
      {stats.reviews_by_day && stats.reviews_by_day.length > 0 && (
        <div className="admin-section">
          <h2>Reviews by Day (Last 30 Days)</h2>
          <div className="daily-chart">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={stats.reviews_by_day} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e232b" vertical={false} />
                <XAxis
                  dataKey="date"
                  stroke="#545d68"
                  tick={{ fill: '#7d8590', fontSize: 10 }}
                  tickFormatter={(val) => val ? val.slice(5) : ''}
                />
                <YAxis stroke="#545d68" tick={{ fill: '#7d8590', fontSize: 10 }} allowDecimals={false} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#181c23', borderColor: '#2a2f38', color: '#d4dae3', fontSize: 12 }}
                />
                <Bar dataKey="count" fill="#e2a039" radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* --- LLM Provider Health --- */}
      <div className="admin-section">
        <h2>LLM Provider Health</h2>
        {totalLlm === 0 ? (
          <p className="empty-text">No LLM calls recorded yet.</p>
        ) : (
          <div className="llm-health">
            <div className="llm-health__item">
              <div className="llm-health__label">Gemini OK</div>
              <div className="llm-health__value llm-health__value--success">
                {llm.gemini_success || 0}
              </div>
            </div>
            <div className="llm-health__item">
              <div className="llm-health__label">Groq Fallback</div>
              <div className="llm-health__value llm-health__value--fallback">
                {llm.groq_fallback || 0}
              </div>
            </div>
            <div className="llm-health__item">
              <div className="llm-health__label">LLM Failed</div>
              <div className="llm-health__value llm-health__value--failure">
                {llm.llm_failure || 0}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* --- Guest vs Authenticated --- */}
      <div className="admin-section">
        <h2>Guest vs Authenticated Usage</h2>
        <div className="usage-split">
          <div className="usage-split__bar">
            <div className="usage-split__auth" style={{ width: `${authPct}%` }} />
            <div className="usage-split__guest" style={{ width: `${guestPct}%` }} />
          </div>
          <div className="usage-split__labels">
            <span>Auth: {stats.auth_reviews || 0}</span>
            <span>Guest: {stats.guest_reviews || 0}</span>
          </div>
        </div>
      </div>

      {/* --- Top Issue Categories --- */}
      {stats.top_categories && Object.keys(stats.top_categories).length > 0 && (
        <div className="admin-section">
          <h2>Top Issue Categories</h2>
          <div className="category-grid">
            {Object.entries(stats.top_categories).map(([cat, count]) => (
              <div key={cat} className="category-item">
                <span className="category-item__name">{cat}</span>
                <span className="category-item__count">{count}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* --- Reviews by Language --- */}
      <div className="admin-section">
        <h2>Reviews by Language</h2>
        <div className="language-bars">
          {Object.entries(stats.reviews_by_language || {}).map(([lang, count]) => {
            const percentage = Math.max(5, (count / stats.total_reviews) * 100);
            return (
              <div key={lang} className="language-bar">
                <div className="language-bar__label">
                  <span className="lang-name">{lang}</span>
                  <span className="lang-count">{count}</span>
                </div>
                <div className="language-bar__track">
                  <div className="language-bar__fill" style={{ width: `${percentage}%` }} />
                </div>
              </div>
            );
          })}
          {Object.keys(stats.reviews_by_language || {}).length === 0 && (
            <p className="empty-text">No reviews processed yet.</p>
          )}
        </div>
      </div>
    </div>
  );
}
