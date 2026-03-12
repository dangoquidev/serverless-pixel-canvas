import { get } from 'svelte/store';
import { authToken } from '../stores/authStore.js';

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:3000";

const request = async (endpoint, options = {}) => {
    const token = get(authToken);

    const headers = {
        'Content-Type': 'application/json',
        ...options.headers,
    };

    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    const config = {
        ...options,
        headers,
    };

    const response = await fetch(`${API_URL}${endpoint}`, config);

    if (response.status === 401) {
        // Unauthorized - token might be invalid/expired
        authToken.set(null);
        throw new Error("Unauthorized");
    }

    if (response.status === 403) {
    }

    return response;
};

export const fetchCanvas = async () => {
    const res = await request('/canvas');
    if (!res.ok) throw new Error("Failed to fetch canvas");
    return res.json();
};

export const fetchChunk = async (cx, cy) => {
    const response = await fetch(`${API_URL}/canvas?cx=${cx}&cy=${cy}`);
    if (!response.ok) throw new Error(`Failed to fetch chunk ${cx},${cy}`);

    let base64Text = await response.text();

    base64Text = base64Text.replace(/^"|"$/g, '');

    const binaryString = atob(base64Text);

    const len = binaryString.length;
    const bytes = new Uint8Array(len);
    for (let i = 0; i < len; i++) {
        bytes[i] = binaryString.charCodeAt(i);
    }

    return bytes.buffer;
};

export const drawPixel = async (x, y, color) => {
    const res = await request('/pixels', {
        method: 'POST',
        body: JSON.stringify({ x, y, color })
    });

    if (res.status === 429) {
        const data = await res.json();
        throw new Error(data.message || "Rate limited");
    }
    if (res.status === 401) {
        throw new Error("You need to be logged in to draw pixels");
    }

    if (!res.ok) {
        throw new Error("Failed to draw pixel");
    }

    return true;
};
