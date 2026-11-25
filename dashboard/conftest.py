"""Bootstrap Django before running dashboard tests."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dashboard_project.settings")

import django  # noqa: E402
django.setup()
