#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""知乎网页端 x-zse-96 / x-zst-81 请求头。

签名输入为 ``101_3_3.0 + 路径及查询串 + d_c0 + x-zst-81`` 的 MD5，
再经过与当前网页端一致的置换编码。``x-zst-81`` 是网页端固定头，不是密钥。
"""

from __future__ import annotations

import hashlib
import random
import re
from collections.abc import Callable

ZSE93 = "101_3_3.0"
# 网页端随请求附带的固定头，参与签名明文拼接。
X_ZST_81 = (
    "3_2.0aR_sn77yn6O92wOB8hPZnQr0EMYxc4f18wNBUgpTQ6nxERFZfTY0-4Lm-h3_tufIwJS8gcxTgJS_AuPZNcXCTwxI78YxEM20s4PGDwN8gGcYAupMWufIoLVqr4gxrRPOI0cY7HL8qun9g93mFukyigcmebS_FwOYPRP0E4rZUrN9DDom3hnynAUMnAVPF_PhaueTFH9fQL39OCCqYTxfb0rfi9wfPhSM6vxGDJo_rBHpQGNmBBLqPJHK2_w8C9eTVMO9Z9NOrMtfhGH_DgpM-BNM1DOxScLG3gg1Hre1FCXKQcXKkrSL1r9GWDXMk8wqBLNmbRH96BtOFqVZ7UYG3gC8D9cMS7Y9UrHLVCLZPJO8_CL_6GNCOg_zhJS8PbXmGTcBpgxfkieOPhNfthtf2gC_qD3YOce8nCwG2uwBOqeMoML9NBC1xb9yk6SuJhHLK7SM6LVfCve_3vLKlqcL6TxL_UosDvHLxrHmWgxBQ8Xs"
)
_ALPHABET = "6fpLRqJO8M/c3jnYxFkUVC4ZIG12SiH=5v0mXDazWBTsuw7QetbKdoPyAl+hN9rgE"
_ZK = [
    1170614578, 1024848638, 1413669199, -343334464, -766094290, -1373058082,
    -143119608, -297228157, 1933479194, -971186181, -406453910, 460404854,
    -547427574, -1891326262, -1679095901, 2119585428, -2029270069, 2035090028,
    -1521520070, -5587175, -77751101, -2094365853, -1243052806, 1579901135,
    1321810770, 456816404, -1391643889, -229302305, 330002838, -788960546,
    363569021, -1947871109,
]
_ZB = [
    20, 223, 245, 7, 248, 2, 194, 209, 87, 6, 227, 253, 240, 128, 222, 91,
    237, 9, 125, 157, 230, 93, 252, 205, 90, 79, 144, 199, 159, 197, 186, 167,
    39, 37, 156, 198, 38, 42, 43, 168, 217, 153, 15, 103, 80, 189, 71, 191,
    97, 84, 247, 95, 36, 69, 14, 35, 12, 171, 28, 114, 178, 148, 86, 182,
    32, 83, 158, 109, 22, 255, 94, 238, 151, 85, 77, 124, 254, 18, 4, 26,
    123, 176, 232, 193, 131, 172, 143, 142, 150, 30, 10, 146, 162, 62, 224, 218,
    196, 229, 1, 192, 213, 27, 110, 56, 231, 180, 138, 107, 242, 187, 54, 120,
    19, 44, 117, 228, 215, 203, 53, 239, 251, 127, 81, 11, 133, 96, 204, 132,
    41, 115, 73, 55, 249, 147, 102, 48, 122, 145, 106, 118, 74, 190, 29, 16,
    174, 5, 177, 129, 63, 113, 99, 31, 161, 76, 246, 34, 211, 13, 60, 68,
    207, 160, 65, 111, 82, 165, 67, 169, 225, 57, 112, 244, 155, 51, 236, 200,
    233, 58, 61, 47, 100, 137, 185, 64, 17, 70, 234, 163, 219, 108, 170, 166,
    59, 149, 52, 105, 24, 212, 78, 173, 45, 0, 116, 226, 119, 136, 206, 135,
    175, 195, 25, 92, 121, 208, 126, 139, 3, 75, 141, 21, 130, 98, 241, 40,
    154, 66, 184, 49, 181, 46, 243, 88, 101, 183, 8, 23, 72, 188, 104, 179,
    210, 134, 250, 201, 164, 89, 216, 202, 220, 50, 221, 152, 140, 33, 235, 214,
]
_PAD = [48, 53, 57, 48, 53, 51, 102, 55, 100, 49, 53, 101, 48, 49, 100, 55]
_D_C0_RE = re.compile(r"d_c0=([^;]+)")


def _i32(value: int) -> int:
    value &= 0xFFFFFFFF
    if value >= 0x80000000:
        value -= 0x100000000
    return value


def _u32(value: int) -> int:
    return value & 0xFFFFFFFF


def _shr_u(value: int, bits: int) -> int:
    return _u32(value) >> (bits & 31)


def _shl(value: int, bits: int) -> int:
    return _i32(_i32(value) << (bits & 31))


def _xor(left: int, right: int) -> int:
    return _i32(_i32(left) ^ _i32(right))


def _store_u32(value: int, target: list[int], index: int) -> None:
    target[index] = _shr_u(value, 24) & 255
    target[index + 1] = _shr_u(value, 16) & 255
    target[index + 2] = _shr_u(value, 8) & 255
    target[index + 3] = _u32(value) & 255


def _load_u32(data: list[int], index: int) -> int:
    return _i32(
        ((data[index] & 255) << 24)
        | ((data[index + 1] & 255) << 16)
        | ((data[index + 2] & 255) << 8)
        | (data[index + 3] & 255)
    )


def _q(value: int, bits: int) -> int:
    return _i32(_shl(value, bits) | _shr_u(value, 32 - bits))


def _g(value: int) -> int:
    block = [0, 0, 0, 0]
    _store_u32(value, block, 0)
    mapped = [_ZB[byte & 255] for byte in block]
    mixed = _load_u32(mapped, 0)
    return _xor(_xor(_xor(_xor(mixed, _q(mixed, 2)), _q(mixed, 10)), _q(mixed, 18)), _q(mixed, 24))


def _encrypt_block(block: list[int]) -> list[int]:
    words = [0] * 36
    words[0] = _load_u32(block, 0)
    words[1] = _load_u32(block, 4)
    words[2] = _load_u32(block, 8)
    words[3] = _load_u32(block, 12)
    for index in range(32):
        mixed = _g(_xor(_xor(_xor(words[index + 1], words[index + 2]), words[index + 3]), _ZK[index]))
        words[index + 4] = _xor(words[index], mixed)
    out = [0] * 16
    _store_u32(words[35], out, 0)
    _store_u32(words[34], out, 4)
    _store_u32(words[33], out, 8)
    _store_u32(words[32], out, 12)
    return out


def _encrypt_tail(data: list[int], seed: list[int]) -> list[int]:
    output: list[int] = []
    offset = 0
    remaining = len(data)
    while remaining > 0:
        chunk = data[16 * offset: 16 * (offset + 1)]
        mixed = [(chunk[i] ^ seed[i]) & 255 for i in range(16)]
        seed = _encrypt_block(mixed)
        output.extend(seed)
        offset += 1
        remaining -= 16
    return output


def _encode_head(block: list[int]) -> list[int]:
    mixed = [((block[index] ^ _PAD[index]) ^ 42) & 255 for index in range(16)]
    return _encrypt_block(mixed)


def _pack_triplet(values: list[int]) -> list[int]:
    packed = (values[0] & 255) | ((values[1] & 255) << 8) | ((values[2] & 255) << 16)
    result = []
    shift = 0
    while len(result) < 4:
        result.append((packed >> shift) & 63)
        shift += 6
    return result


def encode_zse96(md5_hex: str, rng: Callable[[], float] | None = None) -> str:
    """把 32 位 MD5 十六进制串编码成 ``2.0_`` 开头的 x-zse-96。"""
    if rng is None:
        rng = random.random
    buffer = [ord(char) for char in md5_hex]
    buffer.insert(0, 0)
    buffer.insert(0, int(rng() * 127))
    while len(buffer) < 48:
        buffer.append(14)
    head = _encode_head(buffer[:16])
    tail = _encrypt_tail(buffer[16:48], head)
    body = head + tail
    for index in range(47, -1, -4):
        body[index] ^= 58
    body.reverse()
    packed: list[int] = []
    for index in range(3, len(body) + 1, 3):
        packed.extend(_pack_triplet(body[index - 3: index]))
    return "2.0_" + "".join(_ALPHABET[item] for item in packed)


def extract_d_c0(cookie: str) -> str:
    """从 Cookie 头里取出 d_c0 的原始值（保留引号）。"""
    matched = _D_C0_RE.search(cookie or "")
    if not matched:
        raise ValueError("Cookie 中没有 d_c0，无法计算 x-zse-96")
    return matched.group(1).strip()


def sign_path(path_and_query: str, cookie: str, rng: Callable[[], float] | None = None) -> dict[str, str]:
    """为一次 API 路径生成 x-zse-93 / x-zse-96 / x-zst-81。"""
    d_c0 = extract_d_c0(cookie)
    plain = "+".join([ZSE93, path_and_query, d_c0, X_ZST_81])
    digest = hashlib.md5(plain.encode("utf-8")).hexdigest()
    return {
        "x-zse-93": ZSE93,
        "x-zst-81": X_ZST_81,
        "x-zse-96": encode_zse96(digest, rng=rng),
    }
