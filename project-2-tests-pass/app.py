"""Application code for the Maker-Checker demo.

This module intentionally starts with bugs / missing logic so the
tests in test_app.py fail on the first run. The loop.sh script drives
an AI agent (the Maker) to fix this file until pytest (the Checker)
reports success.
"""


def add(a, b):
    return a + b


def multiply(a, b):
    return a * b


def is_even(n):
    return n % 2 == 0
