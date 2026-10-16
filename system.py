#!/usr/bin/env python3
"""Prepare a system request for the connected MCP agent; no AI CLI is executed."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ai_extract import task_cli

if __name__ == "__main__":
    task_cli("system")
