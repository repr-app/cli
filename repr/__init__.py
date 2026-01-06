"""
Repr CLI - Privacy-first developer profile generator.

Analyzes your local git repositories and generates a compelling
developer profile without ever sending your source code to the cloud.
"""

try:
    from importlib.metadata import version
    __version__ = version("repr-cli")
except Exception:
    # Fallback for PyInstaller builds where metadata isn't available
    __version__ = "0.2.8"
__author__ = "Repr"
__email__ = "hello@repr.dev"
