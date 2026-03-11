import { writable } from 'svelte/store';

export const isConnected = writable(false);
export const wsError = writable(null);

let socket = null;
let reconnectTimer = null;

export const connectWebSocket = (wsUrl) => {
    if (!wsUrl || socket) return;

    socket = new WebSocket(wsUrl);

    socket.binaryType = "arraybuffer";

    socket.onopen = () => {
        isConnected.set(true);
        wsError.set(null);
        if (reconnectTimer) clearTimeout(reconnectTimer);
    };

    socket.onmessage = (event) => {

        const view = new Uint8Array(event.data);

        if (view.length > 0) {
            window.dispatchEvent(new CustomEvent('ws_binary_update', { detail: view }));
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
