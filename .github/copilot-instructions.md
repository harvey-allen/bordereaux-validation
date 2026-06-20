# GitHub Copilot Instructions

When proposing, generating, or modifying code for this repository, always follow these rules:

- Run `scripts/ci.sh` and ensure it passes before finalizing changes. If the environment does not allow command execution, state that clearly.
- Add or update tests for any functional change (minimum: affected unit tests; include integration coverage when behavior crosses module boundaries).
- Update documentation for new features or behavioural changes (for example: `README.md`, `docs/features.md`, `docs/architecture.md`, API or workflow docs as applicable).
- Follow existing code style, naming, project structure, and conventions already present in the repository.
- Prefer small, focused, self-contained changes that are easy to review; avoid broad refactors unless explicitly requested.
- Keep backend/frontend contracts in sync: whenever APIs or schemas change, update both sides together (including validation and typing where relevant).
- Do not introduce unrelated changes; if you notice adjacent issues, mention them separately rather than bundling them.
- In summaries, clearly list: what changed, which tests were run, and any follow-up actions required.
