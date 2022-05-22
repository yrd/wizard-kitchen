import os

from django.core import management


def execute_management_from_command_line() -> None:
    """Run the default Django command line handler."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cookpot.settings")
    management.execute_from_command_line()
