import json
import zipfile
from io import BytesIO

import pytest
from fastapi import HTTPException

from app.services.plugin_package import materialize_manifest_from_zip


def _zip_bytes(files: dict[str, str | bytes]) -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            data = content if isinstance(content, bytes) else content.encode("utf-8")
            zf.writestr(name, data)
    return buf.getvalue()


def test_materialize_inlines_ui_and_schemas() -> None:
    manifest = {
        "id": "com.example.zip",
        "name": "Zip",
        "version": "1.0.0",
        "api_version": 1,
        "permissions": ["pages", "hosts.editor"],
        "config_schema": "schemas/settings.json",
        "host_binding_schema": "schemas/host_binding.json",
        "ui": {
            "contributions": [
                {
                    "slot": "routes",
                    "id": "home",
                    "route": "plugin:com.example.zip/home",
                    "view": "ui/pages/home.json",
                },
                {
                    "slot": "hosts.editor.fields",
                    "id": "bind",
                    "schema": "schemas/host_binding.json",
                },
            ]
        },
    }
    raw = _zip_bytes(
        {
            "vortex-plugin.json": json.dumps(manifest),
            "ui/pages/home.json": json.dumps(
                {"type": "stack", "children": [{"type": "text", "text": "hi"}]}
            ),
            "schemas/settings.json": json.dumps({"type": "object", "properties": {}}),
            "schemas/host_binding.json": json.dumps(
                {"type": "object", "properties": {"entity_id": {"type": "string"}}}
            ),
            "daemon/main.py": "print('ignored')\n",
        }
    )
    out = materialize_manifest_from_zip(raw)
    assert out["views"]["ui/pages/home.json"]["type"] == "stack"
    assert out["schemas"]["schemas/settings.json"]["type"] == "object"
    assert "entity_id" in out["schemas"]["schemas/host_binding.json"]["properties"]


def test_materialize_nested_folder() -> None:
    manifest = {
        "id": "com.example.nested",
        "name": "Nested",
        "version": "1.0.0",
        "api_version": 1,
        "permissions": ["pages"],
        "ui": {
            "contributions": [
                {
                    "slot": "routes",
                    "id": "home",
                    "route": "plugin:com.example.nested/home",
                    "view": "ui/pages/home.json",
                }
            ]
        },
    }
    raw = _zip_bytes(
        {
            "my-plugin/vortex-plugin.json": json.dumps(manifest),
            "my-plugin/ui/pages/home.json": json.dumps({"type": "text", "text": "ok"}),
        }
    )
    out = materialize_manifest_from_zip(raw)
    assert out["id"] == "com.example.nested"
    assert out["views"]["ui/pages/home.json"]["text"] == "ok"


def test_reject_path_traversal() -> None:
    raw = _zip_bytes({"../vortex-plugin.json": "{}"})
    with pytest.raises(HTTPException) as exc:
        materialize_manifest_from_zip(raw)
    assert exc.value.detail["code"] == "invalid_plugin_package"


def test_reject_missing_manifest() -> None:
    raw = _zip_bytes({"readme.txt": "nope"})
    with pytest.raises(HTTPException) as exc:
        materialize_manifest_from_zip(raw)
    assert "vortex-plugin.json" in exc.value.detail["message"]
