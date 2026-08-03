from types import MappingProxyType
from typing import Any, Mapping

from .catalog import DatasetCatalog
from .datasets import DatasetDID
from .models import Decision, DecisionContext, FileDID, Site
from .policy import DecisionPolicy


class DecisionBox:
    """Apply ePIC processing decisions through site-specific datasets."""

    def __init__(
        self,
        catalog: DatasetCatalog,
        sites: tuple[Site, ...] = (Site("E1_BNL"), Site("E1_JLAB")),
        manage_full_dataset: bool = True,
        site_dataset_template: str | None = None,
    ):
        if not sites:
            raise ValueError("at least one site is required")
        self.catalog = catalog
        self.sites = sites
        self.manage_full_dataset = manage_full_dataset
        self.site_dataset_template = site_dataset_template
        self._run_sequences: dict[str, int] = {}

    def create_run(self, run_dataset: str) -> tuple[str, ...]:
        run_did = DatasetDID.parse(run_dataset)
        dataset_dids = []
        if self.manage_full_dataset:
            dataset_dids.append(str(run_did))
        dataset_dids.extend(str(self._site_dataset(run_did, site.name)) for site in self.sites)
        for dataset_did in dataset_dids:
            self.catalog.ensure_dataset(dataset_did, open_dataset=True)
        return tuple(dataset_dids)

    def decide_file(
        self,
        run_dataset: str,
        file_did: FileDID,
        policy: DecisionPolicy,
        *,
        message: Mapping[str, Any] | None = None,
        run_conditions: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> Decision:
        run_did = DatasetDID.parse(run_dataset)
        self.create_run(run_dataset)

        message_data = dict(message or {})
        sequence = self._sequence_from_message(message_data, run_dataset)
        context = DecisionContext(
            run_dataset=run_dataset,
            file_did=file_did,
            available_sites=self.sites,
            sequence=sequence,
            run_number=run_did.run_number,
            message=MappingProxyType(message_data),
            run_conditions=MappingProxyType(dict(run_conditions or {})),
            metadata=MappingProxyType(dict(metadata or {})),
        )
        assignment = policy.choose_sites(context)
        self._run_sequences[run_dataset] = sequence + 1

        site_datasets = [
            str(self._site_dataset(run_did, site.name))
            for site in assignment.sites
        ]
        for site_dataset in site_datasets:
            self.catalog.ensure_dataset(site_dataset, open_dataset=True)

        if self.manage_full_dataset:
            self.catalog.attach_file(str(run_did), file_did)
        for site_dataset in site_datasets:
            self.catalog.attach_file(site_dataset, file_did)

        return Decision(
            run_dataset=run_dataset,
            full_dataset=str(run_did),
            file_did=file_did,
            site_datasets=tuple(site_datasets),
            reason=assignment.reason,
        )

    def close_run(self, run_dataset: str) -> tuple[str, ...]:
        run_did = DatasetDID.parse(run_dataset)
        dataset_dids = []
        if self.manage_full_dataset:
            dataset_dids.append(str(run_did))
        dataset_dids.extend(str(self._site_dataset(run_did, site.name)) for site in self.sites)
        for dataset_did in dataset_dids:
            self.catalog.close_dataset(dataset_did)
        return tuple(dataset_dids)

    def _sequence_for(self, run_dataset: str) -> int:
        remembered_sequence = self._run_sequences.get(run_dataset, 0)
        if not self.manage_full_dataset:
            return remembered_sequence
        snapshot = getattr(self.catalog, "snapshot", lambda: {"datasets": {}})()
        files = snapshot.get("datasets", {}).get(run_dataset, {}).get("files", [])
        return max(remembered_sequence, len(files))

    def _sequence_from_message(self, message: Mapping[str, Any], run_dataset: str) -> int:
        for key in ("decision_sequence", "sequence"):
            try:
                return int(message[key])
            except (KeyError, TypeError, ValueError):
                continue
        return self._sequence_for(run_dataset)

    def _site_dataset(self, run_did: DatasetDID, site_name: str) -> DatasetDID:
        return run_did.site_dataset(site_name, self.site_dataset_template)
