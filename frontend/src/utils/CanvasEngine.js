export class CanvasEngine {
    constructor(canvas, width, height, chunkSize) {
        this.canvas = canvas;
        this.ctx = canvas.getContext("2d", { alpha: false });
        this.width = width;
        this.height = height;
        this.chunkSize = chunkSize;

        // The Master Buffer
        this.imgData = this.ctx.createImageData(this.width, this.height);
        this.imgData.data.fill(255); // Start White

        // View State
        this.scale = 10;
        this.viewX = 0;
        this.viewY = 0;
    }

    // --- Core Rendering & Data Parsing ---

    /**
     * Single Source of Truth for decoding the 7-byte binary protocol.
     * Maps chunk and local coordinates to global canvas space.
     * @param {Uint8Array} view - The raw byte array [CX, CY, LX, LY, R, G, B]
     */
    applyBinaryBuffer(view) {
        for (let j = 0; j < view.length; j += 7) {
            const globalX = view[j] * this.chunkSize + view[j + 2];
            const globalY = view[j + 1] * this.chunkSize + view[j + 3];

            this.updatePixel(globalX, globalY, view[j + 4], view[j + 5], view[j + 6]);
        }
    }

    getPixel(x, y) {
        if (x < 0 || x >= this.width || y < 0 || y >= this.height) return null;
        const index = (y * this.width + x) * 4;
        return {
            r: this.imgData.data[index],
            g: this.imgData.data[index + 1],
            b: this.imgData.data[index + 2],
            a: this.imgData.data[index + 3]
        };
    }

    updatePixel(x, y, r, g, b, a = 255) {
        if (x < 0 || x >= this.width || y < 0 || y >= this.height) return;
        const index = (y * this.width + x) * 4;
        this.imgData.data[index] = r;
        this.imgData.data[index + 1] = g;
        this.imgData.data[index + 2] = b;
        this.imgData.data[index + 3] = a;
    }

    render() {
        // We use a temporary canvas to apply scaling/panning without blurring
        createImageBitmap(this.imgData).then(bitmap => {
            this.ctx.save();
            this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
            this.ctx.imageSmoothingEnabled = false; // Keep it pixelated
            this.ctx.translate(this.viewX, this.viewY);
            this.ctx.scale(this.scale, this.scale);
            this.ctx.drawImage(bitmap, 0, 0);
            this.ctx.restore();
        });
    }

    // --- Coordinate Math ---

    screenToPixel(clientX, clientY) {
        const rect = this.canvas.getBoundingClientRect();
        const x = Math.floor((clientX - rect.left - this.viewX) / this.scale);
        const y = Math.floor((clientY - rect.top - this.viewY) / this.scale);

        if (x >= 0 && x < this.width && y >= 0 && y < this.height) return { x, y };
        return { x: null, y: null };
    }

    getVisibleChunks(windowWidth, windowHeight) {
        const startX = -this.viewX / this.scale;
        const startY = -this.viewY / this.scale;
        const viewW = windowWidth / this.scale;
        const viewH = windowHeight / this.scale;

        return {
            minCx: Math.max(0, Math.floor(startX / this.chunkSize)),
            minCy: Math.max(0, Math.floor(startY / this.chunkSize)),
            maxCx: Math.min(Math.floor(this.width / this.chunkSize) - 1, Math.floor((startX + viewW) / this.chunkSize)),
            maxCy: Math.min(Math.floor(this.height / this.chunkSize) - 1, Math.floor((startY + viewH) / this.chunkSize))
        };
    }

    hexToRgb(hex) {
        const bigint = parseInt(hex.replace('#', ''), 16);
        return { r: (bigint >> 16) & 255, g: (bigint >> 8) & 255, b: bigint & 255 };
    }
}