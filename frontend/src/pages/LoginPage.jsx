/**
 * LoginPage — Asymmetric split layout
 *
 * Left: branding + feature list. Right: auth buttons.
 * Per spec 7c: Guest button is MORE prominent than GitHub button,
 * and the layout avoids the centered-hero SaaS template look.
 */

import { useEffect, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import './LoginPage.css';

const GITHUB_CLIENT_ID = import.meta.env.VITE_GITHUB_CLIENT_ID;

function LoginPage() {
  const { login, guestLogin } = useAuth();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Handle the GitHub OAuth callback — the code arrives as a query param
  useEffect(() => {
    const code = searchParams.get('code');
    if (code) {
      setLoading(true);
      setError(null);
      handleGitHubCallback(code);
    }
  }, [searchParams]);

  async function handleGitHubCallback(code) {
    try {
      await login(code);
      navigate('/review');
    } catch (err) {
      setError(err.message || 'GitHub authentication failed.');
      setLoading(false);
    }
  }

  function handleGitHubLogin() {
    // Don't set redirect_uri — let GitHub use the one configured in the OAuth App settings
    const authUrl =
      `https://github.com/login/oauth/authorize?client_id=${GITHUB_CLIENT_ID}&scope=read:user`;
    window.location.href = authUrl;
  }

  async function handleGuestLogin() {
    setLoading(true);
    setError(null);
    try {
      await guestLogin();
      navigate('/review');
    } catch (err) {
      setError(err.message || 'Guest login failed.');
      setLoading(false);
    }
  }

  if (loading) {
    return (
      <div className="login-page">
        <div className="login-page__left">
          <div className="login-loading">
            <div className="spinner"></div>
            Authenticating...
          </div>
        </div>
        <div className="login-page__right"></div>
      </div>
    );
  }

  return (
    <div className="login-page">
      {/* Left side — branding and features */}
      <div className="login-page__left">
        <h1 className="login-logo">
          Code<span>Lens</span>
        </h1>
        <p className="login-tagline">
          AI-powered code review that combines static analysis with LLM semantic analysis.
          Find bugs, security issues, and code quality problems before they reach production.
        </p>

        <div className="login-features">
          <div className="login-feature">
            <div className="login-feature__icon"></div>
            <div>
              <h4>Static + LLM Analysis</h4>
              <p>8 pattern-based rules plus Gemini/Groq semantic review</p>
            </div>
          </div>
          <div className="login-feature">
            <div className="login-feature__icon"></div>
            <div>
              <h4>Multi-language Support</h4>
              <p>Python, JavaScript, Java, and C++ out of the box</p>
            </div>
          </div>
          <div className="login-feature">
            <div className="login-feature__icon"></div>
            <div>
              <h4>GitHub Integration</h4>
              <p>Scan your repositories directly — browse and select files</p>
            </div>
          </div>
          <div className="login-feature">
            <div className="login-feature__icon"></div>
            <div>
              <h4>Health Score Tracking</h4>
              <p>Track code quality over time with diff-aware re-reviews</p>
            </div>
          </div>
        </div>
      </div>

      {/* Right side — auth buttons */}
      <div className="login-page__right">
        <div className="login-auth">
          <h2 className="login-auth__title">Get Started</h2>

          {error && <div className="login-error">{error}</div>}

          {/* Guest button is primary (amber) per spec 7c */}
          <button
            id="guest-login-btn"
            className="btn btn--primary login-guest-btn"
            onClick={handleGuestLogin}
          >
            Try as Guest — No signup needed
          </button>

          <div className="login-auth__divider">or</div>

          {/* GitHub button is secondary */}
          <button
            id="github-login-btn"
            className="btn btn--secondary login-github-btn"
            onClick={handleGitHubLogin}
          >
            <svg className="login-github-icon" viewBox="0 0 16 16" fill="currentColor">
              <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
            </svg>
            Sign in with GitHub
          </button>
        </div>
      </div>
    </div>
  );
}

export default LoginPage;
