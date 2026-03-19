<script>
  import { onMount, onDestroy } from "svelte";
  import {
    selectedColor,
    cooldownRemaining,
    loadedChunks,
  } from "../stores/canvasStore.js";
  import { isOffline, queueSize } from "../stores/offlineStore.js";
  import { fetchChunk, drawPixel } from "../utils/api.js";

  const CANVAS_WIDTH = 1000;
  const CANVAS_HEIGHT = 1000;
  const CHUNK_SIZE = 100;

  let canvasRef;
  let ctx;

  let scale = 10;
  let translateX = 0;
  let translateY = 0;

  // Interaction state
  let isDragging = false;
  let hasDragged = false;
  let startDrag = { x: 0, y: 0, tx: 0, ty: 0 };

  // We use CSS variables for hover to avoid Svelte reactivity thrashing on mousemove
  let wrapperRef;

  onMount(() => {
    translateX = window.innerWidth / 2 - (CANVAS_WIDTH / 2) * scale;
    translateY = window.innerHeight / 2 - (CANVAS_HEIGHT / 2) * scale;

    ctx = canvasRef.getContext("2d", { alpha: false });
    ctx.fillStyle = "#FFFFFF";
    ctx.fillRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);

    calculateVisibleChunks();

    window.addEventListener("pixel_batch_update", handleLiveUpdate);
    window.addEventListener("resize", handleWindowResize);
  });

  onDestroy(() => {
    window.removeEventListener("pixel_batch_update", handleLiveUpdate);
    window.removeEventListener("resize", handleWindowResize);
  });

  // --- Window Resize Handler ---

  function handleWindowResize() {
    // Recalculate visible chunks when window resizes since viewport changed
    calculateVisibleChunks();
  }

  // --- Optimized Rendering ---

  function handleLiveUpdate(e) {
    renderPixels(e.detail);
  }

  function renderPixels(pixels) {
    if (!ctx) return;

    // BATCH DRAWING: Much faster than switching context state per pixel
    pixels.forEach((p) => {
      // Fast string parsing: "PIXEL#150#200" -> x: 150, y: 200
      const firstHash = p.PixelId.indexOf("#");
      const secondHash = p.PixelId.indexOf("#", firstHash + 1);
      const x = parseInt(p.PixelId.substring(firstHash + 1, secondHash), 10);
      const y = parseInt(p.PixelId.substring(secondHash + 1), 10);

      ctx.fillStyle = p.color;
      ctx.fillRect(x, y, 1, 1);
    });
  }

  // --- Spatial / Chunking Logic ---

  async function calculateVisibleChunks() {
    if (!wrapperRef) return;

    const viewportWidth = window.innerWidth / scale;
    const viewportHeight = window.innerHeight / scale;
    const startX = -translateX / scale;
    const startY = -translateY / scale;

    const minCx = Math.max(0, Math.floor(startX / CHUNK_SIZE));
    const minCy = Math.max(0, Math.floor(startY / CHUNK_SIZE));
    const maxCx = Math.min(
      9,
      Math.floor((startX + viewportWidth) / CHUNK_SIZE),
    );
    const maxCy = Math.min(
      9,
      Math.floor((startY + viewportHeight) / CHUNK_SIZE),
    );

    const chunksToLoad = [];

    loadedChunks.update((loaded) => {
      for (let cx = minCx; cx <= maxCx; cx++) {
        for (let cy = minCy; cy <= maxCy; cy++) {
          const chunkId = `${cx},${cy}`;
          if (!loaded.has(chunkId)) {
            loaded.add(chunkId);
            chunksToLoad.push({ cx, cy });
          }
        }
      }
      return loaded;
    });

    if (chunksToLoad.length > 0) {
      try {
        // 3. THE AWS THROTTLE FIX: Staggered loading.
        // Instead of firing 16 requests in the same millisecond,
        // we fetch them in tiny batches so AWS Lambda can keep up.
        const BATCH_SIZE = 4;
        for (let i = 0; i < chunksToLoad.length; i += BATCH_SIZE) {
          const batch = chunksToLoad.slice(i, i + BATCH_SIZE);
          const promises = batch.map((c) => fetchChunk(c.cx, c.cy));

          const results = await Promise.all(promises);
          results.forEach((res) => renderPixels(res.pixels));
        }
      } catch (err) {
        console.error("Failed to load chunks", err);
      }
    }
  }

  // --- Interaction Logic ---

  async function handleCanvasClick(e) {
    if (hasDragged || $cooldownRemaining > 0) return;

    const { x, y } = clientToPixel(e.clientX, e.clientY);
    if (x === null) return;

    const colorToDraw = $selectedColor;

    // Optimistic UI
    ctx.fillStyle = colorToDraw;
    ctx.fillRect(x, y, 1, 1);
    cooldownRemaining.set(10000); // 10s cooldown

    try {
      await drawPixel(x, y, colorToDraw);
    } catch (err) {
      alert(`Error: ${err.message}`);
    }
  }

  function handleWheel(e) {
    // Zoom toward mouse pointer logic (simplified)
    const zoomSensitivity = 0.002;
    const newScale = Math.min(
      Math.max(0.5, scale - e.deltaY * zoomSensitivity),
      40,
    );
    scale = newScale;

    // Recalculate chunks after zooming (debounced by rAF naturally via user stop)
    requestAnimationFrame(calculateVisibleChunks);
  }

  function startPan(e) {
    isDragging = true;
    hasDragged = false;
    startDrag = { x: e.clientX, y: e.clientY, tx: translateX, ty: translateY };
  }

  function pan(e) {
    if (!isDragging) return;

    const dx = e.clientX - startDrag.x;
    const dy = e.clientY - startDrag.y;

    if (Math.abs(dx) > 5 || Math.abs(dy) > 5) hasDragged = true;

    // Direct assignment triggers Svelte reactivity, which is fine for transform
    translateX = startDrag.tx + dx;
    translateY = startDrag.ty + dy;
  }

  function stopPan() {
    if (isDragging) {
      isDragging = false;
      calculateVisibleChunks(); // Only check for new chunks when they stop dragging
    }
  }

  function clientToPixel(clientX, clientY) {
    if (!canvasRef) return { x: null, y: null };
    const rect = canvasRef.getBoundingClientRect();
    const x = Math.floor((clientX - rect.left) / scale);
    const y = Math.floor((clientY - rect.top) / scale);

    if (x >= 0 && x < CANVAS_WIDTH && y >= 0 && y < CANVAS_HEIGHT)
      return { x, y };
    return { x: null, y: null };
  }

  function handleMouseMove(e) {
    if (isDragging) {
      pan(e);
    } else {
      // Update CSS variables directly to bypass Svelte virtual DOM diffing for high-frequency events
      const { x, y } = clientToPixel(e.clientX, e.clientY);
      if (x !== null && wrapperRef) {
        wrapperRef.style.setProperty("--hover-x", `${x}px`);
        wrapperRef.style.setProperty("--hover-y", `${y}px`);
        wrapperRef.style.setProperty("--hover-display", "block");
      } else if (wrapperRef) {
        wrapperRef.style.setProperty("--hover-display", "none");
      }
    }
  }
</script>

<svelte:window on:mouseup={stopPan} on:mouseleave={stopPan} />

<!-- Offline Status Indicator -->
{#if $isOffline}
  <div class="offline-indicator">
    📡 Offline | Queued: {$queueSize}
  </div>
{/if}

<div
  class="canvas-container"
  on:wheel|preventDefault={handleWheel}
  on:mousedown={startPan}
  on:mousemove={handleMouseMove}
>
  <div
    bind:this={wrapperRef}
    class="canvas-wrapper"
    style="transform: translate({translateX}px, {translateY}px) scale({scale});"
  >
    <canvas
      bind:this={canvasRef}
      width={CANVAS_WIDTH}
      height={CANVAS_HEIGHT}
      on:click={handleCanvasClick}
    ></canvas>
    <div class="pixel-hover"></div>
  </div>
</div>

<style>
  .offline-indicator {
    position: fixed;
    top: 10px;
    right: 10px;
    background-color: rgba(255, 152, 0, 0.9);
    color: white;
    padding: 12px 16px;
    border-radius: 6px;
    font-weight: bold;
    font-size: 14px;
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
    z-index: 1000;
    animation: pulse-glow 2s infinite;
  }

  @keyframes pulse-glow {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.7; }
  }

  .canvas-container {
    width: 100vw;
    height: 100vh;
    overflow: hidden;
    background-color: #2a2a2a; /* Darker background feels better for a canvas */
    cursor: grab;
    position: relative;
  }
  .canvas-container:active {
    cursor: grabbing;
  }

  .canvas-wrapper {
    position: absolute;
    transform-origin: 0 0;
    /* Hardware acceleration hint */
    will-change: transform;

    /* Default CSS variables for the hover cursor */
    --hover-x: 0px;
    --hover-y: 0px;
    --hover-display: none;
  }

  canvas {
    display: block;
    image-rendering: pixelated;
    box-shadow: 0px 0px 50px rgba(0, 0, 0, 0.5);
    cursor: crosshair;
  }

  .pixel-hover {
    position: absolute;
    top: 0;
    left: 0;
    width: 1px;
    height: 1px;
    display: var(--hover-display);
    transform: translate(var(--hover-x), var(--hover-y));
    pointer-events: none;
    box-shadow:
      0 0 0 0.5px rgba(255, 255, 255, 0.8),
      0 0 0 1px rgba(0, 0, 0, 0.8);
    /* Using transform instead of left/top is MUCH faster for browser rendering */
    will-change: transform;
  }
</style>
