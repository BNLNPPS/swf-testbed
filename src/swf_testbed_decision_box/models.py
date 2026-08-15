from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Iterable, Mapping


@dataclass(frozen=True, order=True)
class Site:
    """PanDA site and dataset suffix used by the decision box."""

    name: str

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("site name cannot be empty")


@dataclass(frozen=True)
class FileDID:
    """Rucio file DID in scope:name form."""

    scope: str
    name: str

    @classmethod
    def parse(cls, value: str, default_scope: str | None = None) -> "FileDID":
        if ":" in value:
            scope, name = value.split(":", 1)
        elif default_scope:
            scope, name = default_scope, value
        else:
            raise ValueError(f"file DID must be scope:name, got {value!r}")
        if not scope or not name:
            raise ValueError(f"invalid file DID {value!r}")
        return cls(scope=scope, name=name)

    def __str__(self) -> str:
        return f"{self.scope}:{self.name}"


@dataclass(frozen=True)
class DecisionContext:
    """Inputs available to policy evaluation for one STF file."""

    run_dataset: str
    file_did: FileDID
    available_sites: tuple[Site, ...]
    sequence: int
    run_number: str | None = None
    message: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    run_conditions: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    metadata: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))


@dataclass(frozen=True)
class SiteAssignment:
    """Decision result for one STF file."""

    file_did: FileDID
    sites: tuple[Site, ...]
    reason: str

    @classmethod
    def from_sites(cls, file_did: FileDID, sites: Iterable[Site], reason: str) -> "SiteAssignment":
        unique_sites = tuple(sorted(set(sites), key=lambda site: site.name))
        return cls(file_did=file_did, sites=unique_sites, reason=reason)


@dataclass(frozen=True)
class Decision:
    """Applied decision, including the datasets that were mutated."""

    run_dataset: str
    full_dataset: str
    file_did: FileDID
    site_datasets: tuple[str, ...]
    reason: str
