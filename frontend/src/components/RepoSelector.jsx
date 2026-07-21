/**
 * RepoSelector — Searchable list of user's GitHub repositories.
 *
 * Fetches repos from GET /api/github/repos and displays them
 * in a scrollable list with search, pagination, and metadata
 * (visibility, language, stars, last updated).
 */

import { useState, useEffect, useCallback } from 'react';
import { getGithubRepos } from '../api/client';

export default function RepoSelector({ onSelectRepo }) {
  const [repos, setRepos] = useState([]);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [hasNext, setHasNext] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedRepo, setSelectedRepo] = useState(null);

  // Debounced search
  const [debouncedSearch, setDebouncedSearch] = useState('');

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    setPage(1); // Reset page when search changes
  }, [debouncedSearch]);

  useEffect(() => {
    fetchRepos();
  }, [page, debouncedSearch]);

  async function fetchRepos() {
    setLoading(true);
    setError(null);
    try {
      const data = await getGithubRepos(page, 20, debouncedSearch);
      setRepos(data.repos || []);
      setHasNext(data.has_next || false);
    } catch (err) {
      setError(err.message || 'Failed to load repositories.');
    } finally {
      setLoading(false);
    }
  }

  function handleSelect(repo) {
    setSelectedRepo(repo.full_name);
    onSelectRepo(repo);
  }

  function formatDate(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    const now = new Date();
    const diffMs = now - d;
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffDays === 0) return 'today';
    if (diffDays === 1) return 'yesterday';
    if (diffDays < 30) return `${diffDays}d ago`;
    if (diffDays < 365) return `${Math.floor(diffDays / 30)}mo ago`;
    return `${Math.floor(diffDays / 365)}y ago`;
  }

  return (
    <div className="github-panel" style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div className="github-panel__header">
        <input
          type="search"
          className="repo-search"
          placeholder="Search your repositories..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          autoFocus
        />
      </div>

      {error && (
        <div style={{ padding: 'var(--space-3) var(--space-4)', color: 'var(--color-critical)', fontSize: 'var(--text-sm)' }}>
          {error}
        </div>
      )}

      <div className="repo-list">
        {loading && repos.length === 0 ? (
          <div className="loading-overlay" style={{ padding: 'var(--space-8)' }}>
            <div className="spinner" />
            <p>Loading repositories...</p>
          </div>
        ) : repos.length === 0 ? (
          <div style={{ padding: 'var(--space-8)', textAlign: 'center', color: 'var(--text-tertiary)', fontSize: 'var(--text-sm)' }}>
            {debouncedSearch ? 'No repositories match your search.' : 'No repositories found.'}
          </div>
        ) : (
          repos.map((repo) => (
            <div
              key={repo.full_name}
              className={`repo-item ${selectedRepo === repo.full_name ? 'repo-item--selected' : ''}`}
              onClick={() => handleSelect(repo)}
            >
              <div className="repo-item__info">
                <span className="repo-item__name">{repo.full_name}</span>
                {repo.description && (
                  <span className="repo-item__desc">{repo.description}</span>
                )}
              </div>
              <div className="repo-item__meta">
                {repo.private && <span className="repo-item__private">private</span>}
                {repo.language && <span>{repo.language}</span>}
                {repo.stargazers_count > 0 && <span>★ {repo.stargazers_count}</span>}
                <span>{formatDate(repo.updated_at)}</span>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Pagination */}
      {(page > 1 || hasNext) && (
        <div style={{ display: 'flex', justifyContent: 'space-between', padding: 'var(--space-2) var(--space-4)', borderTop: '1px solid var(--border-default)', background: 'var(--bg-secondary)' }}>
          <button
            className="btn btn--ghost"
            disabled={page === 1}
            onClick={() => setPage((p) => p - 1)}
          >
            ← Previous
          </button>
          <button
            className="btn btn--ghost"
            disabled={!hasNext}
            onClick={() => setPage((p) => p + 1)}
          >
            Next →
          </button>
        </div>
      )}

      {/* Manual input fallback */}
      <div className="repo-manual-input">
        <p>Or paste a repo URL / owner/repo for repositories you don't own:</p>
        <input
          type="text"
          placeholder="e.g. facebook/react"
          onKeyDown={(e) => {
            if (e.key === 'Enter' && e.target.value.trim()) {
              const val = e.target.value.trim();
              onSelectRepo({
                full_name: val,
                owner: val.split('/')[0] || val,
                name: val.split('/')[1] || val,
                private: false,
                language: null,
                description: '',
              });
            }
          }}
        />
      </div>
    </div>
  );
}
