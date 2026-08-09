from app.schemas.plugin import PluginManifest
from app.services.plugin_manifest import (
    build_ui_contributions,
    contribution_allowed,
    parse_manifest,
    resolve_view,
)


def test_parse_manifest_v1() -> None:
    m = parse_manifest(
        {
            "id": "com.example.fake",
            "name": "Fake",
            "version": "1.0.0",
            "api_version": 1,
            "permissions": ["nav", "pages", "state.write", "rpc"],
            "rpc": [{"method": "refresh"}],
            "ui": {
                "contributions": [
                    {
                        "slot": "nav.items",
                        "id": "nav",
                        "item": {
                            "label": "Fake",
                            "route": "plugin:com.example.fake/home",
                        },
                    }
                ]
            },
            "views": {
                "ui/pages/home.json": {
                    "type": "stack",
                    "children": [{"type": "text", "text": "hi"}],
                }
            },
        }
    )
    assert isinstance(m, PluginManifest)
    assert m.id == "com.example.fake"
    assert contribution_allowed(m, "nav.items")
    assert not contribution_allowed(m, "hosts.table.columns")
    view = resolve_view(m, "ui/pages/home.json")
    assert view is not None and view["type"] == "stack"


def test_build_ui_filters_missing_permission() -> None:
    class FakeInstall:
        id = __import__("uuid").uuid4()
        plugin_id = "com.example.fake"
        name = "Fake"
        status = "active"
        manifest = {
            "id": "com.example.fake",
            "name": "Fake",
            "version": "1.0.0",
            "api_version": 1,
            "permissions": ["nav"],
            "ui": {
                "contributions": [
                    {
                        "slot": "nav.items",
                        "id": "a",
                        "item": {"label": "A", "route": "plugin:com.example.fake/a"},
                    },
                    {
                        "slot": "routes",
                        "id": "b",
                        "route": "plugin:com.example.fake/a",
                        "view": {"type": "text", "text": "x"},
                    },
                ]
            },
        }

    contribs = build_ui_contributions([FakeInstall()])  # type: ignore[list-item]
    assert len(contribs) == 1
    assert contribs[0].slot == "nav.items"
