# Spec reference (`specs/<slug>.spec.json`)

A spec is the confirmed design of one parity project. The generator splits it into the project's config files. Full examples: [comparison workflow](../examples/mode-a-price-compare/spec.json), [supplied-report workflow](../examples/mode-b-mismatch-report/spec.json). When one business project needs both workflows, use mode `AB` and include both `comparison` and `diff_ingest` sections in that single spec.

```jsonc
{
  "spec_version": 1,
  "project":   { ... },          // required
  "database":  { ... },          // optional
  "processing":{ ... },          // optional
  "datasets":  [ ... ],          // required
  "filters":   { ... },          // optional
  "comparison":{ ... },          // Mode A or AB (required)
  "diff_ingest":{ ... },         // Mode B or AB (required)
  "known_discrepancies": { ... },// optional (defaults to 3 classifications, no rules)
  "llm":       { ... },          // optional
  "analysis_snapshots": [ ... ], // optional; generates config/config.yaml
  "reports":   { ... },          // optional
  "samples":   { ... }           // optional, for --with-samples
}
```

## project → `config/project.json`
| Field | Required | Notes |
|---|---|---|
| `name` | yes | Display name; also prefixes agent names |
| `slug` | yes | lowercase letters/digits/hyphens; used in file names |
| `mode` | yes | `A` (compare files), `B` (analyse a supplied mismatch report), or `AB` (both workflows in one generated project) |
| `description`, `owner` | no | Shown in README and docs |
| `python` | no | Command used in agent instructions (default `python`) |

## database / processing
- `database`: `{"engine": "sqlite" | "duckdb", "path": "db/parity.db"}`
- `processing`: `{"batch_size": 50000}` — rows per streaming batch in every stage.

## datasets[] → `config/datasets.json` + `config/mappings/<name>.mapping.json`
| Field | Notes |
|---|---|
| `name` | snake_case; tables are `raw_<name>` and `flt_<name>` |
| `role` | `source` / `target` (Mode A), `diff` (Mode B), `reference` (extra analysis data) |
| `description` | Where the file comes from and how to obtain it (shown in the folder README) |
| `connector` | Input acquisition. v1 implements `{"type": "local", "folder": "input/source", "file_pattern": "prices_*.csv", "selection": "latest" \| "all" \| "single"}`. `sqlserver`, `sftp`, `azure_blob`, `s3`, and `gcs` are planned contract names but require implementation before use. |
| `format` | csv: `{"type": "csv", "delimiter": ",", "header": true, "encoding": "utf-8-sig", "skip_rows": 0, "quotechar": "\""}`; fixed width: `{"type": "fixed_width", "strip_values": true}`; jsonl: `{"type": "jsonl"}`. Any format may add `"skip_lines_starting_with": ["#"]` and `"extract": {"from_column": "Message", "pattern": "<regex with (?P<name>...) groups>", "on_no_match": "skip" \| "keep" \| "error"}` |
| `load_policy` | `{"mode": "replace"}` or `{"mode": "append", "dedupe_on": ["col", ...]}` (default dedupe: all columns) |
| `columns` | list of `{"name", "type", "source" \| "start"+"end" \| "index", "required": true, "default": null}`. `source` = header (csv), regex group (extract) or JSON path (jsonl); `start`/`end` are 1-based inclusive (fixed width); `index` is 0-based (headerless csv). Types: string, integer, decimal, date, datetime |

## filters → `config/filters.json`
```json
{"<dataset>": {"scope": "latest_load" | "all",
               "include": [{"name": "...", "reason": "...", "condition": {...}}],
               "exclude": [{"name": "...", "reason": "...", "condition": {...}}]}}
```
Condition: `{"column": "c", "op": "eq|ne|in|not_in|gt|ge|lt|le|between|like|not_like|is_empty|not_empty", "value": ...}`; combine with `{"all": [...]}`, `{"any": [...]}`, `{"not": {...}}`. Numeric values compare numerically. Advanced: `{"sql": "<expression>", "params": [...]}`.

## comparison (Mode A or AB) → `config/comparison.json`
```json
{"source": "<dataset>", "target": "<dataset>",
 "keys":   [{"name": "store", "source": "STORE", "target": "store_no", "type": "string", "zero_pad": 4}],
 "fields": [{"name": "retail", "source": "RTL", "target": "retail", "type": "decimal", "tolerance": 0.001},
            {"name": "eff", "source": "EFF", "target": "eff_date", "type": "date", "source_format": "%d/%m/%Y", "target_format": "%Y-%m-%d"}],
 "options": {"trim": true, "case_sensitive": true}}
```
Normalisation options per key/field: `trim`, `case` (`upper`/`lower`), `zero_pad`, `strip_leading_zeros`, `null_values`, `format` / `source_format` / `target_format`, `scale`, `tolerance`, `thousands`.

## diff_ingest (Mode B or AB) → `config/diff_ingest.json`
```json
{"inputs": [{"dataset": "diff_src_only", "result_type": "MISSING_IN_TARGET"},
            {"dataset": "diff_tgt_only", "result_type": "MISSING_IN_SOURCE"}],
 "keys": [{"name": "store", "column": "store", "type": "string"}],
 "compare_fields": [{"name": "retail_price", "column": "retail_price", "type": "decimal"}],
 "pair_opposite_directions": true}
```
Single-file reports: `{"dataset": "diffs", "direction_column": "direction", "direction_map": {"<value>": "MISSING_IN_TARGET", ...}}`.

## known_discrepancies → `rules/known_discrepancies.json`
```json
{"classifications": {"EXPECTED": "...", "DATA_ISSUE": "...", "POTENTIAL_ISSUE": "..."},
 "default": {"classification": "POTENTIAL_ISSUE", "confidence": 0, "hypothesis": "...", "evidence_needed": "..."},
 "rules": [{"code": "KD-1", "title": "...", "description": "business explanation",
            "classification": "EXPECTED", "priority": 10, "confidence": 0.9, "enabled": true,
            "applies_to": ["MISMATCH"],
            "when": {"all": [{"field": "mismatch_fields", "op": "eq", "value": ["dealer_price"]},
                             {"field": "details.dealer_price.source", "op": "eq", "value": 0}]},
            "sql_check": {"query": "SELECT 1 FROM flt_events WHERE sku = :sku", "params": {"sku": "key.sku"}, "expect": "exists"},
            "python_check": "function_in_custom_rules",
            "hypothesis": "Text with {key.sku} placeholders",
            "evidence_needed": "What a reviewer checks"}]}
```
Record paths: `result_type`, `mismatch_fields` (list), `key.<name>`, `source.<column>`, `target.<column>`, `details.<field>.source|target`. Rule ops: everything from filters plus `contains`, `not_contains`, `regex`, `days_diff` (with `field2`), `abs_diff_le` (with `field2`), and any op with `field2` instead of `value` to compare two fields. A rule needs at least one of `when`, `sql_check`, `python_check`; all present checks must pass.

## llm → `config/project.json` `llm`
```json
{"enabled": true, "classifications": ["POTENTIAL_ISSUE"], "max_rows_per_batch": 50, "max_batches": 20,
 "priority": ["MISMATCH", "MISSING_IN_TARGET", "MISSING_IN_SOURCE"],
 "evidence_queries": [{"name": "events", "query": "SELECT * FROM flt_events WHERE sku = :sku", "params": {"sku": "key.sku"}}]}
```

## analysis_snapshots → `config/config.yaml`

Use this section to declare reference data that must be retrieved and stored locally before deterministic or LLM analysis. If omitted, reference datasets are generated as required snapshots with their dataset name.

```json
{"name": "price_events", "dataset": "price_events", "required_for_analysis": true,
 "lookup_keys": ["store", "sku"], "snapshot_date_column": "event_date",
 "description": "Events required to explain price timing differences"}
```

The generator adds the target filtered table, connector selection, and load policy from the referenced dataset. `precheck` validates the dataset, table, lookup keys, and date column. `classify` blocks when a required snapshot table is missing or empty.

## reports and output delivery
`{"formats": ["xlsx", "csv"]}`

The report engine writes locally under the configured output directory, normally `output/reports/`, and writes review feedback under `output/feedback/`. This is report generation, not remote publishing.

When a project needs automatic delivery, define a separate output-publisher design with the destination type, target path/container, file allow-list, overwrite policy, credential source, and delivery audit. Possible publishers are local shared-folder, FTP/SFTP, Azure Blob, S3, GCS, or an HTTP/API endpoint. No output publisher is implemented in factory v1.

## samples
`{"<dataset>": "relative/path/from/spec/to/sample.csv"}` — copied into the dataset folder with `--with-samples` for dry runs.
