# Parity AI Factory

This repository contains the reusable parity-project factory and a complete generated CPP implementation.

## Repository Layout

- `parity-project-factory/`: generator, reusable parity engine, templates, agents, examples, and factory tests.
- `parity-project-factory/Standalone project/CPP-PM000003-Parity-Analysis/`: runnable PM000003 parity analysis project with synthetic input data, databases, and reports.

## Getting Started

Open the subfolder that matches your task in VS Code:

- Factory development: `parity-project-factory/`
- PM000003 execution and reporting: `parity-project-factory/Standalone project/CPP-PM000003-Parity-Analysis/`

Each subfolder retains its own instructions and agent definitions. Run commands from the relevant subfolder.

## Validation

Factory tests:

```powershell
cd parity-project-factory
python -m unittest discover -s tests -v
```

CPP tests:

```powershell
cd "parity-project-factory/Standalone project/CPP-PM000003-Parity-Analysis"
python -m pytest -q
```

## Data Policy

The published CPP files are synthetic examples generated for demonstration and validation. Secrets, environment files, transient task state, logs, database lock files, and database backups remain excluded from Git.
