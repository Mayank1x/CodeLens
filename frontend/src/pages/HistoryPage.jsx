import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { getHistory } from '../api/client';
import { STATUS_CONFIG, LANGUAGES } from '../utils/constants';
import './HistoryPage.css';

export default function HistoryPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  
  const [reviews, setReviews] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  // Pagination
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const perPage = 10;

  const isGuest = user?.username === 'Guest User' || user?.id === 'guest';

  useEffect(() => {
    if (!isGuest) {
      fetchHistory();
    } else {
      setLoading(false);
    }
  }, [page, isGuest]);

  async function fetchHistory() {
    setLoading(true);
    setError(null);
    try {
      const data = await getHistory(page, perPage);
      setReviews(data.reviews || []);
      setTotalPages(data.pages || 1);
    } catch (err) {
      setError(err.message || 'Failed to load history.');
    } finally {
      setLoading(false);
    }
  }

  function handleRowClick(reviewId) {
    navigate(`/review?id=${reviewId}`);
  }

  function getLanguageLabel(val) {
    const lang = LANGUAGES.find((l) => l.value === val);
    return lang ? lang.label : val;
  }

  function formatDate(isoString) {
    const d = new Date(isoString);
    return new Intl.DateTimeFormat('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    }).format(d);
  }

  const handleGitHubLogin = () => {
    window.location.href = `https://github.com/login/oauth/authorize?client_id=${import.meta.env.VITE_GITHUB_CLIENT_ID}&scope=read:user`;
  };

  if (isGuest) {
    return (
      <div className="page-container history-page">
        <div className="history-header">
          <h1>Review History</h1>
          <p>A complete log of your past code reviews.</p>
        </div>
        <div className="card empty-state fade-in">
          <h2>Log In to Track History</h2>
          <p>Guest users cannot save code reviews. Log in with GitHub to view your permanent review history and track your improvements over time.</p>
          <button className="btn btn--primary" onClick={handleGitHubLogin} style={{ marginTop: '16px' }}>
            Log in with GitHub
          </button>
        </div>
      </div>
    );
  }

  if (loading && reviews.length === 0) {
    return (
      <div className="page-container empty-state">
        <div className="spinner"></div>
      </div>
    );
  }

  return (
    <div className="page-container history-page">
      <div className="history-header">
        <h1>Review History</h1>
        <p>A complete log of your past code reviews.</p>
      </div>

      {error && <div className="toast toast--error fade-in">{error}</div>}

      {reviews.length === 0 && !error ? (
        <div className="card empty-state">
          <p>You haven't submitted any code for review yet.</p>
          <button className="btn btn--primary" onClick={() => navigate('/review')}>
            Create your first review
          </button>
        </div>
      ) : (
        <>
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Language</th>
                  <th>Status</th>
                  <th>Issues Found</th>
                </tr>
              </thead>
              <tbody>
                {reviews.map((rev) => {
                  const statusConfig = STATUS_CONFIG[rev.status] || { label: rev.status, badgeClass: 'badge--info' };
                  
                  return (
                    <tr 
                      key={rev.id} 
                      className="history-table-row"
                      onClick={() => handleRowClick(rev.id)}
                    >
                      <td>{formatDate(rev.created_at)}</td>
                      <td>{getLanguageLabel(rev.language)}</td>
                      <td>
                        <span className={`badge ${statusConfig.badgeClass}`}>
                          {statusConfig.label}
                        </span>
                      </td>
                      <td>
                        {rev.status === 'complete' 
                          ? <strong>{rev.issue_count}</strong> 
                          : '-'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="pagination">
              <button 
                className="btn btn--ghost" 
                disabled={page === 1}
                onClick={() => setPage(p => p - 1)}
              >
                Previous
              </button>
              <span>Page {page} of {totalPages}</span>
              <button 
                className="btn btn--ghost" 
                disabled={page === totalPages}
                onClick={() => setPage(p => p + 1)}
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
