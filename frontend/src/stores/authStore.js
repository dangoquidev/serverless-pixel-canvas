import { writable } from 'svelte/store';

/** Auth Lambda redirects to FRONTEND_URL#token=JWT (success) or #error=code (failure) */
const AUTH_ERROR_MESSAGES = {
    discord_api_failure: 'Discord authentication failed. Please try again.',
    internal_configuration_error: 'Server configuration error. Please try again later.',
    internal_error: 'An unexpected error occurred. Please try again.',
    missing_code: 'Authorization was cancelled or incomplete.',
};

function parseHashParams() {
    if (typeof window === 'undefined') return { token: null, error: null };
    const hash = window.location.hash?.substring(1) || '';
    if (!hash) return { token: null, error: null };
    const params = new URLSearchParams(hash);
    const token = params.get('token');
    const error = params.get('error');
    return { token: token || null, error: error || null };
}

function clearHash() {
    if (typeof window !== 'undefined') {
        window.history.replaceState(null, '', window.location.pathname || '/');
    }
}

// Parse OAuth callback hash once at load (before any component)
const hashParams = typeof window !== 'undefined' ? parseHashParams() : { token: null, error: null };
if (hashParams.token || hashParams.error) {
    clearHash();
}

const createPersistentStore = (key, initialValue) => {
    const isBrowser = typeof window !== 'undefined';
    const storedValue = isBrowser
        ? (hashParams.token ?? localStorage.getItem(key))
        : null;
    const store = writable(storedValue ?? initialValue);

    if (isBrowser) {
        store.subscribe(value => {
            if (value) {
                localStorage.setItem(key, value);
            } else {
                localStorage.removeItem(key);
            }
        });
    }

    return store;
};

export const authToken = createPersistentStore('pixel_canvas_auth_token', null);

export const authError = writable(
    hashParams.error ? (AUTH_ERROR_MESSAGES[hashParams.error] ?? `Authentication failed (${hashParams.error}).`) : null
);

export const clearAuthError = () => authError.set(null);

export const login = () => {
    clearAuthError();
    const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:3000';
    window.location.href = `${API_URL}/auth/callback`;
};

export const logout = () => {
    authToken.set(null);
    clearAuthError();
};
