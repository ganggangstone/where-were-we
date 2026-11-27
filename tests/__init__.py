"""Lets `python -m unittest tests.<module>` from the repository root import sibling test modules by their top-level names."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
