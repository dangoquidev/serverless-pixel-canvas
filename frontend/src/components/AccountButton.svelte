<script>
  import { onMount } from "svelte";
  import { authToken, login, logout } from "../stores/authStore.js";

  let menuOpen = false;

  function toggleMenu() {
    menuOpen = !menuOpen;
  }

  function handleLogin() {
    menuOpen = false;
    login();
  }

  function handleLogout() {
    menuOpen = false;
    logout();
  }

  function handleClickOutside(e) {
    if (menuOpen && !e.target.closest(".account-menu-wrapper")) {
      menuOpen = false;
    }
  }

  onMount(() => {
    document.addEventListener("click", handleClickOutside);
    return () => document.removeEventListener("click", handleClickOutside);
  });
</script>

<div class="account-menu-wrapper">
  <button
    class="account-btn"
    on:click={toggleMenu}
    title={$authToken ? "Account menu" : "Account menu"}
    aria-label="Account menu"
    aria-expanded={menuOpen}
    aria-haspopup="true"
  >
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
      stroke-linecap="round"
      stroke-linejoin="round"
    >
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </svg>
  </button>

  {#if menuOpen}
    <div class="account-menu panel" role="menu">
      {#if $authToken}
        <button class="menu-item" on:click={handleLogout} role="menuitem">
          LOGOUT
        </button>
      {:else}
        <button class="menu-item" on:click={handleLogin} role="menuitem">
          LOGIN WITH DISCORD
        </button>
      {/if}
    </div>
  {/if}
</div>

<style>
  .account-menu-wrapper {
    position: fixed;
    top: 20px;
    left: 20px;
    z-index: 1000;
  }

  .account-btn {
    width: 48px;
    height: 48px;
    padding: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: white;
    border: 4px solid black;
    box-shadow: 4px 4px 0px black;
  }

  .account-btn:hover {
    background: var(--accent-color);
    color: white;
  }

  .account-menu {
    position: absolute;
    top: calc(100% + 8px);
    left: 0;
    min-width: 180px;
    padding: 8px 0;
  }

  .menu-item {
    display: block;
    width: 100%;
    text-align: left;
    padding: 10px 16px;
    border: none;
    border-bottom: 2px solid black;
    border-radius: 0;
    box-shadow: none;
  }

  .menu-item:last-child {
    border-bottom: none;
  }

  .menu-item:hover {
    background: var(--accent-color);
    color: white;
  }
</style>
