# Working on Pipe CFD

- The user requires comparisons with reference research data as the model develops. Preserve source provenance, applicable conditions, measured deviations and limitations in the code and validation report.
- Distinguish analytical verification, experimental validation and empirical correlations. Never use reference values or synthetic outputs in place of actual CFD fields.
- Target Foundation OpenFOAM 14 on Ubuntu/WSL2. Check solver syntax against that distribution.
- Future scope: pipe/manifold/multiport channel-plate builder; CAD import, boundary selection, meshing and complex geometry; visualization evolves alongside those stages. See docs/ROADMAP.md.
- For physics changes, run the relevant benchmark and a meaningful mesh study. Record failed or unqualified comparisons as well as successful ones. Do not tune physical coefficients to conceal discrepancies.
- Keep generated cases, dependencies and simulation output out of Git. Commit small reproducible benchmark summaries, tests, source and reference provenance.
- Preserve local user work and existing repository history. Bind this local tool to localhost and use one backend worker.
