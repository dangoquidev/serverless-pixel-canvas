import { mount } from 'svelte'
import './app.css'
import App from './App.svelte'
import { initializeOfflineDB } from './stores/offlineStore.js'
import { syncQueuedPixels } from './utils/api.js'

const app = mount(App, {
  target: document.getElementById('app'),
})

// Register Service Worker for offline support
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').then((reg) => {
    console.log('Service Worker registered:', reg);
  }).catch((err) => {
    console.warn('Service Worker registration failed:', err);
  });
}

// Initialize offline database
initializeOfflineDB().then(() => {
  console.log('Offline database initialized');

  if (navigator.onLine) {
    syncQueuedPixels().catch((error) => {
      console.warn('Initial offline queue sync failed:', error);
    });
  }
});

export default app
