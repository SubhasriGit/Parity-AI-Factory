"""Project configuration loading and validation.

A generated project keeps every project-specific decision in JSON files:

    config/project.json          name, mode, database, processing, llm, reports
    config/datasets.json         datasets (source / target / diff / reference)
    config/mappings/*.json       column layout per dataset
    config/filters.json          filtering rules per dataset
    config/comparison.json       source/target keys + compare fields
    config/diff_ingest.json      supplied-report interpretation
    rules/known_discrepancies.json  ordered classification rules
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .db import Database, check_identifier

ROLES = ("source", "target", "diff", "reference")
FORMATS = ("csv", "fixed_width", "jsonl")
LOAD_MODES = ("replace", "append")
MODES = ("A", "B", "AB")
FIELD_TYPES = ("string", "integer", "decimal", "date", "datetime")
FILTER_SCOPES = ("latest_load", "all")


class ConfigError(Exception):
    pass


def read_json(path: Path) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        raise ConfigError(f"Missing file: {path}")
    except json.JSONDecodeError as exc:
        raise ConfigError(
            f"Invalid JSON in {path}: line {exc.lineno} col {exc.colno}: {exc.msg}")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def read_yaml(path: Path) -> Any:
    try:
        import yaml
    except ImportError as exc:
        raise ConfigError(
            "PyYAML is required to read config/*.yaml; install requirements.txt") from exc
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}
    except FileNotFoundError as exc:
        raise ConfigError(f"Missing file: {path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {path}: {exc}") from exc


@dataclass
class Dataset:
    name: str
    role: str
    raw: Dict[str, Any]
    mapping: Dict[str, Any]

    @property
    def raw_table(self) -> str:
        return f"raw_{self.name}"

    @property
    def filtered_table(self) -> str:
        return f"flt_{self.name}"

    @property
    def columns(self) -> List[str]:
        return [c["name"] for c in self.mapping.get("columns", [])]

    @property
    def connector(self) -> Dict[str, Any]:
        return self.raw.get("connector", {})

    @property
    def format(self) -> Dict[str, Any]:
        return self.raw.get("format", {"type": "csv"})

    @property
    def load_policy(self) -> Dict[str, Any]:
        return self.raw.get("load_policy", {"mode": "replace"})


@dataclass
class ProjectContext:
    root: Path
    project: Dict[str, Any]
    datasets: Dict[str, Dataset]
    filters: Dict[str, Any]
    comparison: Optional[Dict[str, Any]]
    diff_ingest: Optional[Dict[str, Any]]
    analysis_snapshots: Dict[str, Any]
    rules: Dict[str, Any]
    _db: Optional[Database] = field(default=None, repr=False)

    # -- convenience -----------------------------------------------------
    @property
    def mode(self) -> str:
        return str(self.project.get("mode", "A")).upper()

    @property
    def slug(self) -> str:
        return self.project.get("slug", "parity")

    @property
    def batch_size(self) -> int:
        return int(self.project.get("processing", {}).get("batch_size", 50000))

    def path(self, relative: str) -> Path:
        candidate = Path(relative)
        return candidate if candidate.is_absolute() else (self.root / candidate)

    @property
    def output_dir(self) -> Path:
        return self.path(self.project.get("paths", {}).get("output", "output"))

    @property
    def llm(self) -> Dict[str, Any]:
        return self.project.get("llm", {})

    @property
    def reports(self) -> Dict[str, Any]:
        return self.project.get("reports", {})

    @property
    def db(self) -> Database:
        if self._db is None:
            db_cfg = self.project.get("database", {})
            self._db = Database(db_cfg.get("engine", "sqlite"), self.path(
                db_cfg.get("path", "db/parity.db")))
            self._db.init_core_schema()
        return self._db

    def close(self) -> None:
        if self._db is not None:
            self._db.close()
            self._db = None
        logger = logging.getLogger(
            f"parity.{self.slug}.{abs(hash(str(self.root)))}")
        for handler in list(logger.handlers):
            handler.close()
            logger.removeHandler(handler)

    def datasets_by_role(self, role: str) -> List[Dataset]:
        return [d for d in self.datasets.values() if d.role == role]

    def dataset(self, name: str) -> Dataset:
        if name not in self.datasets:
            raise ConfigError(
                f"Unknown dataset '{name}'. Known: {', '.join(self.datasets) or '(none)'}")
        return self.datasets[name]


def load_project(root: Path) -> ProjectContext:
    root = Path(root).resolve()
    config_dir = root / "config"
    project = read_json(config_dir / "project.json")
    datasets_cfg = read_json(config_dir / "datasets.json")
    datasets: Dict[str, Dataset] = {}
    for raw in datasets_cfg.get("datasets", []):
        name = raw.get("name")
        mapping_ref = raw.get("mapping")
        if isinstance(mapping_ref, dict):
            mapping = mapping_ref
        elif mapping_ref:
            mapping = read_json(root / mapping_ref)
        else:
            mapping = {"columns": []}
        if name in datasets:
            raise ConfigError(
                f"Duplicate dataset name '{name}' in config/datasets.json")
        datasets[name] = Dataset(name=name, role=raw.get(
            "role", ""), raw=raw, mapping=mapping)

    filters = read_json(config_dir / "filters.json") if (config_dir /
                                                         "filters.json").exists() else {"datasets": {}}
    comparison = read_json(
        config_dir / "comparison.json") if (config_dir / "comparison.json").exists() else None
    diff_ingest = read_json(
        config_dir / "diff_ingest.json") if (config_dir / "diff_ingest.json").exists() else None
    snapshots_path = config_dir / "config.yaml"
    analysis_snapshots = read_yaml(snapshots_path) if snapshots_path.exists() else {
        "analysis_snapshots": []}
    rules_path = root / "rules" / "known_discrepancies.json"
    rules = read_json(rules_path) if rules_path.exists() else {"rules": []}
    return ProjectContext(
        root=root,
        project=project,
        datasets=datasets,
        filters=filters,
        comparison=comparison,
        diff_ingest=diff_ingest,
        analysis_snapshots=analysis_snapshots,
        rules=rules,
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_project(ctx: ProjectContext) -> List[str]:
    """Return a list of human-readable problems. Empty list = valid."""
    errors: List[str] = []

    def err(message: str) -> None:
        errors.append(message)

    if ctx.mode not in MODES:
        err(
            f"config/project.json: mode must be one of {MODES}, got '{ctx.mode}'")
    engine = ctx.project.get("database", {}).get("engine", "sqlite")
    if engine not in ("sqlite", "duckdb"):
        err(
            f"config/project.json: database.engine must be 'sqlite' or 'duckdb', got '{engine}'")

    if not ctx.datasets:
        err("config/datasets.json: no datasets defined")

    for ds in ctx.datasets.values():
        where = f"dataset '{ds.name}'"
        try:
            check_identifier(ds.name, "dataset name")
        except ValueError as exc:
            err(f"{where}: {exc}")
        if ds.role not in ROLES:
            err(f"{where}: role must be one of {ROLES}, got '{ds.role}'")
        fmt = ds.format.get("type", "csv")
        if fmt not in FORMATS:
            err(f"{where}: format.type must be one of {FORMATS}, got '{fmt}'")
        connector_type = ds.connector.get("type", "local")
        if connector_type == "local" and not ds.connector.get("folder"):
            err(f"{where}: connector.folder is required for local connector")
        policy = ds.load_policy
        if policy.get("mode", "replace") not in LOAD_MODES:
            err(f"{where}: load_policy.mode must be one of {LOAD_MODES}")
        columns = ds.mapping.get("columns", [])
        if not columns:
            err(f"{where}: mapping has no columns")
        seen = set()
        for col in columns:
            name = col.get("name")
            try:
                check_identifier(name, "column name")
            except ValueError as exc:
                err(f"{where}: {exc}")
                continue
            if name.startswith("_"):
                err(f"{where}: column '{name}' must not start with '_' (reserved for framework columns)")
            if name in seen:
                err(f"{where}: duplicate column '{name}' in mapping")
            seen.add(name)
            if col.get("type", "string") not in FIELD_TYPES:
                err(f"{where}: column '{name}' type must be one of {FIELD_TYPES}")
            if fmt == "fixed_width" and ("start" not in col or "end" not in col):
                err(f"{where}: fixed_width column '{name}' needs 'start' and 'end' (1-based, inclusive)")
            if fmt == "csv" and ds.format.get("header", True) is False and "index" not in col:
                err(f"{where}: headerless csv column '{name}' needs 'index' (0-based)")
        for key in policy.get("dedupe_on", []) or []:
            if key not in seen:
                err(f"{where}: load_policy.dedupe_on column '{key}' is not in the mapping")

    # filters
    for name, flt in (ctx.filters.get("datasets") or {}).items():
        if name not in ctx.datasets:
            err(f"config/filters.json: unknown dataset '{name}'")
            continue
        scope = flt.get("scope")
        if scope is not None and scope not in FILTER_SCOPES:
            err(
                f"config/filters.json: dataset '{name}' scope must be one of {FILTER_SCOPES}")
        from .conditions import validate_condition

        columns = set(ctx.datasets[name].columns)
        for section in ("include", "exclude"):
            for i, rule in enumerate(flt.get(section, []) or []):
                cond = rule.get("condition", rule)
                for problem in validate_condition(cond, sql=True, path=f"{section}[{i}]"):
                    err(f"config/filters.json: dataset '{name}': {problem}")
                for column in _condition_columns(cond):
                    if column not in columns:
                        err(
                            f"config/filters.json: dataset '{name}': column '{column}' is not in the mapping")

    if "A" in ctx.mode:
        errors.extend(_validate_comparison(ctx))
    if "B" in ctx.mode:
        errors.extend(_validate_diff_ingest(ctx))

    errors.extend(_validate_analysis_snapshots(ctx))
    errors.extend(_validate_rules(ctx))
    return errors


def _condition_columns(cond: Any) -> List[str]:
    if not isinstance(cond, dict):
        return []
    found: List[str] = []
    for key in ("all", "any"):
        for sub in cond.get(key, []) or []:
            found.extend(_condition_columns(sub))
    if "not" in cond:
        found.extend(_condition_columns(cond["not"]))
    if "column" in cond:
        found.append(cond["column"])
    return found


def _validate_comparison(ctx: ProjectContext) -> List[str]:
    errors: List[str] = []
    cmp_cfg = ctx.comparison
    if not cmp_cfg:
        return ["Mode A requires config/comparison.json"]
    src, tgt = cmp_cfg.get("source"), cmp_cfg.get("target")
    for side, name in (("source", src), ("target", tgt)):
        if name not in ctx.datasets:
            errors.append(
                f"config/comparison.json: {side} dataset '{name}' is not defined in datasets.json")
    if errors:
        return errors
    src_cols, tgt_cols = set(ctx.datasets[src].columns), set(
        ctx.datasets[tgt].columns)
    if not cmp_cfg.get("keys"):
        errors.append(
            "config/comparison.json: at least one key column is required")
    names = set()
    for section in ("keys", "fields"):
        for item in cmp_cfg.get(section, []):
            name = item.get("name")
            if not name:
                errors.append(
                    f"config/comparison.json: every {section} entry needs a 'name'")
                continue
            if name in names:
                errors.append(
                    f"config/comparison.json: '{name}' is used twice across keys/fields")
            names.add(name)
            s_col = item.get("source", name)
            t_col = item.get("target", name)
            if s_col not in src_cols:
                errors.append(
                    f"config/comparison.json: {section} '{name}' source column '{s_col}' not in {src} mapping")
            if t_col not in tgt_cols:
                errors.append(
                    f"config/comparison.json: {section} '{name}' target column '{t_col}' not in {tgt} mapping")
            if item.get("type", "string") not in FIELD_TYPES:
                errors.append(
                    f"config/comparison.json: '{name}' type must be one of {FIELD_TYPES}")
    return errors


def _validate_diff_ingest(ctx: ProjectContext) -> List[str]:
    errors: List[str] = []
    cfg = ctx.diff_ingest
    if not cfg:
        return ["Mode B requires config/diff_ingest.json"]
    entries = cfg.get("inputs", [])
    if not entries:
        errors.append(
            "config/diff_ingest.json: 'inputs' must list at least one diff dataset")
    key_names = [k if isinstance(k, str) else k.get("name")
                 for k in cfg.get("keys", [])]
    if not key_names:
        errors.append(
            "config/diff_ingest.json: 'keys' must list at least one key column")
    for entry in entries:
        name = entry.get("dataset")
        if name not in ctx.datasets:
            errors.append(
                f"config/diff_ingest.json: dataset '{name}' is not defined in datasets.json")
            continue
        cols = set(ctx.datasets[name].columns)
        if not entry.get("result_type") and not entry.get("direction_column"):
            errors.append(
                f"config/diff_ingest.json: '{name}' needs 'result_type' or 'direction_column'")
        if entry.get("direction_column") and entry["direction_column"] not in cols:
            errors.append(
                f"config/diff_ingest.json: '{name}' direction_column not in mapping")
        for key in cfg.get("keys", []):
            column = key if isinstance(key, str) else key.get(
                "column", key.get("name"))
            if column not in cols:
                errors.append(
                    f"config/diff_ingest.json: key column '{column}' not in dataset '{name}' mapping")
        for column in cfg.get("compare_fields", []):
            column = column if isinstance(column, str) else column.get("name")
            if column not in cols:
                errors.append(
                    f"config/diff_ingest.json: compare field '{column}' not in dataset '{name}' mapping")
    return errors


def _validate_analysis_snapshots(ctx: ProjectContext) -> List[str]:
    errors: List[str] = []
    snapshots = ctx.analysis_snapshots.get("analysis_snapshots", [])
    if not isinstance(snapshots, list):
        return ["config/config.yaml: 'analysis_snapshots' must be a list"]
    seen = set()
    for index, snapshot in enumerate(snapshots):
        if not isinstance(snapshot, dict):
            errors.append(
                f"config/config.yaml: analysis_snapshots[{index}] must be an object")
            continue
        name = snapshot.get("name") or snapshot.get("dataset")
        dataset_name = snapshot.get("dataset")
        if not dataset_name or dataset_name not in ctx.datasets:
            errors.append(
                f"config/config.yaml: snapshot '{name}' references unknown dataset '{dataset_name}'")
            continue
        if name in seen:
            errors.append(
                f"config/config.yaml: duplicate snapshot name '{name}'")
        seen.add(name)
        dataset = ctx.datasets[dataset_name]
        columns = set(dataset.columns)
        for lookup_key in snapshot.get("lookup_keys", []) or []:
            if lookup_key not in columns:
                errors.append(
                    f"config/config.yaml: snapshot '{name}' lookup key '{lookup_key}' is not in dataset '{dataset_name}'")
        date_column = snapshot.get("snapshot_date_column")
        if date_column and date_column not in columns:
            errors.append(
                f"config/config.yaml: snapshot '{name}' date column '{date_column}' is not in dataset '{dataset_name}'")
        expected_table = dataset.filtered_table
        if snapshot.get("table") not in (None, expected_table):
            errors.append(
                f"config/config.yaml: snapshot '{name}' table must be '{expected_table}'")
    return errors


def _validate_rules(ctx: ProjectContext) -> List[str]:
    from .conditions import validate_condition

    errors: List[str] = []
    rules_cfg = ctx.rules
    classifications = set((rules_cfg.get("classifications") or {}).keys())
    if not classifications:
        errors.append(
            "rules/known_discrepancies.json: 'classifications' must define at least one classification")
    default = rules_cfg.get("default", {})
    if default.get("classification") and default["classification"] not in classifications:
        errors.append(
            "rules/known_discrepancies.json: default.classification is not a declared classification")
    codes = set()
    for rule in rules_cfg.get("rules", []):
        code = rule.get("code")
        where = f"rules/known_discrepancies.json rule '{code}'"
        if not code:
            errors.append(
                "rules/known_discrepancies.json: every rule needs a 'code'")
            continue
        if code in codes:
            errors.append(f"{where}: duplicate code")
        codes.add(code)
        if rule.get("classification") not in classifications:
            errors.append(
                f"{where}: classification '{rule.get('classification')}' is not declared")
        if "when" in rule:
            errors.extend(
                f"{where}: {problem}" for problem in validate_condition(rule["when"]))
        sql_check = rule.get("sql_check")
        if sql_check:
            query = str(sql_check.get("query", "")).strip().lower()
            if not (query.startswith("select") or query.startswith("with")):
                errors.append(
                    f"{where}: sql_check.query must be a SELECT statement")
            if sql_check.get("expect", "exists") not in ("exists", "not_exists"):
                errors.append(
                    f"{where}: sql_check.expect must be 'exists' or 'not_exists'")
        if not ("when" in rule or sql_check or rule.get("python_check")):
            errors.append(
                f"{where}: needs at least one of 'when', 'sql_check', 'python_check'")
    return errors


def get_logger(ctx: ProjectContext) -> logging.Logger:
    logger = logging.getLogger(f"parity.{ctx.slug}.{abs(hash(str(ctx.root)))}")
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        log_dir = ctx.path(ctx.project.get("paths", {}).get("logs", "logs"))
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(
            log_dir / "pipeline.log", encoding="utf-8")
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    return logger
