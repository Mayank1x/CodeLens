/**
 * ReviewPage — Main review interface
 *
 * Three input modes: Paste Code, ZIP Upload, GitHub Repo.
 * Shows a split layout: editor/input on the left, results on the right.
 * Includes health score ring indicator for single-file reviews.
 */

import { useState, useRef, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import Editor from '@monaco-editor/react';
import {
  submitReview,
  submitBatchReview,
  submitGithubReview,
  pollReview,
  pollBatch,
  getReview,
} from '../api/client';
import { useAuth } from '../context/AuthContext';
import { LANGUAGES, MONACO_LANGUAGE_MAP, SEVERITY_ORDER } from '../utils/constants';
import RepoSelector from '../components/RepoSelector';
import FileTreeSelector from '../components/FileTreeSelector';
import './ReviewPage.css';

// --- Health Score Ring Component ---
function HealthRing({ score }) {
  if (score == null) return null;

  const radius = 30;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;
  const tier = score >= 80 ? 'good' : score >= 50 ? 'fair' : 'poor';

  return (
    <div className={`health-ring health-ring--${tier}`}>
      <svg width="72" height="72" viewBox="0 0 72 72">
        <circle className="health-ring__track" cx="36" cy="36" r={radius} />
        <circle
          className="health-ring__fill"
          cx="36"
          cy="36"
          r={radius}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
        />
      </svg>
      <span className="health-ring__value">{score}</span>
    </div>
  );
}

export default function ReviewPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { user } = useAuth();
  const isGuest = user?.id === 'guest';

  const [activeTab, setActiveTab] = useState('paste');

  const guestCode = `def get_user_data(user_id):
    # Retrieve user data from DB
    query = "SELECT * FROM users WHERE id = " + user_id
    cursor.execute(query)
    
    # Check admin privileges
    if user_id == 1:
        admin_token = "sk_live_1234567890abcdef"
        print(admin_token)
    
    return cursor.fetchone()
`;

  // Single Review State
  const [code, setCode] = useState(isGuest ? guestCode : '// Paste your code here\n');
  const [language, setLanguage] = useState(LANGUAGES[0].value);
  const [reviewId, setReviewId] = useState(null);
  const [healthScore, setHealthScore] = useState(null);

  // Batch Review State
  const [batchFile, setBatchFile] = useState(null);
  const [batchData, setBatchData] = useState(null);
  const [activeBatchReviewId, setActiveBatchReviewId] = useState(null);

  // GitHub Repo State
  const [githubStep, setGithubStep] = useState('browse'); // 'browse' | 'files'
  const [selectedRepo, setSelectedRepo] = useState(null);

  // Shared UI State
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [status, setStatus] = useState(null);
  const [issues, setIssues] = useState([]);
  const [diffSummary, setDiffSummary] = useState(null);
  const [error, setError] = useState(null);
  const [activeIssueId, setActiveIssueId] = useState(null);

  const editorRef = useRef(null);
  const decorationsRef = useRef([]);
  const fileInputRef = useRef(null);

  // --- Load existing review from URL ---
  useEffect(() => {
    const rId = searchParams.get('id');
    if (rId) {
      setActiveTab('paste');
      setReviewId(rId);
      loadExistingReview(rId);
    }
  }, [searchParams]);

  async function loadExistingReview(rId) {
    setIsSubmitting(true);
    setError(null);
    try {
      const data = await getReview(rId);
      setCode(data.code || '');
      setLanguage(data.language || 'python');
      setStatus(data.status);
      setDiffSummary(data.diff_summary || null);
      setHealthScore(data.health_score ?? null);

      if (data.status === 'complete' || data.status === 'failed') {
        const sortedIssues = (data.issues || []).sort(
          (a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity]
        );
        setIssues(sortedIssues);
      } else {
        startPollingReview(rId);
      }
    } catch (err) {
      setError(err.message || 'Failed to load review.');
    } finally {
      setIsSubmitting(false);
    }
  }

  function handleEditorMount(editor) {
    editorRef.current = editor;
  }

  // --- Tab switching with guest guard ---
  function handleTabChange(tab) {
    if ((tab === 'zip' || tab === 'github') && isGuest) {
      setError('Sign in with GitHub to use batch review and repo scanning.');
      return;
    }
    setActiveTab(tab);
    setError(null);
  }

  // --- Submit handler ---
  async function handleSubmit() {
    setIsSubmitting(true);
    setError(null);
    setIssues([]);
    setStatus('pending');
    setActiveIssueId(null);
    setBatchData(null);
    setHealthScore(null);
    setSearchParams({});

    try {
      if (activeTab === 'paste') {
        if (!code.trim() || code === '// Paste your code here\n') {
          throw new Error('Please enter some code to review.');
        }
        const res = await submitReview(code, language, reviewId);
        setReviewId(res.review_id);
        startPollingReview(res.review_id);
      } else if (activeTab === 'zip') {
        if (!batchFile) throw new Error('Please select a ZIP file.');
        const res = await submitBatchReview(batchFile);
        startPollingBatch(res.batch_id);
      }
    } catch (err) {
      setError(err.message || 'Submission failed.');
      setIsSubmitting(false);
      setStatus(null);
    }
  }

  // --- GitHub repo scan ---
  async function handleGithubScan(repoFullName, selectedFiles) {
    setIsSubmitting(true);
    setError(null);
    setIssues([]);
    setStatus('pending');
    setActiveIssueId(null);
    setBatchData(null);
    setHealthScore(null);

    try {
      const res = await submitGithubReview(repoFullName, selectedFiles);
      startPollingBatch(res.batch_id);
    } catch (err) {
      setError(err.message || 'GitHub scan failed.');
      setIsSubmitting(false);
      setStatus(null);
    }
  }

  async function startPollingReview(id) {
    try {
      const finalData = await pollReview(id, (update) => {
        setStatus(update.status);
      });
      const sortedIssues = (finalData.issues || []).sort(
        (a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity]
      );
      setIssues(sortedIssues);
      setDiffSummary(finalData.diff_summary || null);
      setHealthScore(finalData.health_score ?? null);
    } catch (err) {
      setError(err.message || 'Polling failed.');
    } finally {
      setIsSubmitting(false);
    }
  }

  async function startPollingBatch(id) {
    try {
      const finalData = await pollBatch(id, (update) => {
        setStatus(update.status);
        setBatchData(update);
      });
      setBatchData(finalData);

      const firstComplete = (finalData.reviews || []).find((r) => r.status === 'complete');
      if (firstComplete) {
        setActiveBatchReviewId(firstComplete.id);
        loadBatchReviewIssues(firstComplete.id);
      }
    } catch (err) {
      setError(err.message || 'Batch polling failed.');
    } finally {
      setIsSubmitting(false);
    }
  }

  async function loadBatchReviewIssues(id) {
    try {
      const data = await getReview(id);
      const sortedIssues = (data.issues || []).sort(
        (a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity]
      );
      setIssues(sortedIssues);
      setDiffSummary(data.diff_summary || null);
      setActiveIssueId(null);
    } catch (err) {
      console.error(err);
    }
  }

  // --- Editor decorations ---
  useEffect(() => {
    if (!editorRef.current || !window.monaco) return;
    const decorations = issues.map((issue) => {
      let className = 'issue-highlight-info';
      if (issue.severity === 'critical') className = 'issue-highlight-critical';
      if (issue.severity === 'warning') className = 'issue-highlight-warning';

      return {
        range: new window.monaco.Range(issue.line_number, 1, issue.line_number, 1),
        options: {
          isWholeLine: true,
          className,
          overviewRuler: {
            color: issue.severity === 'critical' ? '#e5534b' : '#c69026',
            position: window.monaco.editor.OverviewRulerLane.Right,
          },
        },
      };
    });
    decorationsRef.current = editorRef.current.deltaDecorations(
      decorationsRef.current,
      decorations
    );
  }, [issues]);

  function handleIssueClick(issue, index) {
    setActiveIssueId(index);
    if (editorRef.current && issue.line_number) {
      editorRef.current.revealLineInCenter(issue.line_number);
      editorRef.current.setPosition({ lineNumber: issue.line_number, column: 1 });
      editorRef.current.focus();
    }
  }

  const getHealthScoreColor = (score) => {
    if (score == null) return '';
    if (score >= 80) return 'health-score--good';
    if (score >= 50) return 'health-score--fair';
    return 'health-score--poor';
  };

  return (
    <div className="review-page">
      {/* --- Guest Banner --- */}
      {isGuest && (
        <div className="guest-banner">
          Guest mode — paste code analysis only.{' '}
          <a
            href={`https://github.com/login/oauth/authorize?client_id=${import.meta.env.VITE_GITHUB_CLIENT_ID}&scope=read:user`}
          >
            Sign in with GitHub
          </a>{' '}
          for history, batch review, and repo scanning.
        </div>
      )}

      {/* --- Header --- */}
      <div className="review-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
          <div className="input-tabs">
            <div
              className={`input-tab ${activeTab === 'paste' ? 'input-tab--active' : ''}`}
              onClick={() => handleTabChange('paste')}
            >
              Paste
            </div>
            <div
              className={`input-tab ${activeTab === 'zip' ? 'input-tab--active' : ''} ${isGuest ? 'input-tab--disabled' : ''}`}
              onClick={() => handleTabChange('zip')}
              title={isGuest ? 'Requires GitHub login' : ''}
            >
              ZIP
            </div>
            <div
              className={`input-tab ${activeTab === 'github' ? 'input-tab--active' : ''} ${isGuest ? 'input-tab--disabled' : ''}`}
              onClick={() => handleTabChange('github')}
              title={isGuest ? 'Requires GitHub login' : ''}
            >
              GitHub
            </div>
          </div>
          <span className="review-header__title">
            {activeTab === 'paste' ? 'review' : activeTab === 'zip' ? 'batch' : 'repo scan'}
          </span>
        </div>

        <div className="review-header__controls">
          {error && <div className="toast toast--error fade-in">{error}</div>}

          {activeTab === 'paste' && (
            <select
              className="select"
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              disabled={isSubmitting}
            >
              {LANGUAGES.map((lang) => (
                <option key={lang.value} value={lang.value}>
                  {lang.label}
                </option>
              ))}
            </select>
          )}

          {activeTab !== 'github' && (
            <button
              className="btn btn--primary"
              onClick={handleSubmit}
              disabled={isSubmitting || status === 'pending' || status === 'processing'}
            >
              {isSubmitting ? (
                <>
                  <div className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} />
                  Analyzing...
                </>
              ) : (
                'Run Analysis'
              )}
            </button>
          )}
        </div>
      </div>

      {/* --- Main Content --- */}
      <div className="review-main">
        {/* --- LEFT PANEL --- */}
        {activeTab === 'paste' && (
          <div className="editor-panel">
            <Editor
              height="100%"
              language={MONACO_LANGUAGE_MAP[language] || language}
              theme="vs-dark"
              value={code}
              onChange={(val) => setCode(val || '')}
              onMount={handleEditorMount}
              options={{
                minimap: { enabled: false },
                fontSize: 13,
                padding: { top: 12 },
                fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                lineHeight: 20,
                renderLineHighlight: 'gutter',
              }}
            />
          </div>
        )}

        {activeTab === 'zip' && !batchData && (
          <div className="upload-panel">
            <div className="dropzone" onClick={() => fileInputRef.current?.click()}>
              <input
                type="file"
                accept=".zip"
                ref={fileInputRef}
                style={{ display: 'none' }}
                onChange={(e) => setBatchFile(e.target.files[0])}
              />
              <h3>{batchFile ? batchFile.name : 'Click to upload .zip'}</h3>
              <p>Max 30 source files, 500KB per file. Non-code files are skipped.</p>
            </div>
          </div>
        )}

        {activeTab === 'github' && !batchData && !isSubmitting && (
          <>
            {!user?.has_repo_scope ? (
              <div className="upload-panel">
                <div className="github-connect-banner" style={{ maxWidth: 480, width: '100%' }}>
                  <div>
                    <strong>Repository access required</strong>
                    <p>Connect your GitHub account with repo scope to browse and scan repositories.</p>
                  </div>
                  <a
                    href={`https://github.com/login/oauth/authorize?client_id=${import.meta.env.VITE_GITHUB_CLIENT_ID}&scope=repo`}
                    className="btn btn--primary"
                  >
                    Connect
                  </a>
                </div>
              </div>
            ) : githubStep === 'browse' ? (
              <RepoSelector
                onSelectRepo={(repo) => {
                  setSelectedRepo(repo);
                  setGithubStep('files');
                }}
              />
            ) : (
              <FileTreeSelector
                repo={selectedRepo}
                onBack={() => setGithubStep('browse')}
                onSubmit={(repoFullName, selectedFiles) => {
                  handleGithubScan(repoFullName, selectedFiles);
                }}
              />
            )}
          </>
        )}

        {/* Batch results view */}
        {batchData && (
          <div className="editor-panel" style={{ overflowY: 'auto' }}>
            <div className="batch-results-header">
              <div>
                <h2>Batch Analysis</h2>
                <p style={{ color: 'var(--text-secondary)', fontSize: 'var(--text-xs)', marginTop: 'var(--space-1)' }}>
                  Scanned {batchData.reviews?.length || 0} of{' '}
                  {(batchData.reviews?.length || 0) + (batchData.skipped_files || 0)} files
                  {batchData.skipped_files > 0 && ` (${batchData.skipped_files} skipped)`}
                </p>
              </div>
              {batchData.health_score != null && (
                <div className={`health-score ${getHealthScoreColor(batchData.health_score)}`}>
                  {batchData.health_score}
                  <span style={{ fontSize: 'var(--text-sm)', fontWeight: 400, color: 'var(--text-secondary)' }}>
                    /100
                  </span>
                </div>
              )}
            </div>
            <div className="batch-file-list">
              {(batchData.reviews || []).map((review) => (
                <div
                  key={review.id}
                  className={`batch-file-item ${activeBatchReviewId === review.id ? 'batch-file-item--active' : ''}`}
                  onClick={() => {
                    setActiveBatchReviewId(review.id);
                    loadBatchReviewIssues(review.id);
                  }}
                >
                  <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-sm)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {review.filename || `${review.language} file`}
                    </span>
                    <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', marginTop: 2 }}>
                      {review.language}
                    </span>
                  </div>
                  <div className="issue-badges">
                    <span className="badge badge--info">{review.issue_count || 0} issues</span>
                    {review.health_score != null && (
                      <span className={`badge ${review.health_score >= 80 ? 'badge--success' : review.health_score >= 50 ? 'badge--warning' : 'badge--critical'}`}>
                        {review.health_score}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Processing overlay for GitHub/Batch */}
        {(activeTab === 'github' || activeTab === 'zip') && isSubmitting && !batchData && (
          <div className="upload-panel">
            <div className="loading-overlay">
              <div className="spinner" />
              <p>Scanning repository files...</p>
            </div>
          </div>
        )}

        {/* --- RIGHT PANEL (ISSUES) --- */}
        <div className="results-panel">
          {(isSubmitting || status === 'processing') && issues.length === 0 ? (
            <div className="loading-overlay">
              <div className="spinner" />
              <p>Analyzing code...</p>
            </div>
          ) : issues.length > 0 ? (
            <>
              <div className="results-header">
                <div className="results-header__info">
                  <h2>{issues.length} Issues</h2>
                  {diffSummary && (
                    <div className="badge badge--info" style={{ marginTop: 'var(--space-1)' }}>
                      {diffSummary}
                    </div>
                  )}
                  <p>Click an issue to jump to it in the editor.</p>
                </div>
                {/* Health score ring for single-file reviews */}
                {activeTab === 'paste' && <HealthRing score={healthScore} />}
              </div>
              <div className="results-content fade-in">
                {issues.map((issue, i) => (
                  <div
                    key={i}
                    className={`issue-card ${activeIssueId === i ? 'issue-card--active' : ''}`}
                    onClick={() => handleIssueClick(issue, i)}
                  >
                    <div className="issue-header">
                      <div className="issue-badges">
                        <span className={`badge badge--${issue.severity}`}>{issue.severity}</span>
                        {issue.category && (
                          <span className={`badge badge--${issue.category}`}>{issue.category}</span>
                        )}
                      </div>
                      <span className="issue-line">L{issue.line_number}</span>
                    </div>
                    <div className="issue-message">{issue.message}</div>
                    {issue.suggestion && (
                      <div className="issue-suggestion">{issue.suggestion}</div>
                    )}
                    <div className="issue-source">
                      {issue.source === 'static' ? 'static' : 'llm'}
                    </div>
                  </div>
                ))}
              </div>
            </>
          ) : status === 'complete' ? (
            <div className="results-empty fade-in">
              <p>No issues found — clean code.</p>
              {activeTab === 'paste' && <HealthRing score={healthScore} />}
            </div>
          ) : (
            <div className="results-empty">
              <p>
                {activeTab === 'paste'
                  ? 'Paste code and click "Run Analysis"'
                  : activeTab === 'zip'
                  ? 'Upload a .zip file to scan'
                  : 'Select a repo and files to scan'}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
