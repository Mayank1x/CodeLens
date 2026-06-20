import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { githubLogin } from '../api/client';
import './LoginPage.css';

const GITHUB_CLIENT_ID = import.meta.env.VITE_GITHUB_CLIENT_ID;
const REDIRECT_URI = `${window.location.origin}/login`;

export default function LoginPage() {
  const { login, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  // If already logged in, redirect to the review page
  useEffect(() => {
    if (isAuthenticated) {
      navigate('/review', { replace: true });
    }
  }, [isAuthenticated, navigate]);

  // Handle the OAuth callback — GitHub redirects back with ?code=...
  useEffect(() => {
    const code = searchParams.get('code');
    if (!code) return;

    setLoading(true);
    setError(null);

    githubLogin(code)
      .then((data) => {
        login(data.token, data.user);
        navigate('/review', { replace: true });
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, [searchParams, login, navigate]);

  function handleGitHubLogin() {
    // Redirect to GitHub's OAuth authorization page.
    // After the user authorizes, GitHub redirects back to our REDIRECT_URI
    // with a ?code= parameter that we exchange for a JWT.
    const githubAuthUrl =
      `https://github.com/login/oauth/authorize` +
      `?client_id=${GITHUB_CLIENT_ID}` +
      `&redirect_uri=${encodeURIComponent(REDIRECT_URI)}` +
      `&scope=read:user`;

    window.location.href = githubAuthUrl;
  }

  return (
    <div className="login-page">
      <div className="login-card card card--elevated">
        <div className="login-card__logo">
          Code<span>Lens</span>
        </div>

        <p className="login-card__tagline">
          AI-powered code review that combines static analysis with
          LLM-based semantic analysis to find bugs, security vulnerabilities,
          and code quality issues.
        </p>

        <div className="login-card__divider" />

        {loading ? (
          <div className="login-card__loading">
            <div className="spinner" />
            Authenticating with GitHub...
          </div>
        ) : (
          <button
            className="btn login-card__github-btn"
            onClick={handleGitHubLogin}
            disabled={!GITHUB_CLIENT_ID}
          >
            <svg className="login-card__github-icon" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z" />
            </svg>
            Sign in with GitHub
          </button>
        )}

        {error && <div className="login-card__error">{error}</div>}

        <div className="login-card__features">
          <div className="login-card__feature">
            <h4>Static Analysis</h4>
            <p>8 built-in rules catch secrets, SQL injection, and more</p>
          </div>
          <div className="login-card__feature">
            <h4>LLM Review</h4>
            <p>AI-powered semantic analysis finds deeper issues</p>
          </div>
          <div className="login-card__feature">
            <h4>Review History</h4>
            <p>Track all your past reviews and trends over time</p>
          </div>
          <div className="login-card__feature">
            <h4>4 Languages</h4>
            <p>Python, JavaScript, Java, and C++ supported</p>
          </div>
        </div>
      </div>
    </div>
  );
}
