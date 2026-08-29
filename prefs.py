#!/usr/bin/env python3
"""
prefs.py - tiny persistent key/value store for user preferences (prefs.json,
next to this script). Currently just remembers the capture region so it doesn't
have to be re-set every run; more keys can be added freely.
"""

import json
import os

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prefs.json")


class Prefs:
    def __init__(self, path=PATH):
        self.path = path
        try:
            with open(path, encoding="utf-8") as fh:
                self._data = json.load(fh)
            if not isinstance(self._data, dict):
                self._data = {}
        except (OSError, ValueError):
            self._data = {}

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        if self._data.get(key) == value:
            return
        self._data[key] = value
        self._flush()

    def _flush(self):
        try:
            with open(self.path, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, indent=2)
        except OSError:
            pass
