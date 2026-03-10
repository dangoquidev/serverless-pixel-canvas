import { writable } from 'svelte/store';

export const selectedColor = writable('#000000');
export const cooldownRemaining = writable(0);
export const isDrawing = writable(false);
