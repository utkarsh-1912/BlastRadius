"""
python-dotenv sets a blank `.env` line (e.g. `AWS_PROFILE=`) as an actual
empty-string environment variable, not an unset one. `os.environ.get(name)`
then returns `""`, which most of our own `if profile:` checks correctly
treat as falsy — but botocore's OWN internal config providers read
AWS_PROFILE (and a few others) directly from the process environment,
independent of what gets passed into `boto3.Session(profile_name=...)`, and
choke on an empty string with a confusing `ProfileNotFound(profile='')`.

Call `clean_blank_env()` once, right after `load_dotenv()`, in every
entrypoint (server/main.py, scripts/*.py, integrations/*/server.py) so a
`.env` copied from `.env.example` with optional fields left blank behaves
exactly like those fields being absent.
"""
from __future__ import annotations

import os

# Names botocore/boto3 inspect directly from the environment, where "set but
# empty" and "unset" must not be allowed to behave differently.
_SENSITIVE_TO_BLANK = [
    "AWS_PROFILE",
    "AWS_DEFAULT_PROFILE",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_ENDPOINT_URL",
    "AWS_REGION",
    "AWS_DEFAULT_REGION",
]


def clean_blank_env(extra_names: list[str] | None = None) -> None:
    for name in _SENSITIVE_TO_BLANK + (extra_names or []):
        if os.environ.get(name, None) is not None and os.environ[name].strip() == "":
            del os.environ[name]
