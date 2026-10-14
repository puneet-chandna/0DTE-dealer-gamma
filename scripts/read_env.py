"""Read and validate local app URLs with the backend's dotenv semantics."""

import os
import sys
from urllib.parse import urlsplit

from dotenv import dotenv_values

filename, key, *defaults = sys.argv[1:]
values = dotenv_values(filename)
environment = os.environ
if key == "DATABASE_URL":
    # Backend settings are case-insensitive; Next.js variable names are not.
    values = {name.upper(): value for name, value in values.items()}
    environment = {name.upper(): value for name, value in environment.items()}
value = environment.get(key, values.get(key))
if value is None:
    value = defaults[0] if defaults else ""

if not value:
    sys.exit(f"Error: {key} is missing or empty in the environment or {filename}.")

try:
    parsed = urlsplit(value)
    port = parsed.port
    if key == "DATABASE_URL":
        if parsed.scheme == "sqlite+aiosqlite":
            valid = value.startswith("sqlite+aiosqlite://") and not parsed.netloc
        else:
            valid = (
                parsed.scheme in {"postgres", "postgresql", "postgresql+asyncpg"}
                and bool(parsed.hostname)
            )
    else:
        schemes = {"http", "https"} if key == "NEXT_PUBLIC_API_URL" else {"ws", "wss"}
        valid = parsed.scheme in schemes and bool(parsed.hostname)
    valid = valid and port != 0 and not any(ord(character) < 32 or ord(character) == 127 for character in value)
    if parsed.scheme != "sqlite+aiosqlite":
        valid = valid and not any(character.isspace() for character in value)
except ValueError:
    valid = False

if not valid:
    sys.exit(f"Error: {key} in the environment or {filename} has an unsupported or invalid URL.")
print(value)
