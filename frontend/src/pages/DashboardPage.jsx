import { useEffect, useState } from 'react';
import { 
  PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, CartesianGrid
} from 'recharts';
import { getStats } from '../api/client';
import { CHART_COLORS, CATEGORY_LABELS, SEVERITY_LABELS } from '../utils/constants';
import './DashboardPage.css';

export default function DashboardPage() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchStats();
  }, []);

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
                      contentStyle={{ backgroundColor: '#161b22', borderColor: '#30363d', color: '#e6edf3' }}
                      itemStyle={{ color: '#e6edf3' }}
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
                    <CartesianGrid strokeDasharray="3 3" stroke="#30363d" vertical={false} />
                    <XAxis dataKey="name" stroke="#8b949e" tick={{fill: '#8b949e'}} />
                    <YAxis stroke="#8b949e" tick={{fill: '#8b949e'}} allowDecimals={false} />
                    <Tooltip 
                      cursor={{fill: 'rgba(255,255,255,0.05)'}}
                      contentStyle={{ backgroundColor: '#161b22', borderColor: '#30363d', color: '#e6edf3' }}
                    />
                    <Bar dataKey="value" radius={[4, 4, 0, 0]}>
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
