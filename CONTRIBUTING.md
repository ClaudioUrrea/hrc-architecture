# Contributing

Issues and pull requests are welcome, with two conditions specific to this
repository.

1. **Do not add a claim the artefact cannot support.** Every quantitative
   statement in the README, the docs and the manuscript belongs to one of four
   evidence classes — measured, simulated, estimated, projected — and carries a
   note on what limits its transferability. A pull request that adds a number
   should say which class it belongs to and add it to
   `analysis/check_against_paper.py`.
2. **Keep `make check` green.** It recomputes the headline quantities from the
   deposited data and fails if any drifts from the published value. If a change
   makes a published number wrong, the number is what must change, and the
   change belongs in `CHANGELOG.md`.

Reports of physical-hardware bring-up are especially welcome: nothing here has
been exercised on a real robot, and that is the first limitation stated in the
paper.
