from types import SimpleNamespace

from app.core.twofa import resolve_twofa_mode, totp_enforced


def test_resolve_twofa_mode() -> None:
    assert resolve_twofa_mode("debug") == "debug"
    assert resolve_twofa_mode("development") == "dev"
    assert resolve_twofa_mode("dev") == "dev"
    assert resolve_twofa_mode("local") == "dev"
    assert resolve_twofa_mode("production") == "prod"
    assert resolve_twofa_mode("prod") == "prod"
    assert resolve_twofa_mode("production", "debug") == "debug"
    assert resolve_twofa_mode("debug", "prod") == "prod"


def test_totp_enforced_debug(monkeypatch) -> None:
    from app.core import twofa as mod

    monkeypatch.setattr(mod, "twofa_mode", lambda: "debug")
    flagged = SimpleNamespace(require_2fa=True)
    bypass = SimpleNamespace(require_2fa=False)
    assert totp_enforced(flagged) is False  # type: ignore[arg-type]
    assert totp_enforced(bypass) is False  # type: ignore[arg-type]


def test_totp_enforced_dev(monkeypatch) -> None:
    from app.core import twofa as mod

    monkeypatch.setattr(mod, "twofa_mode", lambda: "dev")
    flagged = SimpleNamespace(require_2fa=True)
    bypass = SimpleNamespace(require_2fa=False)
    assert totp_enforced(flagged) is True  # type: ignore[arg-type]
    assert totp_enforced(bypass) is False  # type: ignore[arg-type]


def test_totp_enforced_prod(monkeypatch) -> None:
    from app.core import twofa as mod

    monkeypatch.setattr(mod, "twofa_mode", lambda: "prod")
    flagged = SimpleNamespace(require_2fa=True)
    bypass = SimpleNamespace(require_2fa=False)
    assert totp_enforced(flagged) is True  # type: ignore[arg-type]
    assert totp_enforced(bypass) is True  # type: ignore[arg-type]
