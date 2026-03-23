import { derived, get, writable } from 'svelte/store';

export const selectedColor = writable('#000000');
export const loadedChunks = writable(new Set()); // Tracks "cx,cy"

export const MAX_PIXELS = 20;
export const REFILL_SECONDS = 3;

const REFILL_MS = REFILL_SECONDS * 1000;
const COOLDOWN_STORAGE_KEY = 'pixel_canvas_cooldown_v1';

const normalizeState = (state, now = Date.now()) => {
	if (!state || typeof state !== 'object') {
		return {
			pixels: MAX_PIXELS,
			lastRefillAt: now,
		};
	}

	const pixels = Number.isFinite(state.pixels)
		? Math.min(MAX_PIXELS, Math.max(0, Math.floor(state.pixels)))
		: MAX_PIXELS;

	const lastRefillAt = Number.isFinite(state.lastRefillAt)
		? state.lastRefillAt
		: now;

	return { pixels, lastRefillAt };
};

const applyRefill = (rawState, now = Date.now()) => {
	const state = normalizeState(rawState, now);

	if (state.pixels >= MAX_PIXELS) {
		return {
			pixels: MAX_PIXELS,
			lastRefillAt: now,
		};
	}

	const elapsed = Math.max(0, now - state.lastRefillAt);
	const refillCount = Math.floor(elapsed / REFILL_MS);

	if (refillCount <= 0) {
		return state;
	}

	const pixels = Math.min(MAX_PIXELS, state.pixels + refillCount);
	const lastRefillAt = pixels >= MAX_PIXELS
		? now
		: state.lastRefillAt + refillCount * REFILL_MS;

	return { pixels, lastRefillAt };
};

const loadCooldownState = () => {
	if (typeof window === 'undefined') {
		return normalizeState(null);
	}

	try {
		const raw = localStorage.getItem(COOLDOWN_STORAGE_KEY);
		if (!raw) return normalizeState(null);
		return normalizeState(JSON.parse(raw));
	} catch {
		return normalizeState(null);
	}
};

const cooldownState = writable(applyRefill(loadCooldownState()));

if (typeof window !== 'undefined') {
	cooldownState.subscribe((state) => {
		localStorage.setItem(COOLDOWN_STORAGE_KEY, JSON.stringify(state));
	});
}

export const pixelsRemaining = derived(cooldownState, (state) => state.pixels);

export const tickCooldown = () => {
	cooldownState.update((state) => applyRefill(state));
};

export const consumePixel = () => {
	let consumed = false;

	cooldownState.update((rawState) => {
		const now = Date.now();
		const state = applyRefill(rawState, now);

		if (state.pixels <= 0) {
			consumed = false;
			return state;
		}

		consumed = true;

		if (state.pixels >= MAX_PIXELS) {
			return {
				pixels: MAX_PIXELS - 1,
				lastRefillAt: now,
			};
		}

		return {
			...state,
			pixels: state.pixels - 1,
		};
	});

	return consumed;
};

export const refundPixel = () => {
	cooldownState.update((rawState) => {
		const now = Date.now();
		const state = applyRefill(rawState, now);
		const pixels = Math.min(MAX_PIXELS, state.pixels + 1);

		return {
			pixels,
			lastRefillAt: pixels >= MAX_PIXELS ? now : state.lastRefillAt,
		};
	});
};

export const getSecondsUntilNextRefill = () => {
	const state = applyRefill(get(cooldownState));

	if (state.pixels >= MAX_PIXELS) {
		return REFILL_SECONDS;
	}

	const elapsed = Math.max(0, Date.now() - state.lastRefillAt);
	const remaining = REFILL_MS - (elapsed % REFILL_MS);
	return Math.max(1, Math.ceil(remaining / 1000));
};
