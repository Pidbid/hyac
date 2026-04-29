"""Core package for HYAC server.

Keep this package initializer side-effect free. Importing individual helpers such
as ``core.passwords`` should not eagerly initialize configuration, database,
Docker, MinIO, or JWT modules.
"""
