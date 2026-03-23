<script>
  import "./app.css";
  import { onMount } from "svelte";
  import { isConnected, wsError } from "./stores/wsStore.js";
  import { isOffline, queueSize } from "./stores/offlineStore.js";

  import AccountButton from "./components/AccountButton.svelte";
  import AuthModal from "./components/AuthModal.svelte";
  import Toolbar from "./components/Toolbar.svelte";
  import CooldownTimer from "./components/CooldownTimer.svelte";
  import Canvas from "./components/Canvas.svelte";

  let isLoading = true;

  onMount(() => {
    setTimeout(() => {
      isLoading = false;
    }, 800);
  });
</script>

<main>
  <AccountButton />
  <AuthModal />
  <Toolbar />
  <CooldownTimer />

  <Canvas />

  {#if isLoading}
    <div class="modal-overlay">
      <div class="panel loader">
        <h2 class="glitch" data-text="SYSTEM BOOT">SYSTEM BOOT</h2>
        <div class="progress-bar"><div class="fill"></div></div>
        <span class="blink">INITIALIZING CANVAS...</span>
      </div>
    </div>
  {/if}

  {#if $wsError}
    <div class="notification error">
      <strong>⚠️ CONNECTION ERROR:</strong>
      {$wsError}
    </div>
  {:else if !$isConnected && !isLoading}
    <div class="notification warning">
      <span class="blink">●</span> OFFLINE - RECONNECTING
    </div>
  {/if}

  {#if $queueSize > 0}
    <div class="queue-indicator" role="status" aria-live="polite">
      <strong>OFFLINE QUEUE:</strong>
      {$queueSize} pixel{$queueSize > 1 ? "s" : ""} pending
      {#if $isOffline}
        <span class="blink"> · waiting for connection</span>
      {/if}
    </div>
  {/if}
</main>

<style>
  :global(body) {
    margin: 0;
    padding: 0;
    background: #1a1a1a;
    color: #00ff00; /* Retro terminal green */
    font-family: "Courier New", Courier, monospace;
    overflow: hidden;
  }

  main {
    width: 100vw;
    height: 100vh;
    position: relative;
  }

  /* Status Notifications */
  .notification {
    position: fixed;
    top: 20px;
    left: 50%;
    transform: translateX(-50%);
    padding: 10px 20px;
    border: 2px solid currentColor;
    z-index: 2000;
    font-size: 0.8rem;
    text-transform: uppercase;
    background: rgba(0, 0, 0, 0.9);
  }

  .warning {
    color: #ffcc00;
  }
  .error {
    color: #ff0044;
  }

  .queue-indicator {
    position: fixed;
    top: 72px;
    right: 20px;
    padding: 10px 14px;
    border: 2px solid #00e5ff;
    background: rgba(0, 0, 0, 0.9);
    color: #00e5ff;
    z-index: 2000;
    font-size: 0.75rem;
    text-transform: uppercase;
  }

  /* Loading Overlay */
  .modal-overlay {
    position: fixed;
    inset: 0;
    background: #000;
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 9999;
  }

  .loader {
    text-align: center;
    min-width: 300px;
  }

  .progress-bar {
    width: 100%;
    height: 4px;
    background: #333;
    margin: 20px 0;
    position: relative;
    overflow: hidden;
  }

  .fill {
    width: 100%;
    height: 100%;
    background: #00ff00;
    animation: load 0.8s ease-in-out forwards;
    transform-origin: left;
  }

  @keyframes load {
    0% {
      transform: scaleX(0);
    }
    100% {
      transform: scaleX(1);
    }
  }

  .blink {
    animation: blink 1s step-end infinite;
    font-size: 0.7rem;
  }

  @keyframes blink {
    50% {
      opacity: 0;
    }
  }
</style>
