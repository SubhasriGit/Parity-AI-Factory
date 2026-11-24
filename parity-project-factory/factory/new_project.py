"""Parity Project Factory: generate a parity project from a confirmed spec.

Usage:
  python factory/new_project.py --spec specs/my-project.spec.json --dest C:/work/my-project [--with-samples] [--git-init]
  python factory/new_project.py --spec specs/my-project.spec.json --validate-only
  python factory/new_project.py --dest C:/work/my-project --upgrade-core

The spec is produced (and confirmed with the user) by the "Parity Project
Designer" agent. See docs/SPEC_REFERENCE.md.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import yaml

FACTORY_ROOT = Path(__file__).resolve().parent.parent
CORE_DIR = FACTORY_ROOT / "core" / "parity_core"
TEMPLATE_DIR = FACTORY_ROOT / "templates" / "project"
FACTORY_VERSION = "1.0.0"

sys.path.insert(0, str(FACTORY_ROOT / "core"))
from parity_core import __version__ as CORE_VERSION  # noqa: E402
from parity_core.config import load_project, validate_project, write_json  # noqa: E402

PLACEHOLDER = re.compile(r"\{\{([a-z_]+)\}\}")
SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{1,40}$")
MODE_LABELS = {
    "A": "compare source and target files, then analyse the differences",
    "B": "analyse a difference report supplied by another tool",
    "AB": "support both source-to-target comparison and supplied mismatch-report workflows in one project",
}
DEFAULT_CLASSIFICATIONS = {
    "EXPECTED": "Known, accepted difference (explained by a known discrepancy)",
    "DATA_ISSUE": "Difference caused by bad or late data in one of the systems, not by the new system's logic",
    "POTENTIAL_ISSUE": "Unexplained difference that needs investigation; may be a bug",
}


class SpecError(Exception):
    pass


# ---------------------------------------------------------------------------
# Spec handling
# ---------------------------------------------------------------------------


def load_spec(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        spec = json.load(handle)
    problems = check_spec(spec)
    if problems:
        raise SpecError("Spec problems:\n  - " + "\n  - ".join(problems))
    return spec


def check_spec(spec: Dict[str, Any]) -> List[str]:
    problems = []
    project = spec.get("project", {})
    if not project.get("name"):
        problems.append("project.name is required")
    if not SLUG_RE.match(project.get("slug", "")):
        problems.append(
            "project.slug must be lowercase letters/digits/hyphens, starting with a letter (e.g. 'cpp-price-parity')")
    if str(project.get("mode", "")).upper() not in MODE_LABELS:
        problems.append(
            "project.mode must be 'A', 'B', or 'AB' (both workflows in one project)")
    if not spec.get("datasets"):
        problems.append("datasets: at least one dataset is required")
    mode = str(project.get("mode", "")).upper()
    if "A" in mode and not spec.get("comparison"):
        problems.append("Mode A needs a 'comparison' section")
    if "B" in mode and not spec.get("diff_ingest"):
        problems.append("Mode B needs a 'diff_ingest' section")
    for ds in spec.get("datasets", []):
        if not ds.get("columns"):
            problems.append(
                f"dataset '{ds.get('name')}': 'columns' (mapping) is required")
    text = json.dumps(spec).lower()
    for word in ("password", "secret", "apikey", "api_key", "connectionstring", "token"):
        if f'"{word}"' in text:
            problems.append(
                f"spec contains a '{word}' field - credentials must not be stored in the spec or config")
    return problems


def build_config(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Split the spec into the generated project's config files."""
    project = spec["project"]
    mode = project["mode"].upper()
    files: Dict[str, Any] = {}
    files["config/project.json"] = {
        "name": project["name"],
        "slug": project["slug"],
        "description": project.get("description", ""),
        "owner": project.get("owner", ""),
        "mode": mode,
        "database": spec.get("database", {"engine": "sqlite", "path": "db/parity.db"}),
        "processing": spec.get("processing", {"batch_size": 50000}),
        "paths": {"output": "output", "logs": "logs"},
        "llm": {
            "enabled": True,
            "classifications": ["POTENTIAL_ISSUE"],
            "max_rows_per_batch": 50,
            "max_batches": 20,
            "priority": ["MISMATCH", "MISSING_IN_TARGET", "MISSING_IN_SOURCE"],
            "evidence_queries": [],
            **spec.get("llm", {}),
        },
        "reports": {"formats": ["xlsx", "csv"], **spec.get("reports", {})},
    }
    datasets = []
    for ds in spec["datasets"]:
        mapping_path = f"config/mappings/{ds['name']}.mapping.json"
        files[mapping_path] = {"dataset": ds["name"], "columns": ds["columns"]}
        datasets.append({
            "name": ds["name"],
            "role": ds["role"],
            "description": ds.get("description", ""),
            "connector": ds.get("connector", {"type": "local", "folder": default_folder(ds), "file_pattern": "*", "selection": "latest"}),
            "format": ds.get("format", {"type": "csv", "delimiter": ",", "header": True}),
            "mapping": mapping_path,
            "load_policy": ds.get("load_policy", {"mode": "replace"}),
        })
    files["config/datasets.json"] = {"datasets": datasets}
    files["config/filters.json"] = {"datasets": spec.get("filters", {})}
    if "A" in mode:
        files["config/comparison.json"] = spec["comparison"]
    if "B" in mode:
        files["config/diff_ingest.json"] = spec["diff_ingest"]
    snapshot_specs = spec.get("analysis_snapshots")
    if snapshot_specs is None:
        snapshot_specs = []
        for dataset in datasets:
            if dataset["role"] != "reference":
                continue
            date_column = next((column["name"] for column in dataset.get("columns", [
            ]) if "date" in column["name"] or column.get("type") in ("date", "datetime")), None)
            snapshot_specs.append({
                "name": dataset["name"],
                "dataset": dataset["name"],
                "required_for_analysis": True,
                "lookup_keys": [],
                "snapshot_date_column": date_column,
                "description": dataset.get("description", ""),
            })
    files["config/config.yaml"] = {
        "version": 1,
        "analysis_snapshots": snapshot_specs,
    }
    for snapshot in files["config/config.yaml"]["analysis_snapshots"]:
        dataset = next(
            (item for item in datasets if item["name"] == snapshot.get("dataset")), None)
        if dataset:
            snapshot.setdefault("table", f"flt_{dataset['name']}")
            snapshot.setdefault(
                "selection", dataset["connector"].get("selection", "latest"))
            snapshot.setdefault("load_policy", dataset["load_policy"])
    kd = spec.get("known_discrepancies", {})
    files["rules/known_discrepancies.json"] = {
        "classifications": kd.get("classifications", DEFAULT_CLASSIFICATIONS),
        "default": kd.get("default", {
            "classification": "POTENTIAL_ISSUE",
            "confidence": 0.0,
            "hypothesis": "No known discrepancy pattern matched",
            "evidence_needed": "Manual or LLM investigation",
        }),
        "rules": kd.get("rules", []),
    }
    return files


def default_folder(ds: Dict[str, Any]) -> str:
    role = ds.get("role")
    if role == "reference":
        return f"reference/{ds['name']}"
    return f"input/{role}"


# ---------------------------------------------------------------------------
# Template context
# ---------------------------------------------------------------------------


def md_table(headers: List[str], rows: List[List[Any]]) -> str:
    def cell(value: Any) -> str:
        return str("" if value is None else value).replace("|", "\\|").replace("\n", " ")

    lines = ["| " + " | ".join(headers) + " |", "|" +
             "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(cell(v) for v in row) + " |" for row in rows]
    return "\n".join(lines)


def agent_names(name: str, mode: str) -> Dict[str, str]:
    agents = {
        "Setup": f"{name} Setup",
        "Loader": f"{name} Loader",
        "Filter": f"{name} Filter",
    }
    if "A" in mode:
        agents["Comparator"] = f"{name} Comparator"
    if "B" in mode:
        agents["Diff Ingestor"] = f"{name} Diff Ingestor"
    agents.update({
        "Classifier": f"{name} Classifier",
        "LLM Analyst": f"{name} LLM Analyst",
        "Reporter": f"{name} Reporter",
    })
    return agents


def build_context(spec: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, str]:
    project = config["config/project.json"]
    mode = project["mode"]
    name = project["name"]
    python = spec["project"].get("python", "python")
    datasets = config["config/datasets.json"]["datasets"]
    mappings = {d["name"]: config[d["mapping"]]["columns"] for d in datasets}
    rules_cfg = config["rules/known_discrepancies.json"]
    llm = project["llm"]
    now = datetime.now()

    ds_rows = []
    for d in datasets:
        policy = d["load_policy"]
        policy_text = policy.get("mode", "replace") + (
            f" (dedupe on {', '.join(policy['dedupe_on'])})" if policy.get("dedupe_on") else "")
        ds_rows.append([
            f"`{d['name']}`", d["role"], f"`{d['connector'].get('folder')}`", f"`{d['connector'].get('file_pattern', '*')}`",
            d["connector"].get("selection", "latest"), d["format"].get(
                "type", "csv"), policy_text, d.get("description", ""),
        ])
    datasets_table = md_table(["Dataset", "Role", "Folder", "File pattern", "Selection",
                              "Format", "Load policy", "Description / how to obtain"], ds_rows)

    stage_lines = [
        ("init-db", "create/check the local DB and tables (step 0.1)"),
        ("precheck", "validate config, input files, packages, DB connectivity"),
        ("load", "parse files into raw tables (source/target/diff + reference data, step 0.2-3)"),
        ("filter", "apply optional filtering rules into separate flt_ tables (steps 4-5)"),
    ]
    if "A" in mode:
        stage_lines.append(
            ("compare", "compare filtered source vs target on user-confirmed keys and fields (steps 6-7)"))
    if "B" in mode:
        stage_lines.append(
            ("ingest-diff", "load a supplied mismatch report into the shared results table (steps 6-7)"))
    stage_lines.extend([
        ("classify", "deterministic known-discrepancy classification (step 8)"),
        ("llm-export / LLM Analyst / llm-import",
         "LLM second pass on selected unresolved results (step 9)"),
        ("report", "CSV and optional Excel reports (step 10)"),
        ("review-import", "manual review feedback (step 11)"),
    ])
    stages_list = "\n".join(f"{i}. `{s}` — {d}" for i,
                            (s, d) in enumerate(stage_lines, start=1))

    agents = agent_names(name, mode)
    roles = {
        "Setup": "init-db, precheck, status",
        "Loader": "load input files into raw tables",
        "Filter": "apply filters into flt_ tables",
        "Comparator": "compare filtered source vs target on confirmed keys and fields",
        "Diff Ingestor": "convert a supplied mismatch report into shared parity results",
        "Classifier": "deterministic known-discrepancy classification",
        "LLM Analyst": "LLM second pass via llm-export / findings / llm-import",
        "Reporter": "reports and manual review import",
    }
    agent_roles = "\n".join(
        f"- `{full}` -> {roles[short]}" for short, full in agents.items())

    comparison_summary = ""
    diff_summary = ""
    definitions = []
    parity_configs = []
    if "A" in mode:
        cmp_cfg = config["config/comparison.json"]
        rows = []
        for section in ("keys", "fields"):
            for item in cmp_cfg.get(section, []):
                extras = {k: v for k, v in item.items() if k not in (
                    "name", "source", "target", "type")}
                rows.append([section[:-1], item["name"], item.get("source", item["name"]), item.get(
                    "target", item["name"]), item.get("type", "string"), json.dumps(extras) if extras else ""])
        comparison_summary = (
            f"Source dataset `{cmp_cfg['source']}` vs target dataset `{cmp_cfg['target']}`.\n\n"
            + md_table(["Role", "Name", "Source column",
                       "Target column", "Type", "Normalisation"], rows)
        )
        definitions.append("Comparison workflow: " + comparison_summary +
                           "\n\nRecords are paired on user-confirmed keys. Results can be `MISMATCH`, `MISSING_IN_TARGET`, `MISSING_IN_SOURCE`, or a duplicate-key result.")
        parity_configs.append("comparison.json")
    if "B" in mode:
        diff = config["config/diff_ingest.json"]
        rows = [[f"`{e['dataset']}`", e.get(
            "result_type") or f"from column `{e.get('direction_column')}`: {json.dumps(e.get('direction_map', {}))}"] for e in diff.get("inputs", [])]
        keys = [k if isinstance(k, str) else k.get("name")
                for k in diff.get("keys", [])]
        fields = [f if isinstance(f, str) else f.get("name")
                  for f in diff.get("compare_fields", [])]
        diff_summary = md_table(["Diff dataset", "Result type"], rows) + \
            f"\n\nKey: `{', '.join(keys)}`. Compared fields when pairing: `{', '.join(fields) or '-'}`. Pair opposite directions: {diff.get('pair_opposite_directions', True)}."
        definitions.append("Supplied-report workflow: " + diff_summary +
                           "\n\nOpposite-direction rows can be paired into one `MISMATCH`.")
        parity_configs.append("diff_ingest.json")
    parity_definition = "\n\n".join(definitions)
    parity_config_file = ", ".join(parity_configs)

    rules = sorted(rules_cfg.get("rules", []), key=lambda r: (
        r.get("priority", 1000), r.get("code", "")))
    kd_table = md_table(
        ["Priority", "Code", "Title", "Classification", "Applies to"],
        [[r.get("priority", 1000), r.get("code"), r.get("title"), r.get(
            "classification"), ", ".join(r.get("applies_to", []) or ["any"])] for r in rules],
    ) if rules else "_No known discrepancies defined yet. Use the `define-known-discrepancy` skill._"
    kd_details = "\n\n".join(
        f"### {r.get('code')} — {r.get('title')} ({r.get('classification')}, priority {r.get('priority', 1000)})\n\n"
        f"{r.get('description', '')}\n\n"
        f"- Applies to: {', '.join(r.get('applies_to', []) or ['any result type'])}\n"
        f"- Detection: `{json.dumps({k: r[k] for k in ('when', 'sql_check', 'python_check') if k in r})}`\n"
        f"- Evidence needed to confirm: {r.get('evidence_needed', '-')}"
        for r in rules
    ) or "_No known discrepancies defined yet._"
    classifications = rules_cfg["classifications"]
    evidence = llm.get("evidence_queries") or []
    entry_stages = ["compare"] if "A" in mode else []
    if "B" in mode:
        entry_stages.append("ingest-diff")
    cli_rows = [[f"`{s}`", f"`{python} scripts/parity.py {s}`"] for s in ["init-db", "precheck",
                                                                          "load", "filter", *entry_stages, "classify", "llm-export", "llm-import", "report", "status"]]
    cli_rows.append(
        ["`review-import`", f"`{python} scripts/parity.py review-import --file <workbook>`"])
    cli_rows.append(
        ["`query`", f"`{python} scripts/parity.py query \"SELECT ...\"`"])
    workflow_option = " --workflow <compare|ingest-diff>" if mode == "AB" else ""
    cli_rows.append(
        ["`run`", f"`{python} scripts/parity.py run{workflow_option} [--from X] [--to Y]`"])
    folders = sorted({d["connector"].get("folder") for d in datasets})

    return {
        "project_name": name,
        "slug": project["slug"],
        "description": project.get("description") or "_Describe the purpose of this parity project._",
        "owner": project.get("owner") or "-",
        "mode": mode,
        "mode_label": MODE_LABELS[mode],
        "python": python,
        "engine": project["database"].get("engine", "sqlite"),
        "db_path": project["database"].get("path", "db/parity.db"),
        "core_version": CORE_VERSION,
        "created_at": now.strftime("%Y-%m-%d %H:%M"),
        "created_date": now.strftime("%Y-%m-%d"),
        "datasets_table": datasets_table,
        "dataset_names": ", ".join(f"`{d['name']}` ({d['role']})" for d in datasets),
        "input_folders_inline": ", ".join(f"`{f}/`" for f in folders),
        "stages_list": stages_list,
        "agent_roles": agent_roles,
        "agent_list_quoted": ", ".join(f'"{a}"' for a in agents.values()),
        "agent_names_inline": ", ".join(agents.values()),
        "parity_agent_short": "Comparator or Diff Ingestor" if mode == "AB" else ("Comparator" if mode == "A" else "Diff Ingestor"),
        "run_command": f"{python} scripts/parity.py run{workflow_option}",
        "comparison_summary": comparison_summary,
        "diff_summary": diff_summary,
        "parity_definition": parity_definition,
        "parity_config_file": parity_config_file,
        "kd_table": kd_table,
        "kd_details": kd_details,
        "classifications_table": md_table(["Classification", "Meaning"], [[f"`{k}`", v] for k, v in classifications.items()]),
        "classification_names": ", ".join(f"`{k}`" for k in classifications),
        "default_classification": rules_cfg["default"].get("classification", "POTENTIAL_ISSUE"),
        "llm_classifications": ", ".join(f"`{c}`" for c in llm.get("classifications", [])),
        "llm_batch_size": str(llm.get("max_rows_per_batch", 50)),
        "llm_max_batches": str(llm.get("max_batches", "unlimited")),
        "evidence_queries": ", ".join(f"`{e['name']}`" for e in evidence) or "none configured (records only)",
        "cli_table": "\n".join("| " + " | ".join(r) + " |" for r in cli_rows),
    }


def render(text: str, context: Dict[str, str], source: Path) -> str:
    missing = sorted(
        {m for m in PLACEHOLDER.findall(text) if m not in context})
    if missing:
        raise SpecError(
            f"Template {source} uses unknown placeholder(s): {missing}")
    return PLACEHOLDER.sub(lambda m: context[m.group(1)], text)


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def copy_core(dest: Path) -> None:
    target = dest / "parity_core"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(CORE_DIR, target, ignore=shutil.ignore_patterns(
        "__pycache__", "*.pyc"))


def render_templates(dest: Path, context: Dict[str, str], mode: str) -> List[str]:
    written = []
    for src in sorted(TEMPLATE_DIR.rglob("*")):
        if src.is_dir():
            continue
        rel = src.relative_to(TEMPLATE_DIR).as_posix()
        if ".modeA." in rel and "A" not in mode:
            continue
        if ".modeB." in rel and "B" not in mode:
            continue
        rel = rel.replace(".modeA.", ".").replace(".modeB.", ".")
        rel = rel.replace("__slug__", context["slug"])
        if rel.endswith(".tmpl"):
            rel = rel[: -len(".tmpl")]
            text = render(src.read_text(encoding="utf-8"), context, src)
            write_text(dest / rel, text)
        else:
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest / rel)
        written.append(rel)
    return written


def folder_readmes(dest: Path, config: Dict[str, Any]) -> None:
    by_folder: Dict[str, List[dict]] = {}
    for d in config["config/datasets.json"]["datasets"]:
        by_folder.setdefault(d["connector"].get("folder"), []).append(d)
    for folder, items in by_folder.items():
        lines = [f"# {folder}", "",
                 "Put the following input file(s) here. Files in this folder are not committed to git.", ""]
        for d in items:
            cols = config[d["mapping"]]["columns"]
            policy = d["load_policy"]
            lines += [
                f"## Dataset `{d['name']}` ({d['role']})",
                "",
                d.get(
                    "description") or "_Describe where this file comes from and how to obtain it._",
                "",
                f"- File name pattern: `{d['connector'].get('file_pattern', '*')}` (selection: {d['connector'].get('selection', 'latest')})",
                f"- Format: `{json.dumps(d['format'])}`",
                f"- Load policy: `{policy.get('mode', 'replace')}`" + (
                    f", duplicates identified by {policy['dedupe_on']}" if policy.get("dedupe_on") else ""),
                "- Expected columns:",
                "",
                md_table(["Column", "From", "Type"], [[c["name"], c.get(
                    "source", f"{c.get('start', '')}-{c.get('end', '')}" if "start" in c else c.get("index", c["name"])), c.get("type", "string")] for c in cols]),
                "",
            ]
        write_text(dest / folder / "README.md", "\n".join(lines))
    write_text(dest / "db" / "README.md",
               "# db\n\nLocal analysis database (created by `init-db`). Not committed to git.\n")
    write_text(dest / "output" / "README.md",
               "# output\n\n- `reports/` Excel/CSV reports\n- `llm/<run_id>/` LLM batches and findings\n- `feedback/` manual review feedback\n")


def copy_samples(spec: Dict[str, Any], spec_dir: Path, dest: Path, config: Dict[str, Any]) -> List[str]:
    copied = []
    folders = {d["name"]: d["connector"].get(
        "folder") for d in config["config/datasets.json"]["datasets"]}
    for dataset, sample in (spec.get("samples") or {}).items():
        src = (spec_dir / sample).resolve()
        if not src.is_file():
            raise SpecError(f"Sample file for '{dataset}' not found: {src}")
        target_dir = dest / folders[dataset]
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, target_dir / src.name)
        copied.append(f"{folders[dataset]}/{src.name}")
    return copied


def generate(spec_path: Path, dest: Path, force: bool = False, with_samples: bool = False, git_init: bool = False) -> Dict[str, Any]:
    spec = load_spec(spec_path)
    spec["project"]["mode"] = spec["project"]["mode"].upper()
    if dest.exists() and any(dest.iterdir()) and not force:
        raise SpecError(
            f"{dest} exists and is not empty. Use --force to regenerate (data in input/, reference/, db/, output/ is kept).")
    backup = None
    if dest.exists() and any(dest.iterdir()):
        backup = dest / ".factory-backup" / datetime.now().strftime("%Y%m%dT%H%M%S")
        for item in ("config", "rules", ".github", "docs", "README.md"):
            src = dest / item
            if src.is_dir():
                shutil.copytree(src, backup / item)
            elif src.is_file():
                backup.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, backup / item)
    custom_rules = dest / "rules" / "custom_rules.py"
    kept_custom = custom_rules.read_text(
        encoding="utf-8") if custom_rules.exists() else None
    dest.mkdir(parents=True, exist_ok=True)
    config = build_config(spec)
    for rel, data in config.items():
        if rel.endswith((".yaml", ".yml")):
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            with open(dest / rel, "w", encoding="utf-8", newline="\n") as handle:
                yaml.safe_dump(data, handle, sort_keys=False)
        else:
            write_json(dest / rel, data)
    context = build_context(spec, config)
    written = render_templates(dest, context, spec["project"]["mode"])
    if kept_custom is not None:
        write_text(custom_rules, kept_custom)
    folder_readmes(dest, config)
    (dest / "logs").mkdir(exist_ok=True)
    copy_core(dest)
    samples = copy_samples(spec, spec_path.parent, dest,
                           config) if with_samples else []
    write_json(dest / ".parity-factory.json", {
        "factory_version": FACTORY_VERSION,
        "core_version": CORE_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "spec": spec,
    })
    ctx = load_project(dest)
    try:
        problems = validate_project(ctx)
    finally:
        ctx.close()
    if git_init and not (dest / ".git").exists():
        subprocess.run(["git", "init", "-q"], cwd=str(dest), check=False)
    return {"dest": str(dest), "config_files": sorted(config), "templates": written, "samples": samples, "backup": str(backup) if backup else None, "problems": problems}


def upgrade_core(dest: Path) -> Dict[str, Any]:
    marker = dest / ".parity-factory.json"
    if not marker.exists():
        raise SpecError(
            f"{dest} is not a factory-generated project (missing .parity-factory.json)")
    info = json.loads(marker.read_text(encoding="utf-8"))
    old = info.get("core_version")
    copy_core(dest)
    info["core_version"] = CORE_VERSION
    info["core_upgraded_at"] = datetime.now().isoformat(timespec="seconds")
    write_json(marker, info)
    return {"dest": str(dest), "core_version_before": old, "core_version_after": CORE_VERSION}


def main(argv: List[str] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a parity project from a spec")
    parser.add_argument("--spec", help="Path to <slug>.spec.json")
    parser.add_argument(
        "--dest", help="Destination folder for the new project (ideally its own repository)")
    parser.add_argument("--force", action="store_true",
                        help="Regenerate into an existing folder (data folders are kept)")
    parser.add_argument("--with-samples", action="store_true",
                        help="Copy the spec's sample files into the input folders (dry runs)")
    parser.add_argument("--git-init", action="store_true",
                        help="Initialise a git repository in the new project")
    parser.add_argument("--validate-only", action="store_true",
                        help="Check the spec by generating into a temp folder")
    parser.add_argument("--upgrade-core", action="store_true",
                        help="Only refresh parity_core/ in an existing project")
    args = parser.parse_args(argv)
    try:
        if args.upgrade_core:
            if not args.dest:
                parser.error("--upgrade-core needs --dest")
            print(json.dumps(upgrade_core(Path(args.dest).resolve()), indent=2))
            return 0
        if not args.spec:
            parser.error("--spec is required")
        spec_path = Path(args.spec).resolve()
        if args.validate_only:
            with tempfile.TemporaryDirectory() as tmp:
                result = generate(spec_path, Path(tmp) / "project")
            print(json.dumps({"spec": str(spec_path),
                  "problems": result["problems"]}, indent=2))
            return 1 if result["problems"] else 0
        if not args.dest:
            parser.error("--dest is required")
        result = generate(Path(args.spec).resolve(), Path(
            args.dest).resolve(), args.force, args.with_samples, args.git_init)
        print(json.dumps(result, indent=2))
        if result["problems"]:
            print("Generated, but the configuration has problems (see 'problems'). Fix the spec and regenerate with --force.")
            return 1
        print(
            f"Project ready. Next: cd \"{result['dest']}\" ; python scripts/parity.py init-db ; python scripts/parity.py precheck")
        return 0
    except SpecError as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
