"""Frozen entry point: stdout is reserved for the STDIO protocol."""

from xmu_rollcall.mcp_bridge.server import main

if __name__ == "__main__":
    main()
