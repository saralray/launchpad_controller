#!/usr/bin/env python3
"""Entry point for the Launchpad -> Home Assistant controller.

Kept as controller.py so the systemd unit / udev rule (see install-*.sh)
and their `WorkingDirectory` stay unchanged. Real logic lives in the
`launchpad` package.
"""

from launchpad.app import main

if __name__ == "__main__":
    main()
