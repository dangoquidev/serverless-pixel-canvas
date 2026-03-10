<script>
  import './app.css';
  import { onMount } from 'svelte';
  import { isConnected, connectWebSocket } from './stores/wsStore.js';
  import { fetchCanvas } from './utils/api.js';

  import AuthModal from './components/AuthModal.svelte';
  import Toolbar from './components/Toolbar.svelte';
  import CooldownTimer from './components/CooldownTimer.svelte';
  import Canvas from './components/Canvas.svelte';

  let initialCanvasData = [];
  let isLoading = true;
  let connectionError = null;

  onMount(async () => {
      try {
          // 1. Fetch initial state of the board
          const response = await fetchCanvas();
          // Assuming response returns an array of pixel items
          initialCanvasData = response.pixels || [];
          
          // 2. Connect to the WebSocket stream
          const WSS_URL = import.meta.env.VITE_WSS_URL || "wss://localhost/production";
          connectWebSocket(WSS_URL);
          
      } catch (err) {
          console.error("Initialization failed:", err);
          connectionError = err.message;
      } finally {
          isLoading = false;
      }
  });

</script>

<main>
  <AuthModal />
  <Toolbar />
  <CooldownTimer />

  {#if isLoading}
      <div class="modal-overlay">
          <div class="panel">
              <h2>LOADING CANVAS</h2>
              <span class="blink">Please wait...</span>
          </div>
      </div>
  {:else if connectionError}
      <div class="modal-overlay">
          <div class="panel">
              <h2>CONNECTION ERROR</h2>
              <p>{connectionError}</p>
          </div>
      </div>
  {:else}
      <Canvas initialPixels={initialCanvasData} />
  {/if}

  {#if !$isConnected && !isLoading && !connectionError}
      <div class="offline-warning panel">
          OFFLINE - RECONNECTING...
      </div>
  {/if}
</main>

<style>
  main {
      width: 100vw;
      height: 100vh;
      position: relative;
      overflow: hidden;
  }

  .blink {
      animation: blink 1s step-end infinite;
  }

  @keyframes blink { 50% { opacity: 0; } }

  .offline-warning {
      position: fixed;
      top: 80px;
      right: 20px;
      background: var(--accent-color);
      color: white;
      z-index: 1000;
  }
</style>
