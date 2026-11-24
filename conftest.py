"""Pytest configuration – bootstraps Django before tests run."""

import os
import sys

# Ensure the project root is on sys.path so imports work.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import django
django.setup()
