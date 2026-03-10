<script>
  import {
    authToken,
    authError,
    clearAuthError,
    login,
  } from "../stores/authStore.js";

  $: isLoggedIn = !!$authToken;
  let dismissedByUser = false;

  // Reset dismissed state when user logs in (so modal shows again after logout)
  $: if ($authToken) dismissedByUser = false;

  $: showModal = !isLoggedIn && !dismissedByUser;

  function closeModal() {
    dismissedByUser = true;
  }

  function handleOverlayClick(e) {
    if (e.target === e.currentTarget) closeModal();
  }
</script>

{#if showModal}
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div class="modal-overlay" on:click={handleOverlayClick} role="dialog" aria-modal="true" aria-labelledby="auth-modal-title" tabindex="-1">
    <div class="panel login-panel">
      <button class="close-btn" on:click={closeModal} aria-label="Close">×</button>
      <h2 id="auth-modal-title">Authentication Required</h2>
      <p>You must login with Discord to draw pixels on the canvas.</p>
      {#if $authError}
        <div class="error-message" role="alert">
          {$authError}
        </div>
        <button class="text-btn" on:click={clearAuthError}>Dismiss</button>
        <br />
      {/if}
      <button class="brutalist-btn" on:click={login}>
        Login via Discord
      </button>
    </div>
  </div>
{/if}

<style>
  .login-panel {
    position: relative;
    text-align: center;
    max-width: 400px;
  }

  .close-btn {
    position: absolute;
    top: 10px;
    right: 10px;
    width: 36px;
    height: 36px;
    padding: 0;
    font-size: 28px;
    line-height: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    background: white;
    border: 2px solid black;
  }

  .close-btn:hover {
    background: var(--accent-color);
    color: white;
  }

  .error-message {
    color: #c00;
    font-size: 0.95rem;
    margin: 0.5rem 0;
    padding: 0.5rem;
    background: #fff5f5;
    border: 2px solid #c00;
  }

  .text-btn {
    background: none;
    border: none;
    cursor: pointer;
    color: var(--accent-color);
    text-decoration: underline;
    font-size: 0.9rem;
    padding: 0;
  }

  .text-btn:hover {
    color: black;
  }

  .brutalist-btn {
    width: 100%;
    background-color: var(--accent-color);
    color: white;
    border: 4px solid black;
    font-size: 1.2rem;
    padding: 1rem;
  }

  .brutalist-btn:hover {
    background-color: black;
    color: var(--accent-color);
  }
</style>
