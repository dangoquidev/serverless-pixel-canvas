<script>
  import { onMount, onDestroy } from "svelte";
  import {
    selectedColor,
    cooldownRemaining,
    loadedChunks,
  } from "../stores/canvasStore.js";
  import { fetchChunk, drawPixel } from "../utils/api.js";
  import { connectWebSocket, disconnectWebSocket } from "../stores/wsStore.js";
  import { CanvasEngine } from "../utils/CanvasEngine.js";

  // Constants
  const CANVAS_SIZE = 1000;
  const CHUNK_SIZE = 100;

  let canvasRef;
  let engine;
  let isDragging = false;
  let hasDragged = false;
  let dragStart = { x: 0, y: 0, vx: 0, vy: 0 };

  onMount(() => {
    engine = new CanvasEngine(canvasRef, CANVAS_SIZE, CANVAS_SIZE, CHUNK_SIZE);
    // 1. Set a high initial scale (Zoomed in)
    engine.scale = 6;

    // Formula: (ScreenCenter) - (TargetPixel * Scale)
    engine.viewX = window.innerWidth / 2 - 500 * engine.scale;
    engine.viewY = window.innerHeight / 2 - 500 * engine.scale;

    // 3. Now refresh - this will only fetch chunks around the center
    refreshVisibleArea();

    connectWebSocket(import.meta.env.VITE_WSS_URL);
    window.addEventListener("ws_binary_update", handleWSUpdate);
    window.addEventListener("resize", handleResize);
  });

  onDestroy(() => {
    window.removeEventListener("ws_binary_update", handleWSUpdate);
    window.removeEventListener("resize", refreshVisibleArea);
    disconnectWebSocket();
  });

  // --- Data Handling ---

  function handleResize() {
    engine.canvas.width = window.innerWidth;
    engine.canvas.height = window.innerHeight;
    refreshVisibleArea();
  }

  function handleWSUpdate(e) {
    const view = e.detail; // Uint8Array [CX, CY, LX, LY, R, G, B]
    for (let i = 0; i < view.length; i += 7) {
      const gx = view[i] * CHUNK_SIZE + view[i + 2];
      const gy = view[i + 1] * CHUNK_SIZE + view[i + 3];
      engine.updatePixel(gx, gy, view[i + 4], view[i + 5], view[i + 6]);
    }
    engine.render();
  }

  async function refreshVisibleArea() {
    const { minCx, minCy, maxCx, maxCy } = engine.getVisibleChunks(
      window.innerWidth,
      window.innerHeight,
    );
    let chunksToFetch = [];

    loadedChunks.update((set) => {
      for (let cx = minCx; cx <= maxCx; cx++) {
        for (let cy = minCy; cy <= maxCy; cy++) {
          if (!set.has(`${cx},${cy}`)) {
            set.add(`${cx},${cy}`);
            chunksToFetch.push({ cx, cy });
          }
        }
      }
      return set;
    });

    if (chunksToFetch.length > 0) {
      // Load in batches of 4 to prevent AWS Lambda throttling
      for (let i = 0; i < chunksToFetch.length; i += 4) {
        const batch = chunksToFetch.slice(i, i + 4);
        await Promise.all(
          batch.map(async ({ cx, cy }) => {
            const buffer = await fetchChunk(cx, cy);
            const view = new Uint8Array(buffer);
            for (let j = 0; j < view.length; j += 5) {
              engine.updatePixel(
                cx * CHUNK_SIZE + view[j],
                cy * CHUNK_SIZE + view[j + 1],
                view[j + 2],
                view[j + 3],
                view[j + 4],
              );
            }
          }),
        );
        engine.render();
      }
    } else {
      engine.render();
    }
  }

  // --- Interaction Handlers ---

  function handleMouseDown(e) {
    isDragging = true;
    hasDragged = false;
    dragStart = {
      x: e.clientX,
      y: e.clientY,
      vx: engine.viewX,
      vy: engine.viewY,
    };
  }

  function handleMouseUp() {
    if (isDragging) {
      isDragging = false;
      clearTimeout(refreshTimeout);
      refreshVisibleArea();
    }
  }

  async function handleCanvasClick(e) {
    if (hasDragged || $cooldownRemaining > 0) return;
    const { x, y } = engine.screenToPixel(e.clientX, e.clientY);
    if (x === null) return;

    const color = $selectedColor;
    const { r, g, b } = engine.hexToRgb(color);

    // Optimistic UI
    engine.updatePixel(x, y, r, g, b);
    engine.render();
    cooldownRemaining.set(10); // 10s cooldown example

    try {
      await drawPixel(x, y, color);
    } catch (err) {
      console.error(err);
    }
  }
  let refreshTimeout;

  /**
   * Prevents spamming the API by waiting for the user to stop interacting
   */
  function debouncedRefresh() {
    clearTimeout(refreshTimeout);
    refreshTimeout = setTimeout(() => {
      refreshVisibleArea();
    }, 150);
  }

  function handleWheel(e) {
    const zoomDir = e.deltaY > 0 ? 0.9 : 1.1;
    const newScale = Math.min(Math.max(0.5, engine.scale * zoomDir), 50);
    engine.scale = newScale;

    engine.render();

    debouncedRefresh();
  }

  function handleMouseMove(e) {
    if (isDragging) {
      const dx = e.clientX - dragStart.x;
      const dy = e.clientY - dragStart.y;

      if (Math.abs(dx) > 3 || Math.abs(dy) > 3) hasDragged = true;

      engine.viewX = dragStart.vx + dx;
      engine.viewY = dragStart.vy + dy;
      engine.render();

      debouncedRefresh();
    } else {
      const { x, y } = engine.screenToPixel(e.clientX, e.clientY);
      if (x !== null) {
        canvasRef.style.setProperty("--hover-x", `${x}`);
        canvasRef.style.setProperty("--hover-y", `${y}`);
        canvasRef.style.setProperty("--hover-display", "block");
      } else {
        canvasRef.style.setProperty("--hover-display", "none");
      }
    }
  }
</script>

<svelte:window on:mouseup={handleMouseUp} />

<main
  role="application"
  aria-label="Pixel canvas"
  on:mousedown={handleMouseDown}
  on:mousemove={handleMouseMove}
  on:wheel|preventDefault={handleWheel}
>
  <canvas
    bind:this={canvasRef}
    width={window.innerWidth}
    height={window.innerHeight}
    on:click={handleCanvasClick}
    class:grabbing={isDragging}
  ></canvas>
</main>

<style>
  main {
    width: 100vw;
    height: 100vh;
    background: #1a1a1a;
    overflow: hidden;
    touch-action: none;
  }

  canvas {
    display: block;
    image-rendering: pixelated;
    cursor: crosshair;
  }

  canvas.grabbing {
    cursor: grabbing;
  }
</style>
