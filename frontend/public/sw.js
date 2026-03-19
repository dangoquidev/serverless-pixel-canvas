/**
 * Service Worker for Offline Pixel Canvas Support
 * 
 * Features:
 * - Cache canvas chunks for offline viewing
 * - Queue pixel updates when offline
 * - Sync queued updates when connection restored
 * - Precache API responses
 */

const CACHE_NAME = 'pixel-canvas-v1';
const CACHE_URLS = [
  '/',
  '/index.html',
  '/app.css',
  '/main.js'
];

// Install: Precache essential assets
self.addEventListener('install', (event) => {
  console.log('[SW] Installing service worker...');
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      console.log('[SW] Caching essential assets');
      return cache.addAll(CACHE_URLS).catch((err) => {
        console.warn('[SW] Some assets failed to cache:', err);
        // Don't fail installation if some assets can't be cached
        return Promise.resolve();
      });
    })
  );
  self.skipWaiting();
});

// Activate: Clean up old caches
self.addEventListener('activate', (event) => {
  console.log('[SW] Activating service worker...');
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name !== CACHE_NAME)
          .map((name) => {
            console.log('[SW] Deleting old cache:', name);
            return caches.delete(name);
          })
      );
    })
  );
  self.clients.claim();
});

// Fetch: Network-first for API, cache-first for assets
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET requests and external URLs
  if (request.method !== 'GET' || url.origin !== location.origin) {
    return;
  }

  // API calls: Network first, fallback to cache
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          // Cache successful responses
          if (response.ok) {
            const cache = caches.open(CACHE_NAME);
            cache.then((c) => c.put(request, response.clone()));
          }
          return response;
        })
        .catch(() => {
          // Network failed, try cache
          return caches.match(request).then((cached) => {
            if (cached) {
              console.log('[SW] Serving from cache:', url.pathname);
              return cached;
            }
            // No cache, return offline response
            return new Response(
              JSON.stringify({ error: 'offline', data: [] }),
              { status: 503, headers: { 'Content-Type': 'application/json' } }
            );
          });
        })
    );
    return;
  }

  // Static assets: Cache first
  event.respondWith(
    caches
      .match(request)
      .then((cached) => cached || fetch(request))
      .catch(() => {
        // Fallback: serve offline page if available
        return caches.match('/index.html');
      })
  );
});

// Message handler: Sync queued pixels when online
self.addEventListener('message', (event) => {
  const { type, payload } = event.data;

  if (type === 'SYNC_OFFLINE_PIXELS') {
    console.log('[SW] Syncing offline pixels:', payload);
    // Store in IndexedDB for persistence across refreshes
    openPixelStore().then((store) => {
      payload.forEach((pixel) => store.add(pixel));
    });
  }

  if (type === 'GET_OFFLINE_PIXELS') {
    openPixelStore().then((store) => {
      store.getAll((pixels) => {
        event.ports[0].postMessage({ type: 'OFFLINE_PIXELS', pixels });
      });
    });
  }
});

// Simple IndexedDB helper
function openPixelStore() {
  return new Promise((resolve) => {
    const dbReq = indexedDB.open('PixelCanvas', 1);

    dbReq.onupgradeneeded = (e) => {
      const db = e.target.result;
      if (!db.objectStoreNames.contains('pending_pixels')) {
        db.createObjectStore('pending_pixels', { keyPath: 'id', autoIncrement: true });
      }
    };

    dbReq.onsuccess = () => {
      const db = dbReq.result;
      const tx = db.transaction('pending_pixels', 'readwrite');
      resolve(tx.objectStore('pending_pixels'));
    };

    dbReq.onerror = () => {
      console.warn('[SW] IndexedDB failed, using in-memory fallback');
      resolve(createMemoryStore());
    };
  });
}

// In-memory fallback store if IndexedDB unavailable
let memoryStore = [];

function createMemoryStore() {
  return {
    add(item) {
      memoryStore.push(item);
      console.log('[SW] Added to memory store:', item);
    },
    getAll(callback) {
      callback(memoryStore);
    },
    clear() {
      memoryStore = [];
    }
  };
}
