# Working on Pipe CFD

- The user requires comparisons with reference research data as the model develops. Preserve source provenance, applicable conditions, measured deviations and limitations in the code and validation report.
- Distinguish analytical verification, experimental validation and empirical correlations. Never use reference values or synthetic outputs in place of actual CFD fields.
- Target Foundation OpenFOAM 14 on Ubuntu/WSL2. Check solver syntax against that distribution.
- v0.6 delivers the inline pipe/bend/manifold/multi-port builder and full 3D fluid/solid face boundaries. v0.7 adds STEP/IGES/BREP closed-body import, explicit fluid/solid roles and port selection. Future scope: improved 3D discretization and wall layers, cavity extraction and broader geometry validation. See docs/ROADMAP.md.
- For physics changes, run the relevant benchmark and a meaningful mesh study. Record failed or unqualified comparisons as well as successful ones. Do not tune physical coefficients to conceal discrepancies.
- Keep generated cases, dependencies and simulation output out of Git. Commit small reproducible benchmark summaries, tests, source and reference provenance.
- Preserve local user work and existing repository history. Bind this local tool to localhost and use one backend worker.
- Every project update for the user must include how to reconnect and update: PowerShell `wsl -d Ubuntu-24.04`, then Ubuntu `cd ~/projects/pipe-cfd`, `git pull --ff-only`, `bash scripts/setup.sh`, `bash scripts/start.sh`; open http://localhost:5173 and keep the terminal open. Stop the existing app with Ctrl+C first. Clearly distinguish work in progress from changes already pushed.
- Keep inlet units and preset values in the shared material catalog. Preserve original benchmark properties and saved-run meanings. CFM is actual volume, glycol percentages are by mass, and the current model uses constant properties.
