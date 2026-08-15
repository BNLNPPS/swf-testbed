from dataclasses import dataclass


@dataclass(frozen=True)
class DatasetDID:
    scope: str
    name: str

    @classmethod
    def parse(cls, value: str) -> "DatasetDID":
        if ":" not in value:
            raise ValueError(f"dataset DID must be scope:name, got {value!r}")
        scope, name = value.split(":", 1)
        if not scope or not name:
            raise ValueError(f"invalid dataset DID {value!r}")
        return cls(scope=scope, name=name)

    def site_dataset(self, site_name: str, template: str | None = None) -> "DatasetDID":
        if not template:
            return DatasetDID(scope=self.scope, name=f"{self.name}.{site_name}")
        return DatasetDID(
            scope=self.scope,
            name=template.format(
                run_dataset_name=self.name,
                run_number=self.run_number,
                site_name=site_name,
                site=site_name,
            ),
        )

    @property
    def run_number(self) -> str:
        parts = self.name.split(".")
        if len(parts) >= 3 and parts[0] == "swf" and parts[-1] == "run":
            return parts[1]
        raise ValueError(f"cannot derive run number from dataset {self.name!r}")

    def __str__(self) -> str:
        return f"{self.scope}:{self.name}"
