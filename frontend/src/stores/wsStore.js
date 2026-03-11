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
    };

    socket.onmessage = (event) => {
        try {
            const parsedData = JSON.parse(event.data);
            const messages = Array.isArray(parsedData) ? parsedData : [parsedData];

            const newPixels = messages
                .filter(msg => msg.type === 'pixel_update')
                .map(msg => msg.data);

            if (newPixels.length > 0) {
                window.dispatchEvent(new CustomEvent('pixel_batch_update', { detail: newPixels }));
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
