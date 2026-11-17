# Architecture

```text
Client
  └── FastAPI ── PostgreSQL
                   ├── version-pinned submissions
                   ├── judge attempts and verdicts
                   └── transactional judge jobs
                          └── independent workers (SKIP LOCKED)
                                └── restricted Python Docker container
```

- API and worker processes share PostgreSQL; there is no in-memory queue.
- A submission transaction inserts the submission, first attempt, and job together.
- Workers lease one eligible job with `FOR UPDATE SKIP LOCKED`. A stale `RUNNING` lease can be reclaimed; retry counts are bounded.
- A submission stores both `problem_version_id` and `suite_id`. A contest assignment separately records the version, suite, and point weight.
- Each attempt has one immutable verdict. Completion updates the authoritative pointer only when its attempt number is greater than the current authoritative attempt.
- Leaderboard scoring takes each participant's best score per assigned problem from authoritative completed results.
- Every user-facing data query is organization-scoped; private submissions are visible only to their owner and same-organization organizers/admins.
- Request logs are JSON and carry request IDs; submission/worker events also carry submission and attempt IDs.

## Deliberate security boundary

The Docker socket is a privileged host interface. It is mounted only into the worker service, never into the API. Keep worker hosts isolated, restrict who can reach them, and protect the socket and database credentials. Judge containers disable networking, use a read-only root filesystem and non-root UID, drop Linux capabilities, and enforce Docker resource limits. This is a practical first-version container boundary, not a substitute for a hardened multi-tenant VM/microVM service.
