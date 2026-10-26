"""ArmsHub's experimental VPK v1 writer with shared whole-file payloads.

Each directory entry has its own CRC32, byte length and data-section offset.
Identical files under different names can point at the same byte range. This
module stores those bytes once; it does not compress files or deduplicate only
partially equal model geometry. It leaves the existing Charm Studio writer alone.

Evidence boundary: the repository's VPK reader reconstructs these aliases by
seeking each entry's offset independently and validating its CRC. The installed
Valve Authoring Tools vpk.exe also listed and extracted all three files in a
shared-range probe byte-for-byte; report: .build/armshub_archive_probe/validation.json.
Successful extraction demonstrates container layout, not game model drawing or VAC.
The VDC format page describes ArchiveIndex=0x7fff and EntryOffset relative to
the embedded data section; that page was unavailable (HTTP 403) during this audit:
https://developer.valvesoftware.com/wiki/VPK_(file_format)
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import struct
import zlib


@dataclass(frozen=True)
class ArchiveStats:
    file_count: int
    unique_payloads: int
    logical_payload_bytes: int
    stored_payload_bytes: int
    saved_payload_bytes: int
    header_tree_bytes: int
    archive_bytes: int


def _path(name):
    if not isinstance(name, str) or not name:
        raise ValueError('La ruta del recurso debe ser una cadena no vacía')
    value = name.replace('\\', '/')
    parts = value.split('/')
    if (value.startswith('/') or ':' in value or
            any(part in ('', '.', '..') for part in parts) or
            any(ord(character) < 32 for character in value) or
            any(part.strip() != part for part in parts)):
        raise ValueError('Ruta VPK insegura o ambigua: '+repr(name))
    # The Source filesystem resolves these asset paths case-insensitively.
    return value.lower()


def write_shared_vpk(path, files):
    """Write a deterministic single-file VPK v1 and return measured byte totals.

    ``files`` maps resource paths to bytes. No game files are read or installed.
    All entries use zero preload bytes and archive 0x7fff. Only completely
    identical contents share storage, even when their suffixes differ. Distinct
    contents are compared by full bytes, so a hash collision cannot alias them.
    """
    normalized = {}
    for name, data in files.items():
        name = _path(name)
        if name in normalized:
            raise ValueError('Ruta VPK duplicada sin distinguir mayúsculas: '+name)
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError('El contenido VPK debe ser bytes: '+name)
        data = bytes(data)
        if len(data) > 512 * 1024 * 1024:
            raise ValueError('El recurso supera el límite del lector: '+name)
        normalized[name] = data

    groups = {}
    for name, data in sorted(normalized.items()):
        resource = PurePosixPath(name)
        extension = resource.suffix[1:] or ' '
        folder = str(resource.parent) if str(resource.parent) != '.' else ' '
        stem = resource.name[:-len(resource.suffix)] if resource.suffix else resource.name
        if not stem:
            raise ValueError('Nombre de recurso vacío: '+name)
        groups.setdefault(extension, {}).setdefault(folder, []).append((stem, data))

    tree, payload = bytearray(), bytearray()
    ranges = {}
    logical_bytes = 0

    def string(value):
        tree.extend(value.encode('utf8')+b'\0')

    for extension, folders in sorted(groups.items()):
        string(extension)
        for folder, entries in sorted(folders.items()):
            string(folder)
            for stem, data in entries:
                string(stem)
                if data not in ranges:
                    ranges[data] = len(payload)
                    if len(payload)+len(data) > 0xffffffff:
                        raise ValueError('Los datos del VPK superan el límite de 32 bits')
                    payload.extend(data)
                tree.extend(struct.pack('<IHHIIH', zlib.crc32(data) & 0xffffffff,
                                        0, 0x7fff, ranges[data], len(data), 0xffff))
                logical_bytes += len(data)
            string('')
        string('')
    string('')
    if len(tree) > 128 * 1024 * 1024:
        raise ValueError('El árbol VPK supera el límite del lector')
    header_tree = struct.pack('<III', 0x55aa1234, 1, len(tree))+tree
    archive = header_tree+payload
    Path(path).write_bytes(archive)
    return ArchiveStats(len(normalized), len(ranges), logical_bytes, len(payload),
                        logical_bytes-len(payload), len(header_tree), len(archive))


# Convenient name for callers that already use charmstudio.vpk.write_vpk.
write_vpk = write_shared_vpk
