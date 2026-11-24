"""Connectors resolve where a dataset's files come from.

v1 ships the `local` connector (files dropped manually into a project folder).
Other connector types are registered as stubs so the configuration contract
is stable; implement them in this package when a project needs one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, List, Optional

from .local import LocalConnector

PLANNED_CONNECTORS = {
    "sqlserver": "SQL Server / Azure SQL (pyodbc or sqlalchemy) - export query result to the dataset folder",
    "sftp": "SFTP/FTP (paramiko / ftplib) - download matching files to the dataset folder",
    "azure_blob": "Azure Blob Storage (azure-storage-blob) - download matching blobs to the dataset folder",
    "s3": "AWS S3 (boto3) - download matching objects to the dataset folder",
    "gcs": "Google Cloud Storage (google-cloud-storage) - download matching objects to the dataset folder",
}


def get_connector(dataset_name: str, connector_cfg: Dict, project_root: Path):
    connector_type = (connector_cfg or {}).get("type", "local")
    if connector_type == "local":
        return LocalConnector(dataset_name, connector_cfg, project_root)
    if connector_type in PLANNED_CONNECTORS:
        raise NotImplementedError(
            f"Connector '{connector_type}' for dataset '{dataset_name}' is not implemented yet "
            f"({PLANNED_CONNECTORS[connector_type]}). For now, download the file manually into "
            f"'{connector_cfg.get('folder', 'input/...')}' and set connector.type to 'local'."
        )
    raise ValueError(f"Unknown connector type '{connector_type}' for dataset '{dataset_name}'")


__all__ = ["get_connector", "LocalConnector", "PLANNED_CONNECTORS"]
