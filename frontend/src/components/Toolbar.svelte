<script>
    import { selectedColor } from '../stores/canvasStore.js';
    import { authToken, logout } from '../stores/authStore.js';

    // Top predefined colors
    const palette = [
        '#000000', '#FF0000', '#00FF00', '#0000FF',
        '#FFFF00', '#00FFFF', '#FF00FF', '#FFFFFF'
    ];

    function selectColor(color) {
        selectedColor.set(color);
    }
</script>

<div class="toolbar panel">
    <div class="brand">
        <h1>PixelCanvas <span class="blink">_</span></h1>
    </div>

    <div class="controls">
        <div class="color-picker-group">
            <span class="label">COLOR_PICKER:</span>
            <input type="color" bind:value={$selectedColor} class="color-input">
        </div>
        
        <div class="palette">
            {#each palette as color}
                <!-- svelte-ignore a11y-click-events-have-key-events -->
                <!-- svelte-ignore a11y-no-static-element-interactions -->
                <div 
                    class="swatch" 
                    style="background-color: {color};"
                    class:active={$selectedColor === color}
                    title={color}
                    on:click={() => selectColor(color)}
                ></div>
            {/each}
        </div>
        
        <div class="spacer"></div>
        
        {#if $authToken}
            <button class="logout-btn" on:click={logout}>LOGOUT</button>
        {/if}
    </div>
</div>

<style>
    .toolbar {
        position: fixed;
        bottom: 20px;
        left: 50%;
        transform: translateX(-50%);
        display: flex;
        flex-direction: column;
        gap: 10px;
        z-index: 100;
        width: max-content;
    }

    .brand {
        text-align: center;
        border-bottom: 4px solid black;
        padding-bottom: 5px;
        margin-bottom: 5px;
    }

    h1 {
        margin: 0;
        border-bottom: none;
        padding: 0;
        font-size: 1.5rem;
    }

    .blink {
        animation: blink 1s step-end infinite;
    }

    @keyframes blink { 50% { opacity: 0; } }

    .controls {
        display: flex;
        align-items: center;
        gap: 15px;
    }

    .label {
        font-weight: bold;
    }

    .color-picker-group {
        display: flex;
        align-items: center;
        gap: 10px;
    }

    .color-input {
        width: 40px;
        height: 40px;
        padding: 0;
        border: 4px solid black;
        cursor: crosshair;
    }

    .palette {
        display: flex;
        gap: 5px;
    }

    .swatch {
        width: 30px;
        height: 30px;
        border: 4px solid black;
        cursor: pointer;
        box-shadow: 2px 2px 0px black;
        transition: transform 0.1s;
    }

    .swatch:hover {
        transform: translate(2px, 2px);
        box-shadow: 0px 0px 0px black;
    }
    
    .swatch.active {
        border-color: var(--accent-color);
        border-width: 4px;
    }

    .spacer {
        flex-grow: 1;
        min-width: 20px;
    }

    .logout-btn {
        background: #000;
        color: white;
    }
    
    .logout-btn:hover {
        background: var(--accent-color);
    }
</style>
