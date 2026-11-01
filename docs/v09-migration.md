# AutoResearch 0.9.0 migration notes

This release reduces AutoResearch to its core loop: baseline, one trial, a decision by measurement, history, and promotion. It removes features that had no real use and one of the two storage formats. This page lists only the user-visible changes.

## Check your labs first

- SQLite labs from 0.8.0 open without any change. The database schema is the same.
- A lab stored as plain files fails with `E_LEGACY_LAB`, and its files stay as they are. Check out git tag `v0.8.0` to open or export it.
- Lab ids and each lab's `contract_fingerprint` do not change, so harness profiles stay valid.

## Removed commands

| Removed | Use instead |
| --- | --- |
| `trial` without a subcommand, `step`, `--hypothesis <file>` | `trial start` with `--hypothesis-json` or `--title`, `--observation`, `--expected-effect`, then `trial wait` |
| `epoch open`, `baseline --supersede` | Prepare a new lab when the contract changes |
| `prepare --auto`, `--eval`, `--metric`, `--repeats` | `preflight`, then `prepare --spec <spec.json> --confirmed`, then a separate baseline |
| `dashboard ensure`, `--headless`, `--no-dashboard`, `--no-browser` | `dashboard start`, with `--open-browser` if you want a browser tab |
| `init`, `setup`, `report`, `compat`, `archive`, `history-import`, `roots`, `catalog` | `prepare` and `guide` |
| `storage migrate`, `storage cleanup` | None. `storage export` and `storage reconcile` remain |
| `probe`, `replay`, `ingest`, `cases diff` | None |

A removed command or flag now fails with an argument error.

## Dashboard

- The dashboard no longer starts by itself. Run `dashboard start` to watch progress.
- It is read-only. Every write method on `/api/v1` returns 405.
- You can no longer archive, restore or delete a lab, because the browser buttons were the only way to do it. Archived labs stay hidden from the default list.
- The offline HTML page is gone.

## Environment variables

`AUTORESEARCH_NO_DASHBOARD`, `AUTORESEARCH_NO_BROWSER` and `AUTORESEARCH_WIRE_LOG*` are no longer read. AutoResearch no longer records request bodies or `sent-requests.jsonl`. It still journals attempts, so `resume` works as before.

## Specs

- A new spec that declares `baseline_validation.request_identity` or `budget.openrouter` is refused, because neither has any effect now.
- A stored lab that declared `request_identity` still opens, but that gate no longer runs.
- A lab first prepared with `budget.openrouter` gets a different lab id if you prepare it again. The existing lab still opens by its stored id.

## Behaviour

- A duplicate `baseline` is refused immediately. It used to leave the lab blocked until `recover`.
- `trial start` no longer fills `rationale` from the observation and expected effect.
- The bundled `openresearch` skill is gone, and the advice to consult it no longer names it.
