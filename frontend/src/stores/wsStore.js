import { writable } from 'svelte/store';

export const isConnected = writable(false);
export const wsError = writable(null);

let socket = null;
let reconnectTimer = null;

export const connectWebSocket = (wsUrl) => {
  console.log("Connecting WebSocket to:", wsUrl);
  if (!wsUrl || socket){
    console.log("WebSocket already connected or URL not provided");
    return;
  }

  socket = new WebSocket(wsUrl);
  socket.binaryType = "arraybuffer";

  socket.onopen = () => {
      console.log("WebSocket connected");
      isConnected.set(true);
      wsError.set(null);
      if (reconnectTimer) clearTimeout(reconnectTimer);
  };

  socket.onmessage = (event) => {
  const binaryString = atob(event.data);
  const len = binaryString.length;
  const view = new Uint8Array(len);

  for (let i = 0; i < len; i++) {
      view[i] = binaryString.charCodeAt(i);
  }

  if (view.length > 0) {
      window.dispatchEvent(new CustomEvent('ws_binary_update', { detail: view }));
  }
};

    socket.onclose = () => {
        isConnected.set(false);
        console.log("WebSocket disconnected. Reconnecting in 3s...");
        socket = null;

        // Auto-reconnect: Clear existing timer before creating new one to prevent leaks
        if (reconnectTimer) {
            clearTimeout(reconnectTimer);
        }
        
        reconnectTimer = setTimeout(() => {
            reconnectTimer = null; // Clear timer reference when it fires
            connectWebSocket(wsUrl);
        }, 3000);
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
