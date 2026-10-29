"""Shared validation for human name fields, including Unicode digits."""
import unicodedata


def validate_person_name(value):
    if value is not None and any(unicodedata.category(char).startswith('N') for char in value):
        raise ValueError('Names must not contain numbers.')
    return value
