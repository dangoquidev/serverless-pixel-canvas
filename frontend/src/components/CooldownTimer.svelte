<script>
  import {
    pixelsRemaining,
    MAX_PIXELS,
    REFILL_SECONDS,
    tickCooldown,
    getSecondsUntilNextRefill,
  } from "../stores/canvasStore.js";
  import { onMount } from "svelte";

  let displayString = "READY";
  let isCooling = false;
  let secondsUntilNext = REFILL_SECONDS;

  $: isCooling = $pixelsRemaining <= 0;

  const refreshDisplay = () => {
    secondsUntilNext = getSecondsUntilNextRefill();

    if ($pixelsRemaining === MAX_PIXELS) {
      displayString = `${MAX_PIXELS} PIXELS (MAX)`;
    } else if ($pixelsRemaining > 0) {
      displayString = `${$pixelsRemaining} LEFT (+1 in ${secondsUntilNext}s)`;
    } else {
      displayString = `WAIT: ${secondsUntilNext}s`;
    }
  };

  $: refreshDisplay();

  onMount(() => {
    const interval = setInterval(() => {
      tickCooldown();
      refreshDisplay();
    }, 1000);

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
    background: white;
    color: black;
    padding: 10px 20px;
    z-index: 100;
    transition: background-color 0.2s;
  }

  .cooldown-tracker.cooling {
    background: var(--accent-color, #ff4444);
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
