import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getHistory } from '../api/client';
import { STATUS_CONFIG, LANGUAGES } from '../utils/constants';
import './HistoryPage.css';

export default function HistoryPage() {
  const [reviews, setReviews] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  // Pagination
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const perPage = 10;

  const navigate = useNavigate();

  useEffect(() => {
    fetchHistory();
  }, [page]);

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
