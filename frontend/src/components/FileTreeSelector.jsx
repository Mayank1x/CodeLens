/**
 * FileTreeSelector — Checkbox tree for selecting files to scan.
 *
 * When a repo has >30 supported files, this component shows the
 * full file list with checkboxes so users can pick which files
 * to include in the review (max 30).
 */

import { useState, useEffect } from 'react';
import { getRepoTree } from '../api/client';

const MAX_FILES = 30;

export default function FileTreeSelector({ repo, onSubmit, onBack }) {
  const [files, setFiles] = useState([]);
  const [selected, setSelected] = useState(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [totalFiles, setTotalFiles] = useState(0);
  const [skippedFiles, setSkippedFiles] = useState(0);

  useEffect(() => {
    fetchTree();
  }, [repo]);

  async function fetchTree() {
    setLoading(true);
    setError(null);
    try {
      const data = await getRepoTree(repo.owner, repo.name);
      const fileList = data.files || [];
      setFiles(fileList);
      setTotalFiles(data.total_files || 0);
      setSkippedFiles(data.skipped_files || 0);

      // Pre-select up to MAX_FILES files
      const initial = new Set(fileList.slice(0, MAX_FILES).map((f) => f.path));
      setSelected(initial);
    } catch (err) {
      setError(err.message || 'Failed to load file tree.');
    } finally {
      setLoading(false);
    }
  }

  function toggleFile(path) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(path)) {
        next.delete(path);
      } else {
        if (next.size >= MAX_FILES) return prev; // Don't exceed limit
        next.add(path);
      }
      return next;
    });
  }

  function selectAll() {
    setSelected(new Set(files.slice(0, MAX_FILES).map((f) => f.path)));
  }

  function clearAll() {
    setSelected(new Set());
  }

  function formatSize(bytes) {
    if (!bytes) return '';
    if (bytes < 1024) return `${bytes}B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
  }

  if (loading) {
    return (
      <div className="github-panel">
        <div className="loading-overlay">
          <div className="spinner" />
          <p>Loading file tree for {repo.full_name}...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="github-panel">
        <div className="file-tree__header">
          <button className="btn btn--ghost" onClick={onBack}>← Back</button>
          <span style={{ color: 'var(--color-critical)', fontSize: 'var(--text-sm)' }}>{error}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="github-panel">
      <div className="file-tree">
        <div className="file-tree__header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
            <button className="btn btn--ghost" onClick={onBack} style={{ padding: 'var(--space-1) var(--space-2)' }}>
              ←
            </button>
            <h3>{repo.full_name}</h3>
          </div>
          <span className={`file-tree__count ${selected.size > MAX_FILES ? 'file-tree__count--over' : ''}`}>
            {selected.size}/{MAX_FILES} files selected
          </span>
        </div>

        <div style={{ padding: 'var(--space-2) var(--space-4)', fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', borderBottom: '1px solid var(--border-subtle)' }}>
          {files.length} supported files found out of {totalFiles} total ({skippedFiles} skipped)
        </div>

        <div className="file-tree__actions">
          <button className="btn btn--ghost" onClick={selectAll} style={{ fontSize: 'var(--text-xs)', padding: '2px var(--space-2)' }}>
            Select first {MAX_FILES}
          </button>
          <button className="btn btn--ghost" onClick={clearAll} style={{ fontSize: 'var(--text-xs)', padding: '2px var(--space-2)' }}>
            Clear all
          </button>
        </div>

        <div className="file-tree__list">
          {files.map((file) => (
            <label
              key={file.path}
              className="file-tree-item"
              onClick={(e) => {
                // Prevent double-toggle from label wrapping checkbox
                if (e.target.tagName !== 'INPUT') {
                  e.preventDefault();
                  toggleFile(file.path);
                }
              }}
            >
              <input
                type="checkbox"
                checked={selected.has(file.path)}
                onChange={() => toggleFile(file.path)}
                disabled={!selected.has(file.path) && selected.size >= MAX_FILES}
              />
              <span className="file-tree-item__path">{file.path}</span>
              <span className="file-tree-item__lang">{file.language}</span>
              <span className="file-tree-item__size">{formatSize(file.size)}</span>
            </label>
          ))}
        </div>

        <div style={{
          padding: 'var(--space-3) var(--space-4)',
          borderTop: '1px solid var(--border-default)',
          background: 'var(--bg-secondary)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}>
          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
            {selected.size === 0 ? 'Select files to scan' : `${selected.size} file${selected.size === 1 ? '' : 's'} ready`}
          </span>
          <button
            className="btn btn--primary"
            disabled={selected.size === 0}
            onClick={() => onSubmit(repo.full_name, Array.from(selected))}
          >
            Scan {selected.size} file{selected.size === 1 ? '' : 's'}
          </button>
        </div>
      </div>
    </div>
  );
}
