"""Unpack plugin ZIP archives into a self-contained manifest for install."""

from __future__ import annotations

import json
import zipfile
from io import BytesIO
from typing import Any

from fastapi import HTTPException, status

MAX_ZIP_BYTES = 2 * 1024 * 1024
MAX_ZIP_MEMBERS = 256
MAX_MEMBER_BYTES = 512 * 1024
MANIFEST_NAME = "vortex-plugin.json"


def _bad(code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"code": code, "message": message},
    )


def _normalize_member(name: str) -> str | None:
    raw = name.replace("\\", "/").strip()
    if not raw or raw.endswith("/"):
        return None
    parts = [p for p in raw.split("/") if p and p != "."]
    if not parts or any(p == ".." for p in parts):
        return None
    return "/".join(parts)


def _read_json_member(zf: zipfile.ZipFile, zip_name: str) -> Any:
    info = zf.getinfo(zip_name)
    if info.file_size > MAX_MEMBER_BYTES:
        raise _bad("invalid_plugin_package", f"File too large in archive: {zip_name}")
    try:
        data = zf.read(info)
    except Exception as exc:
        raise _bad("invalid_plugin_package", f"Cannot read {zip_name}") from exc
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _bad("invalid_plugin_package", f"Invalid JSON: {zip_name}") from exc


def _find_manifest_path(members: list[str]) -> tuple[str, str]:
    """Return (normalized manifest path, package root prefix including trailing /)."""
    exact = [m for m in members if m == MANIFEST_NAME or m.endswith(f"/{MANIFEST_NAME}")]
    if not exact:
        raise _bad(
            "invalid_plugin_package",
            f"Archive must contain {MANIFEST_NAME}",
        )
    exact.sort(key=lambda p: (p.count("/"), len(p)))
    path = exact[0]
    if path == MANIFEST_NAME:
        return path, ""
    return path, path[: -len(MANIFEST_NAME)]


def materialize_manifest_from_zip(raw: bytes) -> dict[str, Any]:
    """
    Load vortex-plugin.json from a ZIP and inline ui/*.json + schemas/*.json
    into manifest.views / manifest.schemas (path keys preserved).
    """
    if len(raw) > MAX_ZIP_BYTES:
        raise _bad(
            "invalid_plugin_package",
            f"ZIP exceeds {MAX_ZIP_BYTES // (1024 * 1024)} MiB limit",
        )
    try:
        zf_ctx = zipfile.ZipFile(BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise _bad("invalid_plugin_package", "Not a valid ZIP archive") from exc

    with zf_ctx as zf:
        if zf.testzip() is not None:
            raise _bad("invalid_plugin_package", "Corrupt ZIP archive")

        zip_names: dict[str, str] = {}
        for original in zf.namelist():
            if original.endswith("/") or original.endswith("\\"):
                continue
            norm = _normalize_member(original)
            if norm is None:
                raise _bad(
                    "invalid_plugin_package",
                    f"Unsafe path in archive: {original}",
                )
            info = zf.getinfo(original)
            if info.file_size > MAX_MEMBER_BYTES:
                raise _bad(
                    "invalid_plugin_package",
                    f"File too large in archive: {norm}",
                )
            zip_names[norm] = original
            if len(zip_names) > MAX_ZIP_MEMBERS:
                raise _bad(
                    "invalid_plugin_package",
                    f"ZIP exceeds {MAX_ZIP_MEMBERS} files",
                )

        members = list(zip_names)
        manifest_norm, root = _find_manifest_path(members)
        manifest_raw = _read_json_member(zf, zip_names[manifest_norm])
        if not isinstance(manifest_raw, dict):
            raise _bad("invalid_plugin_package", "Manifest must be a JSON object")

        views: dict[str, Any] = dict(manifest_raw.get("views") or {})
        schemas: dict[str, Any] = dict(manifest_raw.get("schemas") or {})
        if not isinstance(views, dict) or not isinstance(schemas, dict):
            raise _bad("invalid_plugin_package", "views/schemas must be objects")

        def load_rel(rel: str) -> Any | None:
            full = f"{root}{rel}" if root else rel
            full = _normalize_member(full) or full
            zip_name = zip_names.get(full)
            if zip_name is None:
                return None
            return _read_json_member(zf, zip_name)

        for member in members:
            if root and not member.startswith(root):
                continue
            rel = member[len(root) :] if root else member
            if rel == MANIFEST_NAME or not rel.endswith(".json"):
                continue
            payload = _read_json_member(zf, zip_names[member])
            if rel.startswith("ui/") and rel not in views:
                views[rel] = payload
            elif rel.startswith("schemas/") and rel not in schemas:
                schemas[rel] = payload

        ui = manifest_raw.get("ui") or {}
        contribs = ui.get("contributions") if isinstance(ui, dict) else None
        if isinstance(contribs, list):
            for contrib in contribs:
                if not isinstance(contrib, dict):
                    continue
                view_ref = contrib.get("view")
                if isinstance(view_ref, str) and view_ref not in views:
                    loaded = load_rel(view_ref)
                    if loaded is not None:
                        views[view_ref] = loaded
                schema_ref = contrib.get("schema")
                if isinstance(schema_ref, str) and schema_ref not in schemas:
                    loaded = load_rel(schema_ref)
                    if loaded is not None:
                        schemas[schema_ref] = loaded

        for key in ("config_schema", "host_binding_schema"):
            ref = manifest_raw.get(key)
            if isinstance(ref, str) and ref not in schemas:
                loaded = load_rel(ref)
                if loaded is not None:
                    schemas[ref] = loaded

        manifest_raw["views"] = views
        manifest_raw["schemas"] = schemas
        return manifest_raw
