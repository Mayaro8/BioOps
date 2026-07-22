import os


# Existing endpoint tests exercise application behavior without an identity
# provider. Authentication-specific tests enable it explicitly.
os.environ.setdefault("BIOOPS_SSO_ENABLED", "false")
