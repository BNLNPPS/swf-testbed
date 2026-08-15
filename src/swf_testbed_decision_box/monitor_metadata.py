from typing import Any, Mapping


def metadata_with_execution_id(metadata: Mapping[str, Any] | None, execution_id: str | None) -> dict[str, Any]:
    result = dict(metadata or {})
    if execution_id:
        result["workflow_execution_id"] = execution_id
    return result


def execution_id_matches(metadata: Mapping[str, Any] | None, execution_id: str | None) -> bool:
    if not execution_id:
        return True
    return (metadata or {}).get("workflow_execution_id") == execution_id
