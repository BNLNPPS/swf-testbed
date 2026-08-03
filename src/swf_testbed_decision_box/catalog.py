from abc import ABC, abstractmethod
from typing import Any

from .models import FileDID


class DatasetCatalog(ABC):
    """Minimal interface needed by the decision box.

    Production prompt processing uses the Rucio-backed implementation below.
    """

    @abstractmethod
    def ensure_dataset(self, dataset_did: str, open_dataset: bool = True) -> None:
        """Create the dataset if needed and keep its open/closed state."""

    @abstractmethod
    def attach_file(self, dataset_did: str, file_did: FileDID) -> bool:
        """Attach a file DID. Return True if this call added a new member."""

    @abstractmethod
    def close_dataset(self, dataset_did: str) -> None:
        """Mark a dataset closed."""


class DatasetStateLookupError(RuntimeError):
    """Raised when a dataset open/closed state cannot be determined."""


class RucioDatasetCatalog(DatasetCatalog):
    """Rucio-backed catalog adapter.

    This adapter follows the same helper APIs used by the existing data agent
    and reuses the data agent's initialized Rucio client.
    """

    def __init__(self, client, lifetime_days: int | None = None):
        self.client = client
        self.lifetime_days = lifetime_days
        self._use_rucio_utils = False
        self._closed_datasets: set[str] = set()
        try:
            from swf_common_lib.rucio_utils import create_dataset, add_files_to_dataset

            self._create_dataset = create_dataset
            self._add_files_to_dataset = add_files_to_dataset
            self._use_rucio_utils = True
        except ModuleNotFoundError as exc:
            if exc.name not in {"swf_common_lib", "swf_common_lib.rucio_utils"}:
                raise
            from rucio.common.exception import DataIdentifierAlreadyExists
            from rucio_comms import DatasetManager, FileManager

            self.dataset_manager = DatasetManager()
            self.file_manager = FileManager(rucio_client=self.client)
            self.data_identifier_already_exists = DataIdentifierAlreadyExists

    def ensure_dataset(self, dataset_did: str, open_dataset: bool = True) -> None:
        if open_dataset and self._dataset_is_closed(dataset_did):
            raise ValueError(f"dataset {dataset_did} is already closed")
        if self._use_rucio_utils:
            result = self._create_dataset(
                dataset_name=dataset_did,
                lifetime_days=self.lifetime_days,
                open_dataset=open_dataset,
                client=self.client,
            )
            if not result:
                raise RuntimeError(f"failed to create dataset {dataset_did}")
            return
        try:
            self.dataset_manager.create_dataset(
                dataset_name=dataset_did,
                lifetime_days=self.lifetime_days,
                open_dataset=open_dataset,
            )
        except self.data_identifier_already_exists:
            return

    def attach_file(self, dataset_did: str, file_did: FileDID) -> bool:
        if self._dataset_is_closed(dataset_did):
            raise ValueError(f"dataset {dataset_did} is closed")
        self.ensure_dataset(dataset_did, open_dataset=True)
        if self._use_rucio_utils:
            result = self._add_files_to_dataset([str(file_did)], dataset_did, client=self.client)
        else:
            result = self.file_manager.add_files_to_dataset([str(file_did)], dataset_did)
        return bool(result)

    def close_dataset(self, dataset_did: str) -> None:
        scope, name = dataset_did.split(":", 1)
        self.client.set_status(scope=scope, name=name, open=False)
        self._closed_datasets.add(dataset_did)

    def _dataset_is_closed(self, dataset_did: str) -> bool:
        if dataset_did in self._closed_datasets:
            return True
        scope, name = dataset_did.split(":", 1)
        for method_name in ("get_did", "get_metadata"):
            method = getattr(self.client, method_name, None)
            if method is None:
                continue
            try:
                metadata = method(scope=scope, name=name)
            except Exception as exc:
                if self._is_did_not_found(exc):
                    continue
                raise DatasetStateLookupError(f"failed to look up dataset {dataset_did}") from exc
            is_open = self._metadata_open_state(metadata)
            if is_open is None:
                continue
            if not is_open:
                self._closed_datasets.add(dataset_did)
                return True
            return False
        return False

    @staticmethod
    def _is_did_not_found(exc: Exception) -> bool:
        return any(
            cls.__name__ in {"DataIdentifierNotFound", "DIDNotFound", "DataIdentifierNotFoundError"}
            for cls in type(exc).__mro__
        )

    @staticmethod
    def _metadata_open_state(metadata: Any) -> bool | None:
        if not metadata:
            return None
        for key in ("is_open", "open"):
            if key in metadata:
                value = metadata[key]
                if isinstance(value, str):
                    return value.strip().lower() not in {"0", "false", "no", "off"}
                return bool(value)
        return None
