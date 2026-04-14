# Copilot instructions for DatMail

## Documentation is part of feature completion

When a change adds or changes a feature, API, workflow, configuration requirement, runtime dependency, architecture path, or developer-facing behavior, update the relevant documentation before considering the task done.

This applies to:

- `README.md` for the project entrypoint and operator/developer basics
- `https://github.com/fredagscafeen/mail/wiki` for repo architecture, flow, code-map, and wiki-workflow docs

## Required documentation checks

Before completing feature work, check whether the change affects any of these:

1. setup or local run instructions
2. Docker/runtime behavior
3. configuration keys or secrets
4. message flow, resend flow, or monitoring flow
5. HTTP/API contracts
6. architecture or service boundaries
7. developer workflows, including the separate wiki repository workflow

If it affects any of them, update the matching docs in the same task.

## Wiki maintenance rule

The GitHub wiki is a separate repository: `git@github.com:fredagscafeen/mail.wiki.git`.

When a change should appear in the published wiki:

1. update the wiki repository pages
2. commit and push the wiki repository changes

Do not treat docs as optional follow-up work for completed features.
