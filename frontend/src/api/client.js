/**
 * API Client — Centralized fetch wrapper for all backend communication.
 *
 * Handles JWT auth headers, JSON parsing, and error responses consistently.
 * All API functions return the parsed JSON response or throw an error
 * with a user-friendly message.
 */

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:5000';

/**
 * Core fetch wrapper that adds auth headers and handles errors.
 */
async function apiRequest(endpoint, options = {}) {
  const token = localStorage.getItem('codelens_token');

  const headers = {
    'Content-Type': 'application/json',
    ...options.headers,
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
  });

  const data = await response.json();

  if (!response.ok) {
    // Handle specific status codes
    if (response.status === 401) {
      // Token expired or invalid — clear it and redirect
      localStorage.removeItem('codelens_token');
      localStorage.removeItem('codelens_user');
      window.location.href = '/login';
      throw new Error('Session expired. Please log in again.');
    }

    if (response.status === 429) {
      throw new Error(data.details || 'Rate limit exceeded. Please try again later.');
    }

    throw new Error(data.error || `Request failed with status ${response.status}`);
  }

  return data;
}

/* ── Auth ── */

export async function githubLogin(code) {
  return apiRequest('/api/auth/github/callback', {
    method: 'POST',
    body: JSON.stringify({ code }),
  });
}

/* ── Reviews ── */

export async function submitReview(code, language) {
  return apiRequest('/api/review', {
    method: 'POST',
    body: JSON.stringify({ code, language }),
  });
}

export async function getReview(reviewId) {
  return apiRequest(`/api/review/${reviewId}`);
}

/**
 * Poll a review every `intervalMs` until it reaches a terminal state.
 * Calls `onUpdate` with each response so the UI can show progress.
 * Returns the final review data.
 */
export async function pollReview(reviewId, onUpdate, intervalMs = 2000) {
  return new Promise((resolve, reject) => {
    const poll = async () => {
      try {
        const data = await getReview(reviewId);
        onUpdate(data);

        if (data.status === 'complete' || data.status === 'failed') {
          resolve(data);
        } else {
          setTimeout(poll, intervalMs);
        }
      } catch (err) {
        reject(err);
      }
    };

    poll();
  });
}

/* ── History ── */

export async function getHistory(page = 1, perPage = 10) {
  return apiRequest(`/api/history?page=${page}&per_page=${perPage}`);
}

/* ── Stats ── */

export async function getStats() {
  return apiRequest('/api/stats');
}
