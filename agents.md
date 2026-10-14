# Accelerate: local-repository agent architecture

This branch implements local engineering challenges with FastAPI, LangGraph,
Pydantic, Google GenAI, and OpenRouter fallback.

## Product direction

Learners work in the real repository at the selected fix's parent SHA. Provide
an issue statement, acceptance criteria, relevant paths, and deterministic checkout
commands. Learners use local editors, dependencies, tests, and build tools. Reveal
the original maintainer commit/diff on request for self-comparison. Alternative
correct solutions are welcome; patch similarity is not a correctness score.

Do not implement a hosted editor, learner-code execution, synthetic hidden tests,
or LLM-generated reference solutions. Optional AI patch review is future work.

## Contracts

- RepositoryInput: normalized GitHub URL or owner/repository.
- CommitData: repository, full fix SHA, actual first-parent SHA, diff, changed files,
  commit message, and optional PR description. This is private solution evidence.
- CodeContext: authoritative before/after snapshots, reconstructed issue,
  requirements, relevant paths, and missing evidence.
- GeneratedProblem: title, description, constraints, observable acceptance criteria,
  relevant paths, setup notes, verification notes, and internal source SHA.
- Public challenge: excludes solution evidence; adds checkout commands, parent SHA,
  relevant directories, and file links at the parent revision.
- Solution reveal: actual maintainer diff and metadata plus local comparison commands.

## Agents and workflow

1. Curator scans up to 50 commits and selects a concrete engineering change.
   Message heuristics use word boundaries; LLM assessment checks actual evidence.
2. Engineering Analyst uses a bounded LangGraph fetch/analyze loop to reconstruct
   the issue. Fetch files at the actual parent SHA and fixed SHA, including requested
   dependencies. Reject unresolved context after the limit.
3. Challenge Creator uses a bounded draft/ground/validate loop. Generate an issue
   statement and observable acceptance criteria, not an implementation recipe.
   Ground the relevant paths before validating the final learner task. Invalid
   draft JSON or invented paths must consume a bounded retry. Setup/test commands
   must be supported by evidence; otherwise direct learners to checked-out docs
   and say that setup has not been verified.
4. Persist the accepted challenge immutably. Build checkout commands in application
   code using validated repository identifiers and full SHAs, never LLM shell text.
5. Reveal the stored GitHub patch on demand, without provider calls or code execution.

The top-level LangGraph composes Curator -> Analyst -> Creator. FastAPI handles
persistence and reveal. Generation is synchronous for now; background jobs and
candidate reselection after downstream rejection remain explicit follow-up work.

## Cache and cost policy

Check saved challenges before running agents. Default requests to cache-only mode;
never silently fall back to paid generation on a cache miss. Live generation may
reuse SHA-keyed analyst snapshots before GitHub scouting. An analyst snapshot
saves analysis/scouting calls, but new drafting/validation still uses a provider.

Prefer the existing Flask/xxHash caches and checked-in demo evidence for development.
Mock all providers in automated tests and explicitly disable inherited API credentials
where provider adapters are tested. Do not run paid smoke tests without task authorization.

## Validation and privacy

Use the parent SHA as the learner baseline; checking out the fix would reveal the answer.
Do not include the fix SHA, diff, solution, or PR description in normal public responses.
The reveal endpoint is a learner-controlled boundary, not access control over a public
Git repository. Do not claim that tests passed or a challenge is verified when no
repository execution evidence exists. Keep cache files, databases, credentials,
bytecode, node_modules, and build output out of Git.
