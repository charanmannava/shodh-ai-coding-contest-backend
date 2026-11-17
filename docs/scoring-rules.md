# Scoring rules

- Each contest assignment pins a problem version, test-suite version, and point weight.
- Test cases are immutable rows within that suite; only `is_sample=true` cases and their expected outputs are returned by the problem API.
- Output comparison trims surrounding whitespace and compares the remaining lines exactly.
- A fully passing suite is `ACCEPTED` with 100%; a partial pass is `WRONG_ANSWER` with integer percentage `passed * 100 // total`.
- Compilation, runtime, timeout, and judge infrastructure errors produce zero points.
- Contest points are `percentage * assignment points // 100`.
- A participant's leaderboard score uses their best authoritative completed submission for each assigned problem. A rejudge is authoritative only after completion and only if its attempt number is newer; prior attempts remain available to organizers.
