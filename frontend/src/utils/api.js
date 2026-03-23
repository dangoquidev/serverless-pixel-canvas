import { get } from 'svelte/store';
import { authToken } from '../stores/authStore.js';
import {
    isOffline,
    queuePixel,
    getQueuedPixels,
    clearQueue,
} from '../stores/offlineStore.js';

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:3000";

let isSyncingQueue = false;

const parseJsonBodySafely = async (response) => {
    const text = await response.text();
    if (!text) return null;

    try {
        return JSON.parse(text);
    } catch {
        return null;
    }
};

const request = async (endpoint, options = {}) => {
    const token = get(authToken);

    const headers = {
        'Content-Type': 'application/json',
        ...options.headers,
    };

    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    const config = {
        ...options,
        headers,
    };

    const response = await fetch(`${API_URL}${endpoint}`, config);

    if (response.status === 401) {
        // Unauthorized - token might be invalid/expired
        authToken.set(null);
        throw new Error("Unauthorized");
    }

    if (response.status === 403) {
    }

    return response;
};

const setOfflineStatus = (offline) => {
    isOffline.set(offline);
};

const enqueuePixelDraw = (x, y, color) => {
    queuePixel({
        x,
        y,
        color,
        queuedAt: Date.now(),
    });
};

const sendPixel = async (x, y, color) => {
    const res = await request('/pixels', {
        method: 'POST',
        body: JSON.stringify({ x, y, color })
    });

    return res;
};

export const syncQueuedPixels = async () => {
    if (isSyncingQueue) return;

    const queued = getQueuedPixels();
    if (!queued.length) return;

    isSyncingQueue = true;

    try {
        for (const pixel of queued) {
            const res = await sendPixel(pixel.x, pixel.y, pixel.color);

            if (res.status === 401 || res.status === 403) {
                throw new Error('Unauthorized while syncing offline queue');
            }

            if (res.status === 429) {
                // Keep queue intact and retry later to respect rate limiting.
                return;
            }

            if (!res.ok) {
                throw new Error('Failed to sync offline queue');
            }
        }

        await clearQueue();
    } finally {
        isSyncingQueue = false;
    }
};

if (typeof window !== 'undefined') {
    setOfflineStatus(!window.navigator.onLine);

    window.addEventListener('offline', () => setOfflineStatus(true));
    window.addEventListener('online', async () => {
        setOfflineStatus(false);

        try {
            await syncQueuedPixels();
        } catch (error) {
            console.warn('Offline queue sync failed:', error);
        }
    });
}

export const fetchChunk = async (cx, cy) => {
    const response = await fetch(`${API_URL}/canvas?cx=${cx}&cy=${cy}`);
    if (!response.ok) throw new Error(`Failed to fetch chunk ${cx},${cy}`);

    let base64Text = await response.text();
    base64Text = base64Text.replace(/^"|"$/g, '').trim();
    if (!base64Text) return new ArrayBuffer(0);
    const binaryString = atob(base64Text);
    const len = binaryString.length;
    const bytes = new Uint8Array(len);
    for (let i = 0; i < len; i++) {
        bytes[i] = binaryString.charCodeAt(i);
    }

    return bytes.buffer;
};

export const drawPixel = async (x, y, color) => {
    if (typeof window !== 'undefined' && !window.navigator.onLine) {
        enqueuePixelDraw(x, y, color);
        setOfflineStatus(true);
        return true;
    }

    let res;
    try {
        res = await sendPixel(x, y, color);
        setOfflineStatus(false);
    } catch (error) {
        if (error?.message === 'Unauthorized') {
            throw new Error("You need to be logged in to draw pixels");
        }

        // Network-level errors (offline, DNS, CORS transport) should queue.
        enqueuePixelDraw(x, y, color);
        setOfflineStatus(true);
        return true;
    }

    if (res.status === 429) {
        const data = await parseJsonBodySafely(res);
        const retryAfter = res.headers.get('Retry-After');
        const fallbackMessage = retryAfter
            ? `Rate limited. Retry after ${retryAfter} seconds.`
            : 'Rate limited';

        throw new Error(data?.message || fallbackMessage);
    }
    if (res.status === 401) {
        throw new Error("You need to be logged in to draw pixels");
    }

    if (!res.ok) {
        const data = await parseJsonBodySafely(res);
        throw new Error(data?.message || data?.error || "Failed to draw pixel");
    }

    return true;
};
