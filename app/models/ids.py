"""Shared identity helpers so library modules can depend on each other without cycles."""
import datetime
import uuid


def new_id():
    return uuid.uuid4().hex


def valid_id(value):
    return isinstance(value, str) and len(value) == 32 and all(c in "0123456789abcdef" for c in value)


def now_stamp():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")
