<script>
  import {
    authToken,
    authError,
    clearAuthError,
    login,
  } from "../stores/authStore.js";

  $: isLoggedIn = !!$authToken;
</script>

{#if !isLoggedIn}
  <div class="modal-overlay">
    <div class="panel login-panel">
      <h2>Authentication Required</h2>
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
    text-align: center;
    max-width: 400px;
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
