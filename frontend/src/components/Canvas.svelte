<script>
    import { onMount, onDestroy } from 'svelte';
    import { selectedColor, cooldownRemaining } from '../stores/canvasStore.js';
    import { drawPixel } from '../utils/api.js';

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
    let startDragX = 0;
    let startDragY = 0;

    onMount(() => {
        ctx = canvasRef.getContext('2d', { alpha: false });
        // Fill background white
        ctx.fillStyle = '#FFFFFF';
        ctx.fillRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);
        
        // Draw initial state
        renderPixels(initialPixels);

        // Listen for WebSocket real-time updates (bypassing Svelte reactivity)
        window.addEventListener('pixel_update', handleLiveUpdate);
    });

    onDestroy(() => {
        window.removeEventListener('pixel_update', handleLiveUpdate);
    });

    // --- Drawing Logic ---

    function renderPixels(pixels) {
        if (!ctx) return;
        pixels.forEach(p => {
            // p is typically in format: { PixelId: "PIXEL#x#y", color: "#Hex" }
            const parts = p.PixelId.split('#');
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
        // Prevent drawing if dragging or on cooldown
        if (isDragging || $cooldownRemaining > 0) return;

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
        startDragX = e.clientX - translateX;
        startDragY = e.clientY - translateY;
    }

    function pan(e) {
        if (!isDragging) return;
        translateX = e.clientX - startDragX;
        translateY = e.clientY - startDragY;
    }

    function stopPan() {
        // Small timeout to prevent the mouseup from triggering a click event
        setTimeout(() => {
            isDragging = false;
        }, 10);
    }

</script>

<div 
    class="canvas-container"
    on:wheel|preventDefault={handleWheel}
    on:mousedown={startPan}
    on:mousemove={pan}
    on:mouseup={stopPan}
    on:mouseleave={stopPan}
>
    <!-- Use CSS transform for pan/zoom instead of re-rendering canvas context -->
    <canvas 
        bind:this={canvasRef}
        width={CANVAS_WIDTH}
        height={CANVAS_HEIGHT}
        style="transform: translate({translateX}px, {translateY}px) scale({scale});"
        on:click={handleCanvasClick}
    ></canvas>
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

    canvas {
        transform-origin: 0 0;
        /* Pixelated rendering is CRITICAL for a canvas app so it doesn't blur when zoomed */
        image-rendering: pixelated; 
        box-shadow: 10px 10px 0px rgba(0,0,0,0.5);
        border: 4px solid black;
        cursor: crosshair;
    }
</style>
