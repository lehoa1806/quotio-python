"""Protobuf handler for Antigravity IDE token injection.

This module handles protobuf encoding/decoding for Antigravity IDE state database.
The IDE stores OAuth token in a protobuf-encoded value at field 6.
"""

import base64
from typing import Optional, Tuple


class ProtobufError(Exception):
    """Protobuf-related errors."""
    pass


def encode_varint(value: int) -> bytes:
    """Encode a UInt64 as protobuf varint."""
    result = bytearray()
    val = value
    while val >= 0x80:
        result.append((val & 0x7F) | 0x80)
        val >>= 7
    result.append(val)
    return bytes(result)


def read_varint(data: bytes, offset: int) -> Tuple[int, int]:
    """Read a varint from data at offset, returns (value, newOffset)."""
    result = 0
    shift = 0
    pos = offset

    while True:
        if pos >= len(data):
            raise ProtobufError("Incomplete protobuf data")
        byte = data[pos]
        result |= (byte & 0x7F) << shift
        pos += 1
        if (byte & 0x80) == 0:
            break
        shift += 7

    return (result, pos)


def skip_field(data: bytes, offset: int, wire_type: int) -> int:
    """Skip a protobuf field based on wire type."""
    if wire_type == 0:  # Varint
        _, new_offset = read_varint(data, offset)
        return new_offset
    elif wire_type == 1:  # 64-bit
        return offset + 8
    elif wire_type == 2:  # Length-delimited
        length, content_offset = read_varint(data, offset)
        return content_offset + length
    elif wire_type == 5:  # 32-bit
        return offset + 4
    else:
        raise ProtobufError(f"Unknown wire type: {wire_type}")


def remove_field(data: bytes, field_num: int) -> bytes:
    """Remove a field from protobuf data."""
    result = bytearray()
    offset = 0

    while offset < len(data):
        start_offset = offset
        tag, new_offset = read_varint(data, offset)
        wire_type = tag & 7
        current_field = tag >> 3

        if current_field == field_num:
            # Skip this field
            offset = skip_field(data, new_offset, wire_type)
        else:
            # Keep this field
            next_offset = skip_field(data, new_offset, wire_type)
            result.extend(data[start_offset:next_offset])
            offset = next_offset

    return bytes(result)


def create_oauth_field(access_token: str, refresh_token: str, expiry: int) -> bytes:
    """Create OAuthTokenInfo protobuf (Field 6).

    Structure:
    - Field 1: access_token (string)
    - Field 2: token_type (string, "Bearer")
    - Field 3: refresh_token (string)
    - Field 4: expiry (nested Timestamp with Field 1: seconds as int64)
    """
    # Field 1: access_token (string, wire_type = 2)
    tag1 = encode_varint((1 << 3) | 2)
    access_data = access_token.encode('utf-8')
    field1 = tag1 + encode_varint(len(access_data)) + access_data

    # Field 2: token_type (string, fixed value "Bearer", wire_type = 2)
    tag2 = encode_varint((2 << 3) | 2)
    token_type = "Bearer"
    token_type_data = token_type.encode('utf-8')
    field2 = tag2 + encode_varint(len(token_type_data)) + token_type_data

    # Field 3: refresh_token (string, wire_type = 2)
    tag3 = encode_varint((3 << 3) | 2)
    refresh_data = refresh_token.encode('utf-8')
    field3 = tag3 + encode_varint(len(refresh_data)) + refresh_data

    # Field 4: expiry (nested Timestamp message, wire_type = 2)
    # Timestamp contains: Field 1: seconds (int64, wire_type = 0)
    timestamp_tag = encode_varint((1 << 3) | 0)  # Field 1, varint
    # Handle signed int64 for expiry timestamp
    # Convert signed int64 to unsigned (like UInt64(bitPattern:))
    # This preserves the bit pattern for negative numbers
    if expiry < 0:
        # Convert to unsigned representation (two's complement)
        expiry_uint = expiry & 0xFFFFFFFFFFFFFFFF
    else:
        expiry_uint = expiry
    timestamp_msg = timestamp_tag + encode_varint(expiry_uint)

    tag4 = encode_varint((4 << 3) | 2)  # Field 4, length-delimited
    field4 = tag4 + encode_varint(len(timestamp_msg)) + timestamp_msg

    # Combine all fields into OAuthTokenInfo message
    oauth_info = field1 + field2 + field3 + field4

    # Wrap as Field 6 (length-delimited)
    tag6 = encode_varint((6 << 3) | 2)
    field6 = tag6 + encode_varint(len(oauth_info)) + oauth_info

    return field6


def inject_token(existing_base64: str, access_token: str, refresh_token: str, expiry: int) -> str:
    """Inject OAuth token into existing protobuf state data.

    Args:
        existing_base64: Current base64-encoded protobuf data from database
        access_token: New access token to inject
        refresh_token: New refresh token to inject
        expiry: Token expiry timestamp (Unix seconds)

    Returns:
        New base64-encoded protobuf data ready to write to database
    """
    try:
        existing_data = base64.b64decode(existing_base64)
    except Exception as e:
        raise ProtobufError(f"Invalid base64: {e}")

    # Remove existing Field 6 (OAuth info)
    data_without_oauth = remove_field(existing_data, field_num=6)

    # Create new OAuth field
    new_oauth_field = create_oauth_field(
        access_token=access_token,
        refresh_token=refresh_token,
        expiry=expiry
    )

    # Append new OAuth field
    new_data = data_without_oauth + new_oauth_field

    return base64.b64encode(new_data).decode('utf-8')
