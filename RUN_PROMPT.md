# RUN_PROMPT.md — paste this into Claude Code (fill in <TASK> first)

You are working autonomously in `/home/sreevenkat/Desktop/venkat/sem_project_all`.

1. Read `CLAUDE_AUTONOMOUS.md` (rules and verified commands), then `CLAUDE.md` (project log and decisions) and, if the task touches the
   next milestone, `HANDOFF.md`. Follow all of them. Where they conflict, ask me instead of guessing.

2. Task:

   <TASK>

3. Work in a loop until the definition of done in `CLAUDE_AUTONOMOUS.md` is met:
   - make ONE focused change;
   - run the lint command and the verify command(s) that apply to what you changed;
   - read the FULL output (including warnings), not just the last line;
   - if anything fails, find the root cause before editing, then fix it. Never retry the same fix twice;
   - never edit tests, golden vectors, expected outputs or the verify scripts to make them pass; never add error suppression;
   - after writing or changing a test or testbench, break the code on purpose once and confirm the test fails, then restore it.

4. Stop only when either:
   - the definition of done is met (lint and the applicable verify commands exit 0 in the same run, with the expected PASS counts and 0 SKIP,
     no tests removed/skipped/weakened, no error suppression added, `CLAUDE.md` Update Log updated), or
   - the same error has failed 3 attempts: then stop and report what you tried, what you saw each time, and what you suspect.

5. Do not commit or push unless I explicitly ask. If you commit when asked: short past-tense messages, no `Co-Authored-By` trailer, never force-push.

6. Finish by showing:
   - the final output of the lint and verify commands, pasted exactly as printed (with exit codes);
   - a summary of every file you changed and why;
   - anything you could not verify, and any assumptions you made.
