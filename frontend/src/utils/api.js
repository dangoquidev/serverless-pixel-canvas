import { get } from 'svelte/store';
import { authToken } from '../stores/authStore.js';
import { isOffline, queuePixel, getQueuedPixels, clearQueue, cacheChunk } from '../stores/offlineStore.js';

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:3000";

// Track online/offline status
window.addEventListener('online', () => {
    console.log('[API] Back online - syncing queued pixels');
    isOffline.set(false);
    syncQueuedPixels();
});

window.addEventListener('offline', () => {
    console.log('[API] Network offline - queueing pixels');
    isOffline.set(true);
});

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

    return response;
};

export const fetchCanvas = async () => {
    const res = await request('/canvas');
    if (!res.ok) throw new Error("Failed to fetch canvas");
    return res.json();
};

export const fetchChunk = async (cx, cy) => {
    try {
        const res = await request(`/canvas?cx=${cx}&cy=${cy}`);
        if (!res.ok) throw new Error(`Failed to fetch chunk ${cx},${cy}`);
        const data = await res.json();
        
        // Cache chunk for offline access
        if (data.pixels) {
            cacheChunk(`${cx}#${cy}`, data.pixels);
        }
        
        return data;
    } catch (error) {
        console.warn('[API] Chunk fetch failed, trying cache:', error.message);
        // Try to return from cache
        const { getCachedChunk } = await import('../stores/offlineStore.js');
        const cached = await getCachedChunk(`${cx}#${cy}`);
        if (cached) {
            return { pixels: cached.pixels, cached: true };
        }
        throw error;
    }
};

export const drawPixel = async (x, y, color) => {
    // Check online status
    if (!navigator.onLine) {
        console.log('[API] Offline - queueing pixel:', { x, y, color });
        queuePixel({ x, y, color, userId: get(authToken) });
        return { queued: true };
    }

    try {
        const res = await request('/pixels', {
            method: 'POST',
            body: JSON.stringify({ x, y, color })
        });

        if (res.status === 429) {
            const data = await res.json();
            throw new Error(data.message || "Rate limited");
        }
        if (res.status === 401) {
            throw new Error("You need to be logged in to draw pixels");
        }

        if (!res.ok) {
            // Network error - queue for retry
            console.warn('[API] Draw failed, queuing:', { x, y, color });
            queuePixel({ x, y, color, userId: get(authToken) });
            return { queued: true };
        }

        return { success: true };
    } catch (error) {
        // Network error during fetch - queue pixel
        console.warn('[API] Draw request failed, queuing:', error.message);
        queuePixel({ x, y, color, userId: get(authToken) });
        return { queued: true };
    }
};

// Sync queued pixels when connection restored
async function syncQueuedPixels() {
    const queued = getQueuedPixels();
    if (queued.length === 0) return;

    console.log('[API] Syncing', queued.length, 'queued pixels...');
    let successCount = 0;

    for (const pixel of queued) {
        try {
            const res = await request('/pixels', {
                method: 'POST',
                body: JSON.stringify({ 
                    x: pixel.x, 
                    y: pixel.y, 
                    color: pixel.color 
                })
            });

            if (res.ok) {
                successCount++;
            } else if (res.status === 429 || res.status === 401) {
                // Don't retry auth/rate limit errors
                console.warn('[API] Skipping pixel (auth/rate limit):', pixel);
            } else {
                // Try again later
                console.warn('[API] Failed to sync pixel, will retry:', pixel);
                break;
            }
        } catch (error) {
            console.warn('[API] Sync error:', error.message);
            break;
        }
    }

    if (successCount > 0) {
        console.log('[API] Synced', successCount, 'pixels');
    }

    if (successCount === queued.length) {
        // All synced successfully
        await clearQueue();
    }
}
