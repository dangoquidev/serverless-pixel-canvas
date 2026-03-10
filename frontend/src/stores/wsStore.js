import { writable } from 'svelte/store';

export const isConnected = writable(false);
export const wsError = writable(null);

let socket = null;
let reconnectTimer = null;

export const connectWebSocket = (wsUrl) => {
    if (!wsUrl) return;

    if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
        return; // Already connecting or connected
    }

    socket = new WebSocket(wsUrl);

    socket.onopen = () => {
        isConnected.set(true);
        wsError.set(null);
        if (reconnectTimer) {
            clearTimeout(reconnectTimer);
            reconnectTimer = null;
        }
        console.log("WebSocket connected!");
    };

    socket.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);

            // Dispatch a custom event to the window so the Canvas component
            // can pick it up without going through Svelte's reactive engine
            if (data.type === 'pixel_update') {
               window.dispatchEvent(new CustomEvent('pixel_update', { detail: data.data }));
            }
        } catch (e) {
            console.error("Failed to parse WebSocket message:", e);
        }
    };

    socket.onclose = () => {
        isConnected.set(false);
        console.log("WebSocket disconnected. Reconnecting in 3s...");
        socket = null;

        // Auto-reconnect
        if (!reconnectTimer) {
            reconnectTimer = setTimeout(() => {
                connectWebSocket(wsUrl);
            }, 3000);
        }
    };

    socket.onerror = (error) => {
        wsError.set("WebSocket error occurred.");
        console.error("WebSocket Error:", error);
    };
};

export const disconnectWebSocket = () => {
    if (socket) {
        socket.close();
    }
    if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
    }
};
