# Parity Project Factory — rules for AI agents

This repository is a **template factory**, not a parity project. It produces standalone parity projects.

- `core/parity_core/` — the shared, domain-independent engine copied into every generated project. Changes here must stay generic (no project names, systems or business rules), keep Python 3.9 compatibility, and pass `python -m unittest discover -s tests`.
- `templates/project/` — files rendered into each project. `{{placeholder}}` values come from `factory/new_project.py::build_context`; `.modeA.` / `.modeB.` in a file name limits it to that mode; `__slug__` is replaced by the project slug.
- `factory/new_project.py` — spec -> project generator. `factory/inspect_sample.py` — sample-file inspector used while designing mappings.
- `examples/` — reference specs with sample data; they double as end-to-end test fixtures.
- `specs/` — specs written by the Parity Project Designer agent for real projects.

Rules:
1. Start new projects with the **Parity Project Designer** agent. Never hand-build a project by copying folders.
2. Agents orchestrate; scripts process data. Do not add LLM-dependent steps where a deterministic script or SQL can do the job.
3. Never put credentials or real production data in this repository.
4. When you change `parity_core` or templates, rerun the tests and regenerate the examples to make sure both modes still work.
