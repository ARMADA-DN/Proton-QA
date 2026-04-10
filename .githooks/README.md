This repository includes a pre-commit hook in .githooks/pre-commit.

What it does:
- Prevents committing large staged .ttl files unless they are tracked by Git LFS.
- Default threshold is 1 MiB (1048576 bytes).

Enable it locally:
- git config core.hooksPath .githooks

Optional threshold override:
- export TTL_LFS_THRESHOLD_BYTES=2097152
