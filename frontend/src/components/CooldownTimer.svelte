<script>
  import { cooldownRemaining } from "../stores/canvasStore.js";
  import { onMount } from "svelte";

  let displayString = "READY";
  let isCooling = false;

  // Reactively update when cooldownRemaining store changes
  $: {
    if ($cooldownRemaining > 0) {
      isCooling = true;
    }
  }

  // Local tick for the UI timer so we don't pound the Svelte store
  onMount(() => {
    const interval = setInterval(() => {
      if ($cooldownRemaining > 0) {
        cooldownRemaining.update((v) => Math.max(0, v - 100)); // decrease by 100ms

        const secs = Math.ceil($cooldownRemaining / 1000);
        displayString = `WAIT: ${secs}s`;
      } else {
        isCooling = false;
        displayString = "READY TO DRAW";
      }
    }, 100);

    return () => clearInterval(interval);
  });
</script>

<div class="cooldown-tracker panel" class:cooling={isCooling}>
  <span class="status">{displayString}</span>
</div>

<style>
  .cooldown-tracker {
    position: fixed;
    top: 20px;
    right: 20px;
    background: #00ff00;
    padding: 10px 20px;
    z-index: 100;
    transition: background-color 0.2s;
  }

  .cooldown-tracker.cooling {
    background: var(--accent-color);
    color: white;
    animation: shake 0.5s;
  }

  .status {
    font-weight: bold;
    font-size: 1.2rem;
  }

  @keyframes shake {
    0% {
      transform: translate(1px, 1px) rotate(0deg);
    }
    10% {
      transform: translate(-1px, -2px) rotate(-1deg);
    }
    20% {
      transform: translate(-3px, 0px) rotate(1deg);
    }
    30% {
      transform: translate(3px, 2px) rotate(0deg);
    }
    40% {
      transform: translate(1px, -1px) rotate(1deg);
    }
    50% {
      transform: translate(-1px, 2px) rotate(-1deg);
    }
    60% {
      transform: translate(-3px, 1px) rotate(0deg);
    }
    70% {
      transform: translate(3px, 1px) rotate(-1deg);
    }
    80% {
      transform: translate(-1px, -1px) rotate(1deg);
    }
    90% {
      transform: translate(1px, 2px) rotate(0deg);
    }
    100% {
      transform: translate(1px, -2px) rotate(-1deg);
    }
  }
</style>
