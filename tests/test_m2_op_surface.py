"""M2 expanded op surface: every op in pensum.op, end-to-end via respx.

Each test sets up the smallest state preconditions, runs the op inside a
fresh MigrationContext, and asserts on Jira HTTP calls plus state mutations.
The runner is exercised by test_m2_migrations.py; tests here focus on the
op-level alias resolution and dialect contract.
"""

from collections.abc import Awaitable, Callable

import httpx
import pytest
import respx

from pensum import PATAuth, StateFile, create_engine, op
from pensum.engine import Engine
from pensum.exceptions import ConfigurationError
from pensum.migrations.context import MigrationContext, reset_context, set_context
from pensum.state.file import (
    CustomFieldMapping,
    ProjectMapping,
    ScreenMapping,
    SimpleMapping,
)

BASE = "https://jira.example.com"
DC_ROOT = f"{BASE}/rest/api/2"
CLOUD_ROOT = f"{BASE}/rest/api/3"


def _dc_engine() -> Engine:
    return create_engine(f"jira_dc+{BASE}", auth=PATAuth("tok"))


def _cloud_engine() -> Engine:
    return create_engine(f"jira_cloud+{BASE}", auth=PATAuth("tok"))


async def _run_in_ctx(
    engine: Engine, state: StateFile, body: Callable[[], Awaitable[None]],
) -> None:
    ctx = MigrationContext(engine=engine, state=state, direction="upgrade")
    token = set_context(ctx)
    try:
        await body()
    finally:
        reset_context(token)


# ── Screens ──────────────────────────────────────────────────────────
@pytest.mark.asyncio
@respx.mock
async def test_create_screen_records_id():
    respx.post(f"{DC_ROOT}/screens", json__eq={
        "name": "Bug Screen", "description": "for bugs",
    }).mock(return_value=httpx.Response(201, json={"id": "scr-1"}))
    state = StateFile(env="dev", jira_url=BASE)
    engine = _dc_engine()
    try:
        await _run_in_ctx(engine, state, lambda: op.create_screen(
            alias="bug_screen", name="Bug Screen", description="for bugs",
        ))
    finally:
        await engine.close()
    assert state.screens["bug_screen"].id == "scr-1"
    assert state.screens["bug_screen"].tab_ids == {}


@pytest.mark.asyncio
@respx.mock
async def test_delete_screen_removes_mapping():
    respx.delete(f"{DC_ROOT}/screens/scr-1").mock(return_value=httpx.Response(204))
    state = StateFile(env="dev", jira_url=BASE)
    state.screens["bug_screen"] = ScreenMapping(id="scr-1")
    engine = _dc_engine()
    try:
        await _run_in_ctx(engine, state, lambda: op.delete_screen(alias="bug_screen"))
    finally:
        await engine.close()
    assert "bug_screen" not in state.screens


@pytest.mark.asyncio
@respx.mock
async def test_add_screen_tab_records_tab_id():
    respx.post(f"{DC_ROOT}/screens/scr-1/tabs", json__eq={"name": "Fields"}).mock(
        return_value=httpx.Response(201, json={"id": "tab-7"})
    )
    state = StateFile(env="dev", jira_url=BASE)
    state.screens["bug_screen"] = ScreenMapping(id="scr-1")
    engine = _dc_engine()
    try:
        await _run_in_ctx(engine, state, lambda: op.add_screen_tab(
            screen_alias="bug_screen", tab_name="Fields",
        ))
    finally:
        await engine.close()
    assert state.screens["bug_screen"].tab_ids == {"Fields": "tab-7"}


@pytest.mark.asyncio
async def test_add_screen_tab_is_idempotent_for_existing_tab_name():
    """M4 idempotency: adding a tab that's already in state returns the
    existing tab id without hitting Jira."""
    state = StateFile(env="dev", jira_url=BASE)
    state.screens["bug_screen"] = ScreenMapping(id="scr-1", tab_ids={"Fields": "tab-7"})
    engine = _dc_engine()
    captured: list[str] = []

    async def _call():
        result = await op.add_screen_tab(
            screen_alias="bug_screen", tab_name="Fields",
        )
        captured.append(result)

    try:
        await _run_in_ctx(engine, state, _call)
    finally:
        await engine.close()
    assert captured == ["tab-7"]
    # State unchanged
    assert state.screens["bug_screen"].tab_ids == {"Fields": "tab-7"}


@pytest.mark.asyncio
@respx.mock
async def test_add_screen_tab_field_resolves_field_alias():
    respx.post(
        f"{DC_ROOT}/screens/scr-1/tabs/tab-7/fields",
        json__eq={"fieldId": "customfield_10042"},
    ).mock(return_value=httpx.Response(204))
    state = StateFile(env="dev", jira_url=BASE)
    state.screens["bug_screen"] = ScreenMapping(id="scr-1", tab_ids={"Fields": "tab-7"})
    state.custom_fields["bug_severity"] = CustomFieldMapping(id="customfield_10042")
    engine = _dc_engine()
    try:
        await _run_in_ctx(engine, state, lambda: op.add_screen_tab_field(
            screen_alias="bug_screen", tab_name="Fields", field_alias="bug_severity",
        ))
    finally:
        await engine.close()


@pytest.mark.asyncio
async def test_add_screen_tab_field_rejects_unknown_tab():
    state = StateFile(env="dev", jira_url=BASE)
    state.screens["bug_screen"] = ScreenMapping(id="scr-1")
    state.custom_fields["bug_severity"] = CustomFieldMapping(id="customfield_10042")
    engine = _dc_engine()
    try:
        with pytest.raises(ConfigurationError) as e:
            await _run_in_ctx(engine, state, lambda: op.add_screen_tab_field(
                screen_alias="bug_screen", tab_name="Missing",
                field_alias="bug_severity",
            ))
        assert "no tab named" in str(e.value)
    finally:
        await engine.close()


# ── Screen schemes ───────────────────────────────────────────────────
@pytest.mark.asyncio
@respx.mock
async def test_create_screen_scheme_resolves_screen_aliases():
    respx.post(
        f"{DC_ROOT}/screenscheme",
        json__eq={
            "name": "Bug SS", "description": "",
            "screens": {"default": "scr-1", "create": "scr-2"},
        },
    ).mock(return_value=httpx.Response(201, json={"id": "ss-1"}))
    state = StateFile(env="dev", jira_url=BASE)
    state.screens["bug_screen"] = ScreenMapping(id="scr-1")
    state.screens["bug_create_screen"] = ScreenMapping(id="scr-2")
    engine = _dc_engine()
    try:
        await _run_in_ctx(engine, state, lambda: op.create_screen_scheme(
            alias="bug_ss",
            name="Bug SS",
            screens={"default": "bug_screen", "create": "bug_create_screen"},
        ))
    finally:
        await engine.close()
    assert state.screen_schemes["bug_ss"].id == "ss-1"


@pytest.mark.asyncio
async def test_create_screen_scheme_requires_default():
    state = StateFile(env="dev", jira_url=BASE)
    state.screens["bug_screen"] = ScreenMapping(id="scr-1")
    engine = _dc_engine()
    try:
        with pytest.raises(ConfigurationError) as e:
            await _run_in_ctx(engine, state, lambda: op.create_screen_scheme(
                alias="bug_ss", name="Bug SS", screens={"create": "bug_screen"},
            ))
        assert "'default'" in str(e.value)
    finally:
        await engine.close()


@pytest.mark.asyncio
@respx.mock
async def test_delete_screen_scheme():
    respx.delete(f"{DC_ROOT}/screenscheme/ss-1").mock(return_value=httpx.Response(204))
    state = StateFile(env="dev", jira_url=BASE)
    state.screen_schemes["bug_ss"] = SimpleMapping(id="ss-1")
    engine = _dc_engine()
    try:
        await _run_in_ctx(engine, state, lambda: op.delete_screen_scheme(alias="bug_ss"))
    finally:
        await engine.close()
    assert "bug_ss" not in state.screen_schemes


# ── Issue-type screen schemes ────────────────────────────────────────
@pytest.mark.asyncio
@respx.mock
async def test_create_issuetype_screen_scheme_resolves_default_and_typed_mappings():
    """Both 'default' and a typed issuetype alias resolve correctly."""
    respx.post(
        f"{DC_ROOT}/issuetypescreenscheme",
        json__eq={
            "name": "Bug ITSS",
            "description": "",
            "issueTypeMappings": [
                {"issueTypeId": "default", "screenSchemeId": "ss-1"},
                {"issueTypeId": "10010", "screenSchemeId": "ss-2"},
            ],
        },
    ).mock(return_value=httpx.Response(201, json={"id": "itss-1"}))
    state = StateFile(env="dev", jira_url=BASE)
    state.screen_schemes["default_ss"] = SimpleMapping(id="ss-1")
    state.screen_schemes["bug_ss"] = SimpleMapping(id="ss-2")
    state.issuetypes["bug"] = SimpleMapping(id="10010")
    engine = _dc_engine()
    try:
        await _run_in_ctx(engine, state, lambda: op.create_issuetype_screen_scheme(
            alias="bug_itss",
            name="Bug ITSS",
            mappings={"default": "default_ss", "bug": "bug_ss"},
        ))
    finally:
        await engine.close()
    assert state.issuetype_screen_schemes["bug_itss"].id == "itss-1"


@pytest.mark.asyncio
async def test_create_issuetype_screen_scheme_requires_default():
    state = StateFile(env="dev", jira_url=BASE)
    state.screen_schemes["bug_ss"] = SimpleMapping(id="ss-1")
    engine = _dc_engine()
    try:
        with pytest.raises(ConfigurationError):
            await _run_in_ctx(engine, state, lambda: op.create_issuetype_screen_scheme(
                alias="x", name="x", mappings={"bug": "bug_ss"},
            ))
    finally:
        await engine.close()


@pytest.mark.asyncio
@respx.mock
async def test_delete_issuetype_screen_scheme():
    respx.delete(f"{DC_ROOT}/issuetypescreenscheme/itss-1").mock(
        return_value=httpx.Response(204)
    )
    state = StateFile(env="dev", jira_url=BASE)
    state.issuetype_screen_schemes["bug_itss"] = SimpleMapping(id="itss-1")
    engine = _dc_engine()
    try:
        await _run_in_ctx(engine, state, lambda: op.delete_issuetype_screen_scheme(
            alias="bug_itss",
        ))
    finally:
        await engine.close()
    assert "bug_itss" not in state.issuetype_screen_schemes


# ── Field configurations ─────────────────────────────────────────────
@pytest.mark.asyncio
@respx.mock
async def test_create_field_configuration():
    respx.post(f"{DC_ROOT}/fieldconfiguration", json__eq={
        "name": "Bug FC", "description": "",
    }).mock(return_value=httpx.Response(201, json={"id": "fc-1"}))
    state = StateFile(env="dev", jira_url=BASE)
    engine = _dc_engine()
    try:
        await _run_in_ctx(engine, state, lambda: op.create_field_configuration(
            alias="bug_fc", name="Bug FC",
        ))
    finally:
        await engine.close()
    assert state.field_configurations["bug_fc"].id == "fc-1"


@pytest.mark.asyncio
@respx.mock
async def test_set_field_configuration_item_resolves_aliases():
    respx.put(
        f"{DC_ROOT}/fieldconfiguration/fc-1/fields",
        json__eq={"fieldConfigurationItems": [{
            "id": "customfield_10042",
            "isRequired": True,
            "isHidden": False,
            "description": "Required for triage",
        }]},
    ).mock(return_value=httpx.Response(204))
    state = StateFile(env="dev", jira_url=BASE)
    state.field_configurations["bug_fc"] = SimpleMapping(id="fc-1")
    state.custom_fields["bug_severity"] = CustomFieldMapping(id="customfield_10042")
    engine = _dc_engine()
    try:
        await _run_in_ctx(engine, state, lambda: op.set_field_configuration_item(
            fc_alias="bug_fc", field_alias="bug_severity",
            required=True, description="Required for triage",
        ))
    finally:
        await engine.close()


@pytest.mark.asyncio
@respx.mock
async def test_delete_field_configuration():
    respx.delete(f"{DC_ROOT}/fieldconfiguration/fc-1").mock(
        return_value=httpx.Response(204)
    )
    state = StateFile(env="dev", jira_url=BASE)
    state.field_configurations["bug_fc"] = SimpleMapping(id="fc-1")
    engine = _dc_engine()
    try:
        await _run_in_ctx(engine, state, lambda: op.delete_field_configuration(
            alias="bug_fc",
        ))
    finally:
        await engine.close()
    assert "bug_fc" not in state.field_configurations


# ── Field configuration schemes ──────────────────────────────────────
@pytest.mark.asyncio
@respx.mock
async def test_create_field_configuration_scheme_creates_and_sets_mappings():
    respx.post(f"{DC_ROOT}/fieldconfigurationscheme", json__eq={
        "name": "Bug FCS", "description": "",
    }).mock(return_value=httpx.Response(201, json={"id": "fcs-1"}))
    respx.put(
        f"{DC_ROOT}/fieldconfigurationscheme/fcs-1/mapping",
        json__eq={"mappings": [
            {"issueTypeId": "default", "fieldConfigurationId": "fc-1"},
        ]},
    ).mock(return_value=httpx.Response(204))
    state = StateFile(env="dev", jira_url=BASE)
    state.field_configurations["default_fc"] = SimpleMapping(id="fc-1")
    engine = _dc_engine()
    try:
        await _run_in_ctx(engine, state, lambda: op.create_field_configuration_scheme(
            alias="bug_fcs", name="Bug FCS",
            mappings={"default": "default_fc"},
        ))
    finally:
        await engine.close()
    assert state.field_configuration_schemes["bug_fcs"].id == "fcs-1"


@pytest.mark.asyncio
@respx.mock
async def test_delete_field_configuration_scheme():
    respx.delete(f"{DC_ROOT}/fieldconfigurationscheme/fcs-1").mock(
        return_value=httpx.Response(204)
    )
    state = StateFile(env="dev", jira_url=BASE)
    state.field_configuration_schemes["bug_fcs"] = SimpleMapping(id="fcs-1")
    engine = _dc_engine()
    try:
        await _run_in_ctx(engine, state, lambda: op.delete_field_configuration_scheme(
            alias="bug_fcs",
        ))
    finally:
        await engine.close()
    assert "bug_fcs" not in state.field_configuration_schemes


# ── Issuetypes ───────────────────────────────────────────────────────
@pytest.mark.asyncio
@respx.mock
async def test_create_issuetype():
    respx.post(f"{DC_ROOT}/issuetype", json__eq={
        "name": "Bug", "description": "a bug", "type": "standard",
    }).mock(return_value=httpx.Response(201, json={"id": "10010"}))
    state = StateFile(env="dev", jira_url=BASE)
    engine = _dc_engine()
    try:
        await _run_in_ctx(engine, state, lambda: op.create_issuetype(
            alias="bug", name="Bug", description="a bug",
        ))
    finally:
        await engine.close()
    assert state.issuetypes["bug"].id == "10010"


@pytest.mark.asyncio
@respx.mock
async def test_create_issuetype_subtask_sends_subtask_type():
    respx.post(f"{DC_ROOT}/issuetype", json__eq={
        "name": "Sub-bug", "description": "", "type": "subtask",
    }).mock(return_value=httpx.Response(201, json={"id": "10011"}))
    state = StateFile(env="dev", jira_url=BASE)
    engine = _dc_engine()
    try:
        await _run_in_ctx(engine, state, lambda: op.create_issuetype(
            alias="sub_bug", name="Sub-bug", subtask=True,
        ))
    finally:
        await engine.close()


@pytest.mark.asyncio
@respx.mock
async def test_delete_issuetype():
    respx.delete(f"{DC_ROOT}/issuetype/10010").mock(return_value=httpx.Response(204))
    state = StateFile(env="dev", jira_url=BASE)
    state.issuetypes["bug"] = SimpleMapping(id="10010")
    engine = _dc_engine()
    try:
        await _run_in_ctx(engine, state, lambda: op.delete_issuetype(alias="bug"))
    finally:
        await engine.close()
    assert "bug" not in state.issuetypes


# ── Projects ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
@respx.mock
async def test_create_project_dc_uses_lead_field():
    respx.post(f"{DC_ROOT}/project", json__eq={
        "key": "BUG", "name": "Bug Tracker",
        "projectTypeKey": "software", "lead": "jdoe",
        "description": "",
    }).mock(return_value=httpx.Response(201, json={"id": "p-1"}))
    state = StateFile(env="dev", jira_url=BASE)
    engine = _dc_engine()
    try:
        await _run_in_ctx(engine, state, lambda: op.create_project(
            alias="bug_tracker", key="BUG", name="Bug Tracker",
            project_type_key="software", lead="jdoe",
        ))
    finally:
        await engine.close()
    assert state.projects["bug_tracker"].id == "p-1"


@pytest.mark.asyncio
@respx.mock
async def test_create_project_cloud_uses_leadAccountId():
    respx.get(f"{CLOUD_ROOT}/serverInfo").mock(
        return_value=httpx.Response(200, json={
            "baseUrl": BASE, "version": "1001", "deploymentType": "Cloud",
        })
    )
    respx.post(f"{CLOUD_ROOT}/project", json__eq={
        "key": "BUG", "name": "Bug Tracker",
        "projectTypeKey": "software", "leadAccountId": "acc-123",
        "description": "",
    }).mock(return_value=httpx.Response(201, json={"id": "p-1"}))
    state = StateFile(env="dev", jira_url=BASE)
    engine = _cloud_engine()
    try:
        await _run_in_ctx(engine, state, lambda: op.create_project(
            alias="bug_tracker", key="BUG", name="Bug Tracker",
            project_type_key="software", lead="acc-123",
        ))
    finally:
        await engine.close()


@pytest.mark.asyncio
@respx.mock
async def test_delete_project_dc_uses_key():
    respx.delete(f"{DC_ROOT}/project/BUG").mock(return_value=httpx.Response(204))
    state = StateFile(env="dev", jira_url=BASE)
    state.projects["bug_tracker"] = ProjectMapping(id="p-1", key="BUG")
    engine = _dc_engine()
    try:
        await _run_in_ctx(engine, state, lambda: op.delete_project(
            alias="bug_tracker", key="BUG",
        ))
    finally:
        await engine.close()
    assert "bug_tracker" not in state.projects


@pytest.mark.asyncio
@respx.mock
async def test_set_project_issuetype_screen_scheme():
    respx.put(
        f"{DC_ROOT}/issuetypescreenscheme/project",
        json__eq={"issueTypeScreenSchemeId": "itss-1", "projectId": "p-1"},
    ).mock(return_value=httpx.Response(204))
    state = StateFile(env="dev", jira_url=BASE)
    state.projects["bug_tracker"] = ProjectMapping(id="p-1", key="BUG")
    state.issuetype_screen_schemes["bug_itss"] = SimpleMapping(id="itss-1")
    engine = _dc_engine()
    try:
        await _run_in_ctx(
            engine, state, lambda: op.set_project_issuetype_screen_scheme(
                project_alias="bug_tracker", scheme_alias="bug_itss",
            ),
        )
    finally:
        await engine.close()


@pytest.mark.asyncio
@respx.mock
async def test_set_project_field_configuration_scheme():
    respx.put(
        f"{DC_ROOT}/fieldconfigurationscheme/project",
        json__eq={"fieldConfigurationSchemeId": "fcs-1", "projectId": "p-1"},
    ).mock(return_value=httpx.Response(204))
    state = StateFile(env="dev", jira_url=BASE)
    state.projects["bug_tracker"] = ProjectMapping(id="p-1", key="BUG")
    state.field_configuration_schemes["bug_fcs"] = SimpleMapping(id="fcs-1")
    engine = _dc_engine()
    try:
        await _run_in_ctx(
            engine, state, lambda: op.set_project_field_configuration_scheme(
                project_alias="bug_tracker", scheme_alias="bug_fcs",
            ),
        )
    finally:
        await engine.close()


# ── Idempotency: delete-when-absent is a no-op ───────────────────────
@pytest.mark.asyncio
async def test_delete_missing_alias_is_noop():
    """M4 idempotency: deleting an alias not in state is a no-op (not an error).
    This makes downgrade-of-partial safe."""
    state = StateFile(env="dev", jira_url=BASE)
    engine = _dc_engine()
    try:
        # Should not raise, should not hit Jira.
        await _run_in_ctx(engine, state, lambda: op.delete_screen(alias="ghost"))
    finally:
        await engine.close()
    assert "ghost" not in state.screens
