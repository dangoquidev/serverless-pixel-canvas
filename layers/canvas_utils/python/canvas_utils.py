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


def decode_db_item(item: dict) -> tuple:
    """
    CENTRALIZED MATH: Decodes a minified DynamoDB item back into all coordinates.
    Returns: (global_x, global_y, cx, cy, lx, ly, r, g, b)
    """
    cx_str, cy_str = item["c"].split("#")
    cx, cy = int(cx_str), int(cy_str)

    p = int(item["p"])
    lx = p % CHUNK_SIZE
    ly = p // CHUNK_SIZE

    global_x = (cx * CHUNK_SIZE) + lx
    global_y = (cy * CHUNK_SIZE) + ly

    r, g, b = int_to_rgb(int(item["co"]))

    return (global_x, global_y, cx, cy, lx, ly, r, g, b)


def build_binary_array(items: list) -> bytearray:
    """Packs minified DynamoDB items into a pure 7-byte-per-pixel bytearray."""
    binary_data = bytearray()
    for item in items:
        _, _, cx, cy, lx, ly, r, g, b = decode_db_item(item)

        binary_data.extend([cx, cy, lx, ly, r, g, b])

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
        "c": f"{chunk_x}#{chunk_y}",  # Partition Key
        "p": local_y * CHUNK_SIZE + local_x,  # Sort Key
        "co": hex_to_int(color),
        "u": user_id,
        "t": timestamp,
    }


def stream_image_to_binary(new_image: dict) -> bytearray:
    """Converts a DynamoDB Stream NewImage dict into a 7-byte array."""
    standard_item = {
        "c": new_image["c"]["S"],
        "p": new_image["p"]["N"],
        "co": new_image["co"]["N"],
    }
    _, _, cx, cy, lx, ly, r, g, b = decode_db_item(standard_item)
    return bytearray([cx, cy, lx, ly, r, g, b])


def pixel_to_binary(x: int, y: int, color: str) -> bytearray:
    """Converts raw x, y, and hex color into a 7-byte binary frame for WebSockets."""
    cx, cy = x // CHUNK_SIZE, y // CHUNK_SIZE
    lx, ly = x % CHUNK_SIZE, y % CHUNK_SIZE
    r, g, b = int_to_rgb(hex_to_int(color))
    return bytearray([cx, cy, lx, ly, r, g, b])
