"""Access policy: the third defence layer.

Even if a tool is implemented correctly, the policy narrows what it may touch:
which environments, namespaces, indices and hosts are reachable, and how large
a query may be.

Configuration lives in ``config/policy.yaml`` and ``config/environments.yaml``.
Every tool must call :meth:`Policy.assert_allowed` as its first statement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatch
from functools import lru_cache
from pathlib import Path
from typing import Any, Final

import yaml

from tracehub_core.config import REPO_ROOT

DEFAULT_POLICY_PATH: Final = REPO_ROOT / "config" / "policy.yaml"
DEFAULT_ENVIRONMENTS_PATH: Final = REPO_ROOT / "config" / "environments.yaml"


class PolicyError(RuntimeError):
    """Raised when a tool call violates the access policy.

    The message is Turkish because it is shown to the user and fed back to the
    model as an observation.
    """


@dataclass(frozen=True)
class Environment:
    """A logical environment mapped to its physical targets."""

    name: str
    display_name: str
    is_production: bool = False
    k8s_context: str | None = None
    elastic: str | None = None
    grafana: str | None = None
    namespaces: tuple[str, ...] = ()


@dataclass(frozen=True)
class Limits:
    """Per-category query ceilings."""

    values: dict[str, int] = field(default_factory=dict)

    def get(self, name: str, default: int) -> int:
        return self.values.get(name, default)

    def clamp(self, name: str, requested: int, default: int) -> int:
        """Return ``requested`` capped at the configured maximum."""
        return min(requested, self.get(name, default))


@dataclass(frozen=True)
class AllowDeny:
    """An allow/deny pattern pair. Deny always wins."""

    allow: tuple[str, ...] = ()
    deny: tuple[str, ...] = ()

    def permits(self, value: str) -> bool:
        candidate = value.strip()
        if any(fnmatch(candidate, pattern) for pattern in self.deny):
            return False
        if not self.allow:
            return True
        return any(fnmatch(candidate, pattern) for pattern in self.allow)


class Policy:
    """Validates tool call targets against the configured allowlists."""

    def __init__(
        self,
        *,
        environments: dict[str, Environment],
        namespaces: AllowDeny,
        indices: AllowDeny,
        winrm_hosts: AllowDeny,
        limits: dict[str, Limits],
    ) -> None:
        self._environments = environments
        self._namespaces = namespaces
        self._indices = indices
        self._winrm_hosts = winrm_hosts
        self._limits = limits

    # --- environments ---------------------------------------------------

    @property
    def environment_names(self) -> tuple[str, ...]:
        return tuple(self._environments)

    def environment(self, name: str) -> Environment:
        """Resolve an environment name, raising ``PolicyError`` if unknown."""
        resolved = self._environments.get(name.strip().casefold())
        if resolved is None:
            allowed = ", ".join(self.environment_names)
            raise PolicyError(f"'{name}' adında tanımlı bir ortam yok. Tanımlı ortamlar: {allowed}")
        return resolved

    def is_production(self, name: str) -> bool:
        return self.environment(name).is_production

    # --- the guard every tool calls -------------------------------------

    def assert_allowed(
        self,
        *,
        environment: str,
        namespace: str | None = None,
        index: str | None = None,
        host: str | None = None,
    ) -> Environment:
        """Validate a tool call target. Returns the resolved environment.

        Raises ``PolicyError`` with a Turkish message on any violation.
        """
        resolved = self.environment(environment)

        if namespace is not None:
            if not self._namespaces.permits(namespace):
                raise PolicyError(
                    f"'{namespace}' namespace'ine erişim politika tarafından engellendi."
                )
            if resolved.namespaces and not any(
                fnmatch(namespace, pattern) for pattern in resolved.namespaces
            ):
                allowed = ", ".join(resolved.namespaces)
                raise PolicyError(
                    f"'{namespace}' namespace'i '{resolved.name}' ortamında tanımlı değil. "
                    f"Tanımlı namespace'ler: {allowed}"
                )

        if index is not None and not self._indices.permits(index):
            raise PolicyError(f"'{index}' index'ine erişim politika tarafından engellendi.")

        if host is not None and not self._winrm_hosts.permits(host):
            raise PolicyError(f"'{host}' sunucusuna erişim politika tarafından engellendi.")

        return resolved

    # --- limits ---------------------------------------------------------

    def limits(self, category: str) -> Limits:
        return self._limits.get(category, Limits())

    def clamp(self, category: str, name: str, requested: int, default: int) -> int:
        """Cap a requested limit at the policy maximum."""
        return self.limits(category).clamp(name, requested, default)

    def require_time_window(self, category: str = "elasticsearch") -> bool:
        return bool(self.limits(category).get("require_time_window", 0))


def load_policy(
    policy_path: Path | None = None,
    environments_path: Path | None = None,
) -> Policy:
    """Build a :class:`Policy` from YAML configuration."""
    policy_data = _read_yaml(policy_path or DEFAULT_POLICY_PATH)
    environments_data = _read_yaml(environments_path or DEFAULT_ENVIRONMENTS_PATH)

    environments = {
        name.casefold(): Environment(
            name=name.casefold(),
            display_name=str(values.get("display_name", name)),
            is_production=bool(values.get("is_production", False)),
            k8s_context=values.get("k8s_context"),
            elastic=values.get("elastic"),
            grafana=values.get("grafana"),
            namespaces=tuple(values.get("namespaces") or ()),
        )
        for name, values in (environments_data.get("environments") or {}).items()
    }

    limits = {
        category: Limits(values=_int_values(section.get("limits") or {}))
        for category, section in policy_data.items()
        if isinstance(section, dict)
    }
    limits["budget"] = Limits(values=_int_values(policy_data.get("budget") or {}))

    return Policy(
        environments=environments,
        namespaces=_allow_deny(policy_data, "kubernetes", "namespaces"),
        indices=_allow_deny(policy_data, "elasticsearch", "indices"),
        winrm_hosts=_allow_deny(policy_data, "winrm", "hosts"),
        limits=limits,
    )


@lru_cache(maxsize=1)
def get_policy() -> Policy:
    """Process-wide policy instance."""
    return load_policy()


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise PolicyError(f"Politika dosyası bulunamadı: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise PolicyError(f"Politika dosyası geçersiz: {path}")
    return data


def _allow_deny(data: dict[str, Any], category: str, key: str) -> AllowDeny:
    section = data.get(category) or {}
    values = section.get(key) or {}
    return AllowDeny(
        allow=tuple(values.get("allow") or ()),
        deny=tuple(values.get("deny") or ()),
    )


def _int_values(raw: dict[str, Any]) -> dict[str, int]:
    """Keep only integer-like entries; booleans become 0/1."""
    result: dict[str, int] = {}
    for key, value in raw.items():
        if isinstance(value, bool):
            result[key] = int(value)
        elif isinstance(value, int):
            result[key] = value
    return result
