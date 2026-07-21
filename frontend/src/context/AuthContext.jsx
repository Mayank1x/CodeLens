import { createContext, useContext, useState, useEffect } from 'react';
import { githubLogin as apiGithubLogin, guestLogin as apiGuestLogin } from '../api/client';

const AuthContext = createContext(null);

/**
 * Provides auth state (user, token) to the entire app.
 * Persists to localStorage so sessions survive page refreshes.
 *
 * Exposes:
 *  - login(code)       — exchanges GitHub OAuth code for JWT + user
 *  - guestLogin()      — gets a guest JWT
 *  - logout()          — clears session
 *  - user, token, isAuthenticated, loading
 */
export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(null);
  const [loading, setLoading] = useState(true);

  // On mount, restore session from localStorage
  useEffect(() => {
    const savedToken = localStorage.getItem('codelens_token');
    const savedUser = localStorage.getItem('codelens_user');

    if (savedToken && savedUser) {
      setToken(savedToken);
      try {
        setUser(JSON.parse(savedUser));
      } catch {
        localStorage.removeItem('codelens_user');
      }
    }

    setLoading(false);
  }, []);

  function _persist(newToken, newUser) {
    setToken(newToken);
    setUser(newUser);
    localStorage.setItem('codelens_token', newToken);
    localStorage.setItem('codelens_user', JSON.stringify(newUser));
  }

  /**
   * Exchange a GitHub OAuth code for a JWT and persist the session.
   */
  async function login(code) {
    const data = await apiGithubLogin(code);
    _persist(data.token, { ...data.user, has_repo_scope: data.has_repo_scope });
    return data;
  }

  /**
   * Start a guest session — gets a temporary JWT with limited access.
   */
  async function guestLogin() {
    const data = await apiGuestLogin();
    _persist(data.token, { ...data.user, has_repo_scope: false });
    return data;
  }

  function logout() {
    setToken(null);
    setUser(null);
    localStorage.removeItem('codelens_token');
    localStorage.removeItem('codelens_user');
  }

  const isAuthenticated = !!token;

  return (
    <AuthContext.Provider value={{ user, token, isAuthenticated, loading, login, guestLogin, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
