---
name: Run Project1 Pipeline
agent: Project1 PM000003 Orchestrator
description: Run the Project1 PM000003 pipeline, resume it, or execute one independent task from the middle.
argument-hint: 'full | resume | status | task=<task-id> | from=<task-id>'
---

Read the Project1 pipeline, task state, confirmed requirements, and open clarifications.

User request: ${input:mode:full}

- Never assume missing values.
- For `task=<task-id>`, validate only that task's prerequisites and execute it independently.
- For `from=<task-id>`, verify the task's prerequisite evidence before starting.
- For `resume`, continue from the first unresolved task.
- For `status`, do not execute data-processing commands.
- Return evidence and `SUCCESS`, `PARTIAL`, `FAILED`, or `BLOCKED`.
