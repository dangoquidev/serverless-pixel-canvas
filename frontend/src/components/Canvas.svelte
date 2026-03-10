<script>
  import { onMount, onDestroy } from "svelte";
  import { selectedColor, cooldownRemaining } from "../stores/canvasStore.js";
  import { drawPixel } from "../utils/api.js";

  // Constants identical to backend chunking
  const CANVAS_WIDTH = 1000;
  const CANVAS_HEIGHT = 1000;
  const CHUNK_SIZE = 100;
  const RATE_LIMIT_MS = 10000; // 10 seconds

  export let initialPixels = []; // Passed in from App.svelte on load

  let canvasRef;
  let ctx;

  // Viewport state
  let scale = 1;
  let translateX = 0;
  let translateY = 0;
  let isDragging = false;
  let hasDragged = false; // True only when user actually moved while panning (blocks spurious click)
  let startDragX = 0;
  let startDragY = 0;
  let startMouseX = 0;
  let startMouseY = 0;
  const DRAG_THRESHOLD = 5; // Pixels of movement to count as a drag (not a click)

  let hoveredPixel = null; // { x, y } or null

  onMount(() => {
    ctx = canvasRef.getContext("2d", { alpha: false });
    // Fill background white
    ctx.fillStyle = "#FFFFFF";
    ctx.fillRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);

    // Draw initial state
    renderPixels(initialPixels);

    // Listen for WebSocket real-time updates (bypassing Svelte reactivity)
    window.addEventListener("pixel_update", handleLiveUpdate);
  });

  onDestroy(() => {
    window.removeEventListener("pixel_update", handleLiveUpdate);
  });

  // --- Drawing Logic ---

  function renderPixels(pixels) {
    if (!ctx) return;
    pixels.forEach((p) => {
      // p is typically in format: { PixelId: "PIXEL#x#y", color: "#Hex" }
      const parts = p.PixelId.split("#");
      if (parts.length === 3) {
        const x = parseInt(parts[1], 10);
        const y = parseInt(parts[2], 10);

        ctx.fillStyle = p.color;
        ctx.fillRect(x, y, 1, 1);
      }
    });
  }

  function handleLiveUpdate(event) {
    // detail: { PixelId: "PIXEL#x#y", color: "#Hex" }
    renderPixels([event.detail]);
  }

  async function handleCanvasClick(e) {
    // Prevent drawing if user was panning (not a simple click) or on cooldown
    if (hasDragged || $cooldownRemaining > 0) return;

    const rect = canvasRef.getBoundingClientRect();
    // Calculate true X/Y based on CSS transform scale
    const x = Math.floor((e.clientX - rect.left) / scale);
    const y = Math.floor((e.clientY - rect.top) / scale);

    if (x >= 0 && x < CANVAS_WIDTH && y >= 0 && y < CANVAS_HEIGHT) {
      const colorToDraw = $selectedColor;

      // Optimistic update locally
      ctx.fillStyle = colorToDraw;
      ctx.fillRect(x, y, 1, 1);

      // Set cooldown immediately
      cooldownRemaining.set(RATE_LIMIT_MS);

      try {
        await drawPixel(x, y, colorToDraw);
      } catch (err) {
        console.error("Failed to draw pixel:", err);
        alert(`Error: ${err.message}`);
        // In a perfect app, we'd revert the optimistic update here.
      }
    }
  }

  // --- Pan & Zoom Logic ---

  function handleWheel(e) {
    e.preventDefault();
    const zoomSensitivity = 0.001;
    const delta = e.deltaY * zoomSensitivity;

    // Only allow zoom between 0.5x and 20x (so pixels are huge)
    const newScale = Math.min(Math.max(0.5, scale - delta), 20);

    // rudimentary zoom toward center
    scale = newScale;
  }

  function startPan(e) {
    isDragging = true;
    hasDragged = false;
    startMouseX = e.clientX;
    startMouseY = e.clientY;
    startDragX = e.clientX - translateX;
    startDragY = e.clientY - translateY;
  }

  function pan(e) {
    if (!isDragging) return;
    // Mark as drag only after moving beyond threshold (avoids blocking simple clicks)
    const dx = e.clientX - startMouseX;
    const dy = e.clientY - startMouseY;
    if (Math.abs(dx) > DRAG_THRESHOLD || Math.abs(dy) > DRAG_THRESHOLD) {
      hasDragged = true;
    }
    translateX = e.clientX - startDragX;
    translateY = e.clientY - startDragY;
  }

  function stopPan() {
    isDragging = false;
  }

  function clientToPixel(clientX, clientY) {
    if (!canvasRef) return null;
    const rect = canvasRef.getBoundingClientRect();
    const x = Math.floor((clientX - rect.left) / scale);
    const y = Math.floor((clientY - rect.top) / scale);
    if (x >= 0 && x < CANVAS_WIDTH && y >= 0 && y < CANVAS_HEIGHT) {
      return { x, y };
    }
    return null;
  }

  function handleMouseMove(e) {
    if (isDragging) {
      pan(e);
    } else {
      hoveredPixel = clientToPixel(e.clientX, e.clientY);
    }
  }

  function handleMouseLeave() {
    stopPan();
    hoveredPixel = null;
  }
</script>

<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
<div
  class="canvas-container"
  role="application"
  aria-label="Pixel canvas"
  on:wheel|preventDefault={handleWheel}
  on:mousedown={startPan}
  on:mousemove={handleMouseMove}
  on:mouseup={stopPan}
  on:mouseleave={handleMouseLeave}
>
  <!-- Wrapper with transform keeps canvas + hover overlay aligned -->
  <div
    class="canvas-wrapper"
    style="transform: translate({translateX}px, {translateY}px) scale({scale});"
  >
    <canvas
      bind:this={canvasRef}
      width={CANVAS_WIDTH}
      height={CANVAS_HEIGHT}
      on:click={handleCanvasClick}
    ></canvas>
    {#if hoveredPixel}
      <div
        class="pixel-hover"
        style="left: {hoveredPixel.x + 4}px; top: {hoveredPixel.y + 4}px;"
      ></div>
    {/if}
  </div>
</div>

<style>
  .canvas-container {
    width: 100vw;
    height: 100vh;
    overflow: hidden;
    background-color: #e0e0e0;
    cursor: grab;
    position: relative;
  }

  .canvas-container:active {
    cursor: grabbing;
  }

  .canvas-wrapper {
    position: relative;
    display: inline-block;
    transform-origin: 0 0;
  }

  canvas {
    display: block;
    /* Pixelated rendering is CRITICAL for a canvas app so it doesn't blur when zoomed */
    image-rendering: pixelated;
    box-shadow: 10px 10px 0px rgba(0, 0, 0, 0.5);
    border: 4px solid black;
    cursor: crosshair;
  }

  .pixel-hover {
    position: absolute;
    width: 1px;
    height: 1px;
    pointer-events: none;
    box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.7);
    /* outline works at any zoom; box-shadow gives a visible border */
  }
</style>
