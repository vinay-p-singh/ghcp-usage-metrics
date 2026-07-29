"""ghcp — pure, side-effect-free building blocks for the usage extractor.

Everything in this package is deterministic and independent of the machine's log
locations. The I/O scanners (which read real logs and are monkeypatched in tests
via the module-level path constants) deliberately stay in ``usage.py``.
"""
