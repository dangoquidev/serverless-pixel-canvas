import json
import time


CHUNK_SIZE = 100
MAX_PIXELS_PER_MINUTE = 20


def hex_to_int(hex_color: str) -> int:
    """Converts '#FF0000' -> 16711680 to save DynamoDB storage space."""
    return int(hex_color.lstrip("#"), 16)


def int_to_rgb(color_int: int) -> tuple:
    """Converts 16711680 -> (255, 0, 0) using ultra-fast bit shifting."""
    r = (color_int >> 16) & 255
    g = (color_int >> 8) & 255
    b = color_int & 255
    return (r, g, b)


def build_binary_array(items: list) -> bytearray:
    """Packs minified DynamoDB items into a pure 5-byte-per-pixel bytearray."""
    binary_data = bytearray()

    for item in items:
        p = int(item["p"])  # The minified local position (0 - 9999)
        local_x = p % CHUNK_SIZE
        local_y = p // CHUNK_SIZE

        r, g, b = int_to_rgb(int(item["co"]))

        binary_data.extend([local_x, local_y, r, g, b])

    return binary_data


def build_pixel_item(
    x: int, y: int, color: str, user_id: str, timestamp: int = None
) -> dict:
    """Transforms raw pixel data into the minified DynamoDB schema format."""
    if timestamp is None:
        timestamp = int(time.time())

    chunk_x = x // CHUNK_SIZE
    chunk_y = y // CHUNK_SIZE
    local_x = x % CHUNK_SIZE
    local_y = y % CHUNK_SIZE

    return {
        "c": f"{chunk_x}#{chunk_y}",  # Partition Key: "5#5"
        "p": local_y * CHUNK_SIZE + local_x,  # Sort Key: 0-9999
        "co": hex_to_int(color),  # Color: 24-bit Integer
        "u": user_id,
        "t": timestamp,
    }


def stream_image_to_binary(new_image: dict) -> bytearray:
    """Converts a DynamoDB Stream NewImage dict into a 7-byte array [CX, CY, LX, LY, R, G, B]."""
    # Parse Chunk X and Y from "c": {"S": "5#5"}
    cx_str, cy_str = new_image["c"]["S"].split("#")
    cx, cy = int(cx_str), int(cy_str)

    # Parse Local X and Y from "p": {"N": "5050"}
    p = int(new_image["p"]["N"])
    local_x = p % CHUNK_SIZE
    local_y = p // CHUNK_SIZE

    # Parse RGB from "co": {"N": "16711680"}
    r, g, b = int_to_rgb(int(new_image["co"]["N"]))

    # Pack exactly 7 bytes per pixel
    return bytearray([cx, cy, local_x, local_y, r, g, b])


def pixel_to_binary(x: int, y: int, color: str) -> bytearray:
    """
    Converts raw x, y, and hex color into a 7-byte binary frame:
    [CX, CY, LX, LY, R, G, B]
    """
    # Coordinate Math
    cx, cy = x // CHUNK_SIZE, y // CHUNK_SIZE
    lx, ly = x % CHUNK_SIZE, y % CHUNK_SIZE

    # Color Math (assuming hex_to_int and int_to_rgb are also in your utils)
    r, g, b = int_to_rgb(hex_to_int(color))

    # Pack exactly 7 bytes
    return bytearray([cx, cy, lx, ly, r, g, b])
