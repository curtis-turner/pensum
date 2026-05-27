"""Jira Data Center dialect.

DC paths live under `/rest/api/2`. Search uses `/search` (covered in M6).
Descriptions use wiki markup (no ADF conversion). PAT or BasicAuth.
"""

from __future__ import annotations

from pensum.dialects.jira._base import JiraDialectBase


class JiraDCDialect(JiraDialectBase):
    name = "jira_dc"
    api_root = "/rest/api/2"
    expected_deployment_type = "Server"
