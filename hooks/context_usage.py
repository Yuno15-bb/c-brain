#!/usr/bin/env python3
# Créé avec Codex
"""Lecture fail-open de l'empreinte de contexte d'un transcript Claude Code."""

import json
import os


def usage_tokens(usage):
    """Somme des tokens qui constituent le contexte relu par l'appel courant."""
    if not isinstance(usage, dict):
        return None
    return (
        usage.get("input_tokens", 0)
        + usage.get("cache_read_input_tokens", 0)
        + usage.get("cache_creation_input_tokens", 0)
    )


def read_context_tokens(transcript_path):
    """Retourne le dernier usage du transcript, ou ``None`` si indisponible."""
    if not transcript_path or not os.path.isfile(transcript_path):
        return None
    last = None
    try:
        with open(transcript_path, encoding="utf-8") as transcript:
            for line in transcript:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                usage = (obj.get("message") or {}).get("usage")
                if usage:
                    last = usage
    except OSError:
        return None
    return usage_tokens(last)
