import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import './Navbar.css';

export default function Navbar() {
  const { user, isAuthenticated, logout } = useAuth();
  const navigate = useNavigate();

  function handleLogout() {
    logout();
    navigate('/login');
  }

  if (!isAuthenticated) return null;

  return (
    <nav className="navbar">
      <NavLink to="/review" className="navbar__brand">
        Code<span>Lens</span>
      </NavLink>

      <div className="navbar__links">
        <NavLink
          to="/review"
          className={({ isActive }) =>
            `navbar__link ${isActive ? 'navbar__link--active' : ''}`
          }
        >
          Review
        </NavLink>
        <NavLink
          to="/history"
          className={({ isActive }) =>
            `navbar__link ${isActive ? 'navbar__link--active' : ''}`
          }
        >
          History
        </NavLink>
        <NavLink
          to="/dashboard"
          className={({ isActive }) =>
            `navbar__link ${isActive ? 'navbar__link--active' : ''}`
          }
        >
          Dashboard
        </NavLink>
      </div>

      <div className="navbar__user">
        {user?.avatar_url && (
          <img
            src={user.avatar_url}
            alt={user.username}
            className="navbar__avatar"
          />
        )}
        <span className="navbar__username">{user?.username}</span>
        <button className="btn btn--ghost navbar__logout" onClick={handleLogout}>
          Log out
        </button>
      </div>
    </nav>
  );
}
