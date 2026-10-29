#!/usr/bin/env python
"""Công cụ dòng lệnh để chạy các tác vụ quản lý Django."""
import os
import sys


def main():
    """Chạy tác vụ quản lý được truyền từ dòng lệnh."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
