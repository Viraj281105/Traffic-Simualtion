#!/usr/bin/env python3
"""Container entrypoint: fix /app/data ownership, then drop to appuser.

The image itself is built with /app owned by appuser (see Dockerfile), so a
brand-new named volume mounted at /app/data is correctly seeded with that
ownership by Docker on first creation. But a volume created by an earlier
version of this image (which ran as root) keeps its existing root:root
ownership when reused — Docker only seeds ownership on a volume's first
ever use, not on every start. Without this fix, upgrading an existing
deployment to the non-root image would fail immediately with a permission
error on the SQLite database. This runs as root just long enough to correct
ownership, then permanently drops privileges via setgid/setuid before
exec'ing the real application, so the actual server process never runs as
root either way.
"""

import os
import pwd
import sys

APP_USER = "appuser"
DATA_DIR = "/app/data"


def main() -> None:
    if os.getuid() == 0:
        user = pwd.getpwnam(APP_USER)
        os.makedirs(DATA_DIR, exist_ok=True)
        for root, dirs, files in os.walk(DATA_DIR):
            os.chown(root, user.pw_uid, user.pw_gid)
            for name in dirs + files:
                os.chown(os.path.join(root, name), user.pw_uid, user.pw_gid)
        os.setgid(user.pw_gid)
        os.initgroups(APP_USER, user.pw_gid)
        os.setuid(user.pw_uid)

    os.execvp(sys.argv[1], sys.argv[1:])


if __name__ == "__main__":
    main()
