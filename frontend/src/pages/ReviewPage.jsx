import { useState, useRef, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import Editor from '@monaco-editor/react';
import { submitReview, pollReview, getReview } from '../api/client';
import { LANGUAGES, MONACO_LANGUAGE_MAP, SEVERITY_ORDER } from '../utils/constants';
import './ReviewPage.css';

export default function ReviewPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [code, setCode] = useState('// Paste your code here\n');
  const [language, setLanguage] = useState(LANGUAGES[0].value);
  
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [reviewStatus, setReviewStatus] = useState(null); // 'pending' | 'processing' | 'complete' | 'failed'
  const [issues, setIssues] = useState([]);
  const [error, setError] = useState(null);
  const [activeIssueId, setActiveIssueId] = useState(null);

  const editorRef = useRef(null);
  const decorationsRef = useRef([]);

  // Load a specific review if ?id= is present in URL
  useEffect(() => {
    const reviewId = searchParams.get('id');
    if (reviewId) {
      loadExistingReview(reviewId);
    }
  }, [searchParams]);

  async function loadExistingReview(reviewId) {
    setIsSubmitting(true);
    setError(null);
    try {
      const data = await getReview(reviewId);
      setCode(data.code || '');
      setLanguage(data.language || 'python');
      setReviewStatus(data.status);
      
      if (data.status === 'complete' || data.status === 'failed') {
        const sortedIssues = (data.issues || []).sort(
          (a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity]
        );
        setIssues(sortedIssues);
      } else {
        // It's still processing, start polling
        startPolling(reviewId);
      }
    } catch (err) {
      setError(err.message || 'Failed to load review.');
    } finally {
      setIsSubmitting(false);
    }
  }

  function handleEditorMount(editor, monaco) {
    editorRef.current = editor;
  }

  async function handleReview() {
    if (!code.trim() || code === '// Paste your code here\n') {
      setError('Please enter some code to review.');
      return;
    }

    setIsSubmitting(true);
    setError(null);
    setIssues([]);
    setReviewStatus('pending');
    setActiveIssueId(null);
    
    // Clear URL params
    setSearchParams({});

    try {
      const { review_id } = await submitReview(code, language);
      startPolling(review_id);
    } catch (err) {
      setError(err.message || 'Submission failed.');
      setIsSubmitting(false);
      setReviewStatus(null);
    }
  }

  async function startPolling(reviewId) {
    try {
      const finalData = await pollReview(
        reviewId,
        (update) => setReviewStatus(update.status)
      );
      
      const sortedIssues = (finalData.issues || []).sort(
        (a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity]
      );
      
      setIssues(sortedIssues);
    } catch (err) {
      setError(err.message || 'Polling failed.');
    } finally {
      setIsSubmitting(false);
    }
  }

  // Update editor decorations (highlights) when issues change
  useEffect(() => {
    if (!editorRef.current) return;

    const decorations = issues.map((issue) => {
      let className = 'issue-highlight-info';
      if (issue.severity === 'critical') className = 'issue-highlight-critical';
      if (issue.severity === 'warning') className = 'issue-highlight-warning';

      return {
        range: new window.monaco.Range(issue.line_number, 1, issue.line_number, 1),
        options: {
          isWholeLine: true,
          className: className,
          overviewRuler: {
            color: issue.severity === 'critical' ? '#f85149' : '#d29922',
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

  return (
    <div className="review-page">
      <div className="review-header">
        <div className="review-header__title">Code Review</div>
        <div className="review-header__controls">
          {error && <div className="toast toast--error fade-in">{error}</div>}
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
          <button
            className="btn btn--primary"
            onClick={handleReview}
            disabled={isSubmitting || reviewStatus === 'pending' || reviewStatus === 'processing'}
          >
            {isSubmitting ? (
              <>
                <div className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} />
                Analyzing...
              </>
            ) : (
              'Review Code'
            )}
          </button>
        </div>
      </div>

      <div className="review-main">
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
              fontSize: 14,
              fontFamily: 'JetBrains Mono, monospace',
              padding: { top: 16 },
              scrollBeyondLastLine: false,
              readOnly: isSubmitting,
            }}
          />
        </div>

        <div className="results-panel">
          {(isSubmitting || reviewStatus === 'processing') && issues.length === 0 ? (
            <div className="loading-overlay">
              <div className="spinner" />
              <p>Analyzing code structure and semantics...</p>
            </div>
          ) : issues.length > 0 ? (
            <>
              <div className="results-header">
                <h2>{issues.length} Issues Found</h2>
                <p>Review the items below. Click an issue to locate it in the editor.</p>
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
                        <span className={`badge badge--${issue.severity}`}>
                          {issue.severity}
                        </span>
                        {issue.category && (
                          <span className={`badge badge--${issue.category}`}>
                            {issue.category}
                          </span>
                        )}
                      </div>
                      <span className="issue-line">Line {issue.line_number}</span>
                    </div>
                    
                    <div className="issue-message">{issue.message}</div>
                    
                    {issue.suggestion && (
                      <div className="issue-suggestion">
                        {issue.suggestion}
                      </div>
                    )}

                    <div className="issue-source">
                      Source: {issue.source === 'static' ? 'Static Analyzer' : 'LLM Reviewer'}
                    </div>
                  </div>
                ))}
              </div>
            </>
          ) : reviewStatus === 'complete' ? (
            <div className="results-empty fade-in">
              <h3>Clean Code! 🎉</h3>
              <p>No issues were found in this snippet.</p>
            </div>
          ) : (
            <div className="results-empty">
              <p>Paste your code and click <strong>Review Code</strong> to get started.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
