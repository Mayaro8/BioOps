import os


# Existing endpoint tests exercise application behavior without an identity
# provider. Authentication-specific tests enable it explicitly.
os.environ.setdefault("YANDEX_AUTH_ENABLED", "false")
