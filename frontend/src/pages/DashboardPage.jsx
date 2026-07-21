import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { 
  PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, CartesianGrid
} from 'recharts';
import { getStats } from '../api/client';
import { CHART_COLORS, CATEGORY_LABELS, SEVERITY_LABELS } from '../utils/constants';
import './DashboardPage.css';

export default function DashboardPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const isGuest = user?.username === 'Guest User' || user?.id === 'guest';

  useEffect(() => {
    if (!isGuest) {
      fetchStats();
    } else {
      setLoading(false);
    }
  }, [isGuest]);

  async function fetchStats() {
    setLoading(true);
    setError(null);
    try {
      const data = await getStats();
      setStats(data);
    } catch (err) {
      setError(err.message || 'Failed to load dashboard data.');
    } finally {
      setLoading(false);
    }
  }

  const handleGitHubLogin = () => {
    window.location.href = `https://github.com/login/oauth/authorize?client_id=${import.meta.env.VITE_GITHUB_CLIENT_ID}&scope=read:user`;
  };

  if (isGuest) {
    return (
      <div className="page-container dashboard-page">
        <div className="dashboard-header">
          <h1>Dashboard</h1>
          <p>Insights into your code quality and issue trends.</p>
        </div>
        <div className="card empty-state fade-in">
          <h2>Log In to View Dashboard</h2>
          <p>Guest users do not generate aggregated statistics. Log in with GitHub to unlock your developer dashboard and track your code quality over time.</p>
          <button className="btn btn--primary" onClick={handleGitHubLogin} style={{ marginTop: '16px' }}>
            Log in with GitHub
          </button>
        </div>
      </div>
    );
  }

  if (loading && !stats) {
    return (
      <div className="page-container empty-state">
        <div className="spinner"></div>
      </div>
    );
  }

  // Format data for Recharts
  const categoryData = stats ? Object.entries(stats.category_breakdown || {}).map(([key, value]) => ({
    name: CATEGORY_LABELS[key] || key,
    value,
    color: CHART_COLORS[key] || '#8884d8'
  })) : [];

  const severityData = stats ? Object.entries(stats.severity_breakdown || {}).map(([key, value]) => ({
    name: SEVERITY_LABELS[key] || key,
    value,
    color: CHART_COLORS[key] || '#8884d8'
  })) : [];

  return (
    <div className="page-container dashboard-page">
      <div className="dashboard-header">
        <h1>Dashboard</h1>
        <p>Insights into your code quality and issue trends.</p>
      </div>

      {error && <div className="toast toast--error fade-in">{error}</div>}

      {stats && stats.total_reviews === 0 ? (
        <div className="card empty-state">
          <p>No data available to generate charts. Start by reviewing some code!</p>
        </div>
      ) : stats ? (
        <>
          <div className="stats-grid fade-up">
            <div className="card stat-card">
              <div className="stat-value">{stats.total_reviews}</div>
              <div className="stat-label">Total Reviews</div>
            </div>
            <div className="card stat-card">
              <div className="stat-value">{stats.average_issues_per_review.toFixed(1)}</div>
              <div className="stat-label">Avg. Issues per Review</div>
            </div>
            <div className="card stat-card">
              <div className="stat-value">{Object.values(stats.severity_breakdown || {}).reduce((a, b) => a + b, 0)}</div>
              <div className="stat-label">Total Issues Found</div>
            </div>
          </div>

          <div className="charts-grid fade-up">
            <div className="card chart-card">
              <h3>Issues by Category</h3>
              <div className="chart-container">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={categoryData}
                      cx="50%"
                      cy="50%"
                      innerRadius={60}
                      outerRadius={100}
                      paddingAngle={5}
                      dataKey="value"
                    >
                      {categoryData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.color} />
                      ))}
                    </Pie>
                    <Tooltip 
                      contentStyle={{ backgroundColor: '#181c23', borderColor: '#2a2f38', color: '#d4dae3', fontSize: 12 }}
                      itemStyle={{ color: '#d4dae3' }}
                    />
                    <Legend />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="card chart-card">
              <h3>Issues by Severity</h3>
              <div className="chart-container">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={severityData} margin={{ top: 20, right: 30, left: 0, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e232b" vertical={false} />
                    <XAxis dataKey="name" stroke="#545d68" tick={{fill: '#7d8590'}} />
                    <YAxis stroke="#545d68" tick={{fill: '#7d8590'}} allowDecimals={false} />
                    <Tooltip 
                      cursor={{fill: 'rgba(255,255,255,0.03)'}}
                      contentStyle={{ backgroundColor: '#181c23', borderColor: '#2a2f38', color: '#d4dae3', fontSize: 12 }}
                    />
                    <Bar dataKey="value" radius={[2, 2, 0, 0]}>
                      {severityData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.color} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
