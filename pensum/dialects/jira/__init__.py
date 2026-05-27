"""Jira dialect family: DC and Cloud share the common module, diverge in dc/cloud."""

from pensum.dialects.jira.cloud import JiraCloudDialect
from pensum.dialects.jira.dc import JiraDCDialect

__all__ = ["JiraCloudDialect", "JiraDCDialect"]
