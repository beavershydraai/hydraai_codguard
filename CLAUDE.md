# CLAUDE.md

@AGENTS.md

## Working with the repo owner

- The owner reviews pull requests, not individual commits. Do the git work yourself: create the branch, commit, push and open the PR into `main` without asking for approval at each step.
- Do not merge your own PRs. The owner merges after review.
- Reply in the language the user writes in (usually Vietnamese). Keep chat replies short and put the detail in the PR description.

## Before opening a PR

- Run the relevant tests and linters once they exist, and report the result in the PR body. If something could not be run, say so.
- Re-read the matching "Done khi" row in `COD_Guard_Epics.md` and confirm the change meets it.
- Update `README.md` and `AGENTS.md` in the same PR when the change alters setup, commands, layout or a domain rule.

## After opening a PR

- Wait for the **CI result** check. If it fails, fix it and push again before telling the user the PR is ready.
- In the reply to the user, say whether CI passed.
