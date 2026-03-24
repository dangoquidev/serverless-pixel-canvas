/**
 * Offline Store - manages queued pixels when network is unavailable
 * 
 * Features:
 * - Queue pixels for offline drawing
 * - Persist queue to IndexedDB
 * - Sync queue when connection restored
 */

import { writable, derived } from 'svelte/store';

// Queue of pixels waiting to be sent
export const offlineQueue = writable([]);
export const isOffline = writable(false);
export const queueSize = derived(offlineQueue, ($q) => $q.length);

let db = null;

// Initialize IndexedDB
export async function initializeOfflineDB() {
  return new Promise((resolve, reject) => {
    const dbReq = indexedDB.open('PixelCanvasOffline', 1);

    dbReq.onupgradeneeded = (e) => {
      const database = e.target.result;
      if (!database.objectStoreNames.contains('queued_pixels')) {
        database.createObjectStore('queued_pixels', { keyPath: 'id', autoIncrement: true });
      }
      if (!database.objectStoreNames.contains('cached_chunks')) {
        database.createObjectStore('cached_chunks', { keyPath: 'chunkId' });
      }
    };

    dbReq.onsuccess = () => {
      db = dbReq.result;
      console.log('[Offline] IndexedDB initialized');
      loadQueueFromDB();
      resolve();
    };

    dbReq.onerror = () => {
      console.warn('[Offline] IndexedDB unavailable, using memory fallback');
      resolve();
    };
  });
}

// Add pixel to queue (for offline drawing)
export function queuePixel(pixel) {
  offlineQueue.update((queue) => [...queue, { ...pixel, timestamp: Date.now() }]);
  saveToDB(pixel);
  console.log('[Offline] Queued pixel:', pixel);
}

// Get all queued pixels
export function getQueuedPixels() {
  let result = [];
  offlineQueue.subscribe((q) => (result = q))();
  return result;
}

// Clear queue after successful sync
export async function clearQueue() {
  offlineQueue.set([]);
  if (db) {
    const tx = db.transaction('queued_pixels', 'readwrite');
    tx.objectStore('queued_pixels').clear();
  }
  console.log('[Offline] Queue cleared');
}

// Cache a canvas chunk for offline access
export function cacheChunk(chunkId, pixels) {
  if (!db) return;
  const tx = db.transaction('cached_chunks', 'readwrite');
  tx.objectStore('cached_chunks').put({
    chunkId,
    pixels,
    timestamp: Date.now(),
  });
}

// Retrieve cached chunk
export async function getCachedChunk(chunkId) {
  return new Promise((resolve) => {
    if (!db) {
      resolve(null);
      return;
    }

    const tx = db.transaction('cached_chunks', 'readonly');
    const req = tx.objectStore('cached_chunks').get(chunkId);

    req.onsuccess = () => {
      resolve(req.result);
    };
    req.onerror = () => {
      resolve(null);
    };
  });
}

// Save pixel to IndexedDB
function saveToDB(pixel) {
  if (!db) return;

  const tx = db.transaction('queued_pixels', 'readwrite');
  tx.objectStore('queued_pixels').add({
    ...pixel,
    timestamp: Date.now(),
  });
}

// Load queue from IndexedDB on startup
function loadQueueFromDB() {
  if (!db) return;

  const tx = db.transaction('queued_pixels', 'readonly');
  const req = tx.objectStore('queued_pixels').getAll();

  req.onsuccess = () => {
    const pixels = req.result;
    if (pixels.length > 0) {
      offlineQueue.set(pixels);
      console.log('[Offline] Loaded', pixels.length, 'queued pixels from DB');
    }
  };
}

// Clear old cache entries (older than 7 days)
export async function clearOldCache() {
  if (!db) return;

  const cutoffTime = Date.now() - 7 * 24 * 60 * 60 * 1000;
  const tx = db.transaction('cached_chunks', 'readwrite');
  const store = tx.objectStore('cached_chunks');

  store.getAll().onsuccess = (e) => {
    e.target.result.forEach((chunk) => {
      if (chunk.timestamp < cutoffTime) {
        store.delete(chunk.chunkId);
      }
    });
  };
}
