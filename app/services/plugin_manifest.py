"""Manifest validation and UI contribution resolution."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException, status

from app.models.plugin import PluginInstall
from app.schemas.plugin import (
    SLOT_PERMISSION,
    PluginManifest,
    PluginUiContributionResolved,
)


def parse_manifest(raw: dict[str, Any] | PluginManifest) -> PluginManifest:
    if isinstance(raw, PluginManifest):
        return raw
    try:
        return PluginManifest.model_validate(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "invalid_manifest",
                "message": f"Invalid plugin manifest: {exc}",
            },
        ) from exc


def resolve_view(
    manifest: PluginManifest,
    view_ref: str | dict[str, Any] | None,
) -> dict[str, Any] | None:
    if view_ref is None:
        return None
    if isinstance(view_ref, dict):
        return view_ref
    inline = manifest.views.get(view_ref)
    if isinstance(inline, dict):
        return inline
    return {"type": "text", "text": f"Missing view: {view_ref}"}


def contribution_allowed(manifest: PluginManifest, slot: str) -> bool:
    required = SLOT_PERMISSION.get(slot)
    if required is None:
        return False
    return required in manifest.permissions


def build_ui_contributions(
    installs: list[PluginInstall],
) -> list[PluginUiContributionResolved]:
    out: list[PluginUiContributionResolved] = []
    for install in installs:
        if install.status != "active":
            continue
        try:
            manifest = PluginManifest.model_validate(install.manifest)
        except Exception:
            continue
        for contrib in manifest.ui.contributions:
            if not contribution_allowed(manifest, contrib.slot):
                continue
            payload: dict[str, Any] = {
                "slot": contrib.slot,
                "id": contrib.id,
            }
            if contrib.item is not None:
                payload["item"] = contrib.item
            if contrib.route is not None:
                payload["route"] = contrib.route
            if contrib.column is not None:
                payload["column"] = contrib.column
            if contrib.action is not None:
                payload["action"] = contrib.action
            if contrib.label is not None:
                payload["label"] = contrib.label
            if contrib.schema_ref is not None:
                if isinstance(contrib.schema_ref, str):
                    payload["schema"] = manifest.schemas.get(contrib.schema_ref, {})
                else:
                    payload["schema"] = contrib.schema_ref

            out.append(
                PluginUiContributionResolved(
                    install_id=install.id,
                    plugin_id=install.plugin_id,
                    plugin_name=install.name,
                    slot=contrib.slot,
                    contribution_id=contrib.id,
                    payload=payload,
                    requires_host_binding=contrib.requires_host_binding,
                    view=resolve_view(manifest, contrib.view),
                )
            )
    return out


def assert_rpc_method(manifest: PluginManifest, method: str) -> None:
    if "rpc" not in manifest.permissions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "permission_denied",
                "message": "Plugin does not have rpc permission",
            },
        )
    names = {m.method for m in manifest.rpc}
    if method not in names:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "rpc_method_not_found",
                "message": f"RPC method not declared: {method}",
            },
        )


def validate_against_schema(
    data: dict[str, Any],
    schema: dict[str, Any] | str | None,
    *,
    schemas: dict[str, Any],
    field_name: str,
) -> dict[str, Any]:
    """Lightweight JSON Schema subset: type=object + required keys only."""
    if schema is None:
        return data
    resolved: dict[str, Any]
    if isinstance(schema, str):
        resolved = schemas.get(schema, {})
    else:
        resolved = schema
    if not resolved:
        return data
    if resolved.get("type") == "object":
        required = resolved.get("required") or []
        missing = [k for k in required if k not in data]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "schema_validation_failed",
                    "message": f"{field_name} missing required: {', '.join(missing)}",
                },
            )
        properties = resolved.get("properties") or {}
        if properties:
            unknown = set(data) - set(properties)
            if unknown and resolved.get("additionalProperties") is False:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "code": "schema_validation_failed",
                        "message": f"{field_name} unknown keys: {', '.join(sorted(unknown))}",
                    },
                )
    return data


def install_id_str(install_id: UUID) -> str:
    return str(install_id)
