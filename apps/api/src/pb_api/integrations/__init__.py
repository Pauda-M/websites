"""External-system integrations.

Each subpackage connects Genesis to an outside system through a ports-and-adapters
boundary: provider-agnostic interfaces (ports) that business logic depends on, and
vendor-specific adapters that implement them. No business logic ever imports a
vendor SDK directly. The first integration is the enterprise digital workspace
(`workspace`), with Microsoft Graph as the primary adapter.
"""
