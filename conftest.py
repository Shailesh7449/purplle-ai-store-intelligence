"""Ensures the project root is importable so `pytest` works from anywhere."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
