<script>
  import { onMount, onDestroy } from "svelte";
  import {
    selectedColor,
    loadedChunks,
    pixelsRemaining,
    consumePixel,
    refundPixel,
  } from "../stores/canvasStore.js";
  import { fetchChunk, drawPixel } from "../utils/api.js";
  import { connectWebSocket, disconnectWebSocket } from "../stores/wsStore.js";
  import { CanvasEngine } from "../utils/CanvasEngine.js";

  // --- Constants & State ---
  const CANVAS_SIZE = 1000;
  const CHUNK_SIZE = 100;

  let canvasRef;
  let hoverRef;
  let engine;
  let isDragging = false;
  let hasDragged = false;
  let dragStart = { x: 0, y: 0, vx: 0, vy: 0 };
  let refreshTimeout;

  // --- Lifecycle ---
  onMount(() => {
    engine = new CanvasEngine(canvasRef, CANVAS_SIZE, CANVAS_SIZE, CHUNK_SIZE);

    // Initial Zoom and Center
    engine.scale = 6;
    engine.viewX = window.innerWidth / 2 - (CANVAS_SIZE / 2) * engine.scale;
    engine.viewY = window.innerHeight / 2 - (CANVAS_SIZE / 2) * engine.scale;

    refreshVisibleArea();

    connectWebSocket(import.meta.env.VITE_WSS_URL);
    window.addEventListener("ws_binary_update", handleWSUpdate);
    window.addEventListener("resize", handleResize);
  });

  onDestroy(() => {
    window.removeEventListener("ws_binary_update", handleWSUpdate);
    window.removeEventListener("resize", handleResize);
    disconnectWebSocket();
    clearTimeout(refreshTimeout);
  });

  // --- Data Handling ---

  function handleResize() {
    engine.canvas.width = window.innerWidth;
    engine.canvas.height = window.innerHeight;
    refreshVisibleArea();
  }

  function handleWSUpdate(e) {
    engine.applyBinaryBuffer(e.detail);
    engine.render();
  }

  async function refreshVisibleArea() {
    const visibleBounds = engine.getVisibleChunks(
      window.innerWidth,
      window.innerHeight,
    );
    const chunksToFetch = getUnloadedChunks(visibleBounds);

    if (chunksToFetch.length === 0) {
      engine.render();
      return;
    }

    await loadChunksInBatches(chunksToFetch, 4);
  }

  function getUnloadedChunks({ minCx, minCy, maxCx, maxCy }) {
    const missingChunks = [];

    loadedChunks.update((set) => {
      for (let cx = minCx; cx <= maxCx; cx++) {
        for (let cy = minCy; cy <= maxCy; cy++) {
          const chunkId = `${cx},${cy}`;
          if (!set.has(chunkId)) {
            set.add(chunkId);
            missingChunks.push({ cx, cy });
          }
        }
      }
      return set;
    });

    return missingChunks;
  }

  // --- Network & Rendering ---
  async function loadChunksInBatches(chunks, batchSize = 4) {
    for (let i = 0; i < chunks.length; i += batchSize) {
      const batch = chunks.slice(i, i + batchSize);

      await Promise.all(
        batch.map(async ({ cx, cy }) => {
          try {
            const buffer = await fetchChunk(cx, cy);
            engine.applyBinaryBuffer(new Uint8Array(buffer));
          } catch (error) {
            console.error(`Failed to fetch chunk ${cx},${cy}`, error);
          }
        }),
      );

      engine.render();
    }
  }

  function debouncedRefresh() {
    clearTimeout(refreshTimeout);
    refreshTimeout = setTimeout(() => {
      refreshVisibleArea();
    }, 150);
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
      debouncedRefresh(); // Only fetch new chunks when the user stops dragging
    }
  }

  async function handleCanvasClick(e) {
    if (hasDragged || $pixelsRemaining <= 0) return;

    const { x, y } = engine.screenToPixel(e.clientX, e.clientY);
    if (x === null) return;

    const color = $selectedColor;
    const { r, g, b } = engine.hexToRgb(color);

    const previousPixel = engine.getPixel(x, y);

    if (!consumePixel()) return;

    engine.updatePixel(x, y, r, g, b, 100);
    engine.render();

    try {
      await drawPixel(x, y, color);
    } catch (err) {
      console.error("Failed to draw pixel:", err);

      refundPixel();

      if (previousPixel) {
        engine.updatePixel(
          x,
          y,
          previousPixel.r,
          previousPixel.g,
          previousPixel.b,
          previousPixel.a,
        );
        engine.render();
      }
    }
  }

  function handleWheel(e) {
    const ZOOM_SPEED = 0.002;
    const zoomFactor = Math.exp(-e.deltaY * ZOOM_SPEED);
    const oldScale = engine.scale;
    const newScale = Math.min(Math.max(0.5, oldScale * zoomFactor), 50);

    // Zoom Math Fix: Calculate world pixel under mouse *before* zoom
    const mouseX = e.clientX;
    const mouseY = e.clientY;
    const worldX = (mouseX - engine.viewX) / oldScale;
    const worldY = (mouseY - engine.viewY) / oldScale;

    // Apply new scale
    engine.scale = newScale;

    // Adjust view so the same world pixel stays under the mouse cursor
    engine.viewX = mouseX - worldX * newScale;
    engine.viewY = mouseY - worldY * newScale;

    engine.render();

    if (hoverRef) hoverRef.style.display = "none";
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

      if (hoverRef) hoverRef.style.display = "none";
    } else {
      const { x, y } = engine.screenToPixel(e.clientX, e.clientY);

      if (x !== null && hoverRef) {
        const screenX = engine.viewX + x * engine.scale;
        const screenY = engine.viewY + y * engine.scale;

        hoverRef.style.transform = `translate(${screenX}px, ${screenY}px)`;
        hoverRef.style.width = `${engine.scale}px`;
        hoverRef.style.height = `${engine.scale}px`;
        hoverRef.style.display = "block";
      } else if (hoverRef) {
        hoverRef.style.display = "none";
      }
    }
  }
</script>

<svelte:window on:mouseup={handleMouseUp} />

<main>
  <canvas
    bind:this={canvasRef}
    width={window.innerWidth}
    height={window.innerHeight}
    aria-label="Interactive pixel canvas"
    tabindex="0"
    on:mousedown={handleMouseDown}
    on:mousemove={handleMouseMove}
    on:wheel|preventDefault={handleWheel}
    on:click={handleCanvasClick}
    class:grabbing={isDragging}
  ></canvas>
  <div
    bind:this={hoverRef}
    class="hover-box"
    style="--preview-color: {$selectedColor}80;"
  ></div>
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
  .hover-box {
    position: absolute;
    top: 0;
    left: 0;
    pointer-events: none;
    box-sizing: border-box;
    border: 1px solid white;
    box-shadow:
      0 0 0 1px black inset,
      0 0 0 1px black;
    display: none;
    z-index: 10;
    will-change: transform;
    background-color: var(--preview-color);
  }
</style>
