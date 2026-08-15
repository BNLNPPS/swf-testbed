import hashlib
from abc import ABC, abstractmethod

from .models import DecisionContext, FileDID, Site, SiteAssignment


class DecisionPolicy(ABC):
    """Policy deciding which site datasets receive a file DID."""

    def choose_sites(
        self,
        context: DecisionContext | FileDID,
        sites: tuple[Site, ...] | None = None,
        sequence: int | None = None,
    ) -> SiteAssignment:
        """Return the sites that should process the context's file DID."""
        if not isinstance(context, DecisionContext):
            if sites is None or sequence is None:
                raise TypeError("choose_sites requires a DecisionContext")
            context = DecisionContext(
                run_dataset="",
                file_did=context,
                available_sites=sites,
                sequence=sequence,
            )
        return self._choose_sites(context)

    @abstractmethod
    def _choose_sites(self, context: DecisionContext) -> SiteAssignment:
        """Policy implementation for a normalized decision context."""


class RoundRobinPolicy(DecisionPolicy):
    def _choose_sites(self, context: DecisionContext) -> SiteAssignment:
        sites = context.available_sites
        _require_sites(sites)
        site = sites[context.sequence % len(sites)]
        return SiteAssignment.from_sites(context.file_did, [site], f"round-robin sequence={context.sequence}")


class HashPolicy(DecisionPolicy):
    def _choose_sites(self, context: DecisionContext) -> SiteAssignment:
        sites = context.available_sites
        _require_sites(sites)
        digest = hashlib.sha256(str(context.file_did).encode("utf-8")).digest()
        idx = int.from_bytes(digest[:8], "big") % len(sites)
        return SiteAssignment.from_sites(context.file_did, [sites[idx]], "sha256 modulo site count")


class AllSitesPolicy(DecisionPolicy):
    def _choose_sites(self, context: DecisionContext) -> SiteAssignment:
        sites = context.available_sites
        _require_sites(sites)
        return SiteAssignment.from_sites(context.file_did, sites, "all sites selected")


class NoSitesPolicy(DecisionPolicy):
    def _choose_sites(self, context: DecisionContext) -> SiteAssignment:
        return SiteAssignment.from_sites(context.file_did, [], "no site selected")


class ExplicitPolicy(DecisionPolicy):
    def __init__(self, selected_sites: tuple[Site, ...]):
        self.selected_sites = selected_sites

    def _choose_sites(self, context: DecisionContext) -> SiteAssignment:
        sites = context.available_sites
        allowed = {site.name: site for site in sites}
        unknown = [site.name for site in self.selected_sites if site.name not in allowed]
        if unknown:
            raise ValueError(f"unknown site(s): {', '.join(unknown)}")
        selected = [allowed[site.name] for site in self.selected_sites]
        return SiteAssignment.from_sites(context.file_did, selected, "explicit site list")


def build_policy(name: str, selected_sites: tuple[Site, ...] = ()) -> DecisionPolicy:
    normalized = name.strip().lower()
    if normalized == "round-robin":
        return RoundRobinPolicy()
    if normalized == "hash":
        return HashPolicy()
    if normalized in {"both", "all", "broadcast"}:
        return AllSitesPolicy()
    if normalized in {"none", "skip"}:
        return NoSitesPolicy()
    if normalized == "explicit":
        return ExplicitPolicy(selected_sites)
    raise ValueError(f"unknown policy {name!r}")


def _require_sites(sites: tuple[Site, ...]) -> None:
    if not sites:
        raise ValueError("at least one site is required")
