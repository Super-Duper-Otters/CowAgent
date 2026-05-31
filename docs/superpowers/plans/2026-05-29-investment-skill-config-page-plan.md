# Investment Skill Config Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an investment-only Skill system that supports Web-managed keyword triggers, Web upload/update of investment Skill packages, and clear separation from CowAgent general Skills.

**Architecture:** Reuse the CowAgent Skill package convention (`SKILL.md` with frontmatter) only as a file/package format. Do not use `agent.skills.SkillManager`, `/api/skills`, or `skills_config.json` for investment routing. Add an `InvestmentSkillLoader` that scans built-in investment Skill packages plus uploaded investment Skill packages, reads an `investment:` frontmatter block, applies Web-configured overrides from `investment_configs`, and feeds deterministic keyword routing in `business/investment/router.py`.

**Tech Stack:** Python, existing `agent.skills.frontmatter` parser, web.py handlers in `channel/web/web_channel.py`, frontend JavaScript in `channel/web/static/js/console.js`, existing investment SQLAlchemy config table, pytest.

---

## Boundaries

- Investment Skills are separate from original CowAgent Skills.
- Original CowAgent Skill files and APIs stay untouched unless hidden from the investment-focused UI.
- Investment Skill metadata is read from investment Skill packages, not from `~/cow/skills/skills_config.json`.
- Web keyword settings override package defaults and are stored in `investment_configs`.
- First implementation supports simple matching only: `exact` and `suffix`.
- First implementation supports three handler types:
  - `builtin_technical_analysis`
  - `daily_content`
  - `script`
- `signal-card-renderer` remains a versioned internal component and is not keyword-routable by default.

## Investment Skill Package Format

Each investment Skill package is a directory or zip containing `SKILL.md`. It follows the familiar CowAgent Skill convention but adds an investment-only frontmatter block:

```yaml
---
name: macro-analysis
description: 宏观分析投研 Skill
investment:
  label: 宏观分析
  enabled: true
  routable: true
  service_type: macro_analysis
  match_type: exact
  triggers:
    - 宏观
    - 宏观分析
  handler_type: script
  entry: scripts/macro_analysis.py
  output_mode: mixed
---
```

Built-in migrated examples:

```yaml
---
name: technical-analysis
description: 根据股票代码或名称生成技术分析报告、图表和信号卡片。
investment:
  label: 技术分析 Skill
  enabled: true
  routable: true
  service_type: technical_analysis
  match_type: suffix
  triggers:
    - 技术分析
  handler_type: builtin_technical_analysis
  entry: scripts/analyze_universal.py
  output_mode: images
---
```

```yaml
---
name: rate
description: 返回当前生效的利率投研内容图片。
investment:
  label: 利率 Skill
  enabled: true
  routable: true
  service_type: rate
  match_type: exact
  triggers:
    - 利率
  handler_type: daily_content
  output_mode: images
---
```

## File Map

- Create: `business/investment/skill_registry.py`
  - Defines `InvestmentSkillDefinition`, loads package metadata, applies config overrides, and matches keywords.
- Create: `business/investment/skill_runner.py`
  - Runs matched investment Skills through existing built-in handlers or a simple script JSON protocol.
- Modify: `business/investment/skill_versions.py`
  - Use definitions from `skill_registry.py`; keep upload/update/version switching investment-only.
- Modify: `business/investment/router.py`
  - Route through `skill_registry.match_investment_skill()` and execute through `skill_runner.run_investment_skill()`.
- Modify: `channel/web/web_channel.py`
  - Add settings and package upload APIs for investment Skills.
- Modify: `channel/web/static/js/console.js`
  - Add a dedicated `投资Skill` page and remove embedded Skill config from system config.
- Modify: `tests/test_investment_business.py`
  - Cover package loading, keyword override, package upload, old Skill update, and route execution.
- Modify: `tests/test_investment_web_ui.py`
  - Cover frontend separation and trigger editing UI.

---

## Task 1: Add Investment Skill Package Loader

**Files:**
- Create: `business/investment/skill_registry.py`
- Test: `tests/test_investment_business.py`

- [ ] **Step 1: Write failing tests**

Add:

```python
def test_investment_skill_loader_reads_builtin_packages_and_excludes_cowagent_skills(investment_env):
    from business.investment.skill_registry import list_investment_skills

    keys = {item["skill_key"] for item in list_investment_skills()}

    assert {"technical-analysis", "rate", "convertible-bond", "signal-card-renderer"} <= keys
    assert "image-generation" not in keys
    assert "knowledge-wiki" not in keys


def test_investment_skill_loader_applies_web_trigger_override(investment_env):
    from business.investment.config_service import save_config
    from business.investment.constants import ServiceType
    from business.investment.skill_registry import match_investment_skill

    save_config("skill.rate.triggers", ["今日利率"], operator_role="admin", operator="pytest")

    assert match_investment_skill("利率") is None
    matched = match_investment_skill("今日利率")
    assert matched is not None
    assert matched.skill_key == "rate"
    assert matched.service_type == ServiceType.RATE


def test_investment_skill_loader_extracts_suffix_target(investment_env):
    from business.investment.config_service import save_config
    from business.investment.constants import ServiceType
    from business.investment.skill_registry import match_investment_skill

    save_config("skill.technical-analysis.triggers", ["走势分析"], operator_role="admin", operator="pytest")

    matched = match_investment_skill("300502.SZ 走势分析")
    assert matched is not None
    assert matched.skill_key == "technical-analysis"
    assert matched.service_type == ServiceType.TECHNICAL_ANALYSIS
    assert matched.target_text == "300502.SZ"
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```powershell
py -m pytest tests/test_investment_business.py -q -k "investment_skill_loader"
```

Expected: failure because `business.investment.skill_registry` does not exist.

- [ ] **Step 3: Implement built-in definitions and loader shape**

Create `business/investment/skill_registry.py`. The first implementation may use in-code built-in defaults that mirror package metadata, but it must expose the same fields that `SKILL.md` loading will produce:

```python
# encoding:utf-8
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config_service import get_config
from .constants import ServiceType, normalize_service
from .render_service import DEFAULT_RENDERER_PATH


@dataclass(frozen=True)
class InvestmentSkillDefinition:
    skill_key: str
    label: str
    description: str
    service_type: ServiceType
    match_type: str
    default_triggers: tuple[str, ...]
    handler_type: str
    entry: str = ""
    output_mode: str = "images"
    routable: bool = True
    base_dir: str = ""
    config_key: str = ""
    default_script_path: str = ""
    script_name: str = ""
    storage_name: str = ""
    copy_assets_from: str = ""

    @property
    def enabled_config_key(self) -> str:
        return f"skill.{self.skill_key}.enabled"

    @property
    def triggers_config_key(self) -> str:
        return f"skill.{self.skill_key}.triggers"

    def as_dict(self) -> dict:
        return {
            "skill_key": self.skill_key,
            "label": self.label,
            "description": self.description,
            "service_type": str(self.service_type),
            "match_type": self.match_type,
            "triggers": list(resolve_triggers(self)),
            "enabled": is_skill_enabled(self),
            "handler_type": self.handler_type,
            "entry": self.entry,
            "output_mode": self.output_mode,
            "routable": self.routable,
            "config_key": self.config_key,
            "default_script_path": self.default_script_path,
            "script_name": self.script_name,
            "storage_name": self.storage_name,
            "base_dir": self.base_dir,
        }


@dataclass(frozen=True)
class InvestmentSkillMatch:
    skill_key: str
    service_type: ServiceType
    raw_input: str
    target_text: str = ""


BUILTIN_DEFINITIONS: tuple[InvestmentSkillDefinition, ...] = (
    InvestmentSkillDefinition(
        skill_key="technical-analysis",
        label="技术分析 Skill",
        description="根据股票代码或名称生成技术分析报告、图表和信号卡片。",
        service_type=ServiceType.TECHNICAL_ANALYSIS,
        match_type="suffix",
        default_triggers=("技术分析",),
        handler_type="builtin_technical_analysis",
        entry="skills/技术分析/scripts/analyze_universal.py",
        config_key="technical_analysis.skill_path",
        default_script_path="skills/技术分析/scripts/analyze_universal.py",
        script_name="analyze_universal.py",
        storage_name="technical-analysis",
    ),
    InvestmentSkillDefinition(
        skill_key="rate",
        label="利率 Skill",
        description="返回当前生效的利率投研内容图片。",
        service_type=ServiceType.RATE,
        match_type="exact",
        default_triggers=("利率",),
        handler_type="daily_content",
        storage_name="rate",
    ),
    InvestmentSkillDefinition(
        skill_key="convertible-bond",
        label="转债 Skill",
        description="返回当前生效的可转债投研内容图片。",
        service_type=ServiceType.CONVERTIBLE_BOND,
        match_type="exact",
        default_triggers=("转债",),
        handler_type="daily_content",
        storage_name="convertible-bond",
    ),
    InvestmentSkillDefinition(
        skill_key="signal-card-renderer",
        label="图片生成 Skill",
        description="把标准投研文本渲染为信号卡片图片，作为投资业务内部组件使用。",
        service_type=ServiceType.UNMATCHED,
        match_type="exact",
        default_triggers=(),
        handler_type="renderer",
        entry=DEFAULT_RENDERER_PATH,
        output_mode="image",
        routable=False,
        config_key="render.renderer_path",
        default_script_path=DEFAULT_RENDERER_PATH,
        script_name="render_card.py",
        storage_name="signal-card-renderer",
        copy_assets_from="skills/signal-card-renderer/assets",
    ),
)


def _uploaded_skill_root() -> Path:
    from .storage import get_storage_dirs

    return get_storage_dirs()["root"] / "investment-skills"


def list_definitions() -> list[InvestmentSkillDefinition]:
    return list(BUILTIN_DEFINITIONS)


def get_skill_definition(skill_key: str) -> InvestmentSkillDefinition:
    for definition in list_definitions():
        if definition.skill_key == skill_key:
            return definition
    raise ValueError(f"unsupported investment skill: {skill_key}")


def list_investment_skills() -> list[dict]:
    return [definition.as_dict() for definition in list_definitions()]


def is_skill_enabled(definition: InvestmentSkillDefinition) -> bool:
    return bool(get_config(definition.enabled_config_key, True))


def resolve_triggers(definition: InvestmentSkillDefinition) -> tuple[str, ...]:
    raw = get_config(definition.triggers_config_key, list(definition.default_triggers))
    if isinstance(raw, str):
        values = [item.strip() for item in raw.replace("，", ",").split(",")]
    elif isinstance(raw, list):
        values = [str(item).strip() for item in raw]
    else:
        values = []
    return tuple(item for item in values if item)


def match_investment_skill(raw_input: str) -> InvestmentSkillMatch | None:
    text = (raw_input or "").strip()
    if not text:
        return None
    for definition in list_definitions():
        if not definition.routable or not is_skill_enabled(definition):
            continue
        triggers = resolve_triggers(definition)
        if definition.match_type == "exact" and text in triggers:
            return InvestmentSkillMatch(definition.skill_key, definition.service_type, raw_input)
        if definition.match_type == "suffix":
            for trigger in triggers:
                if text.endswith(trigger):
                    target = text[: -len(trigger)].strip()
                    if target:
                        return InvestmentSkillMatch(definition.skill_key, definition.service_type, raw_input, target)
    return None
```

- [ ] **Step 4: Run tests**

Run:

```powershell
py -m pytest tests/test_investment_business.py -q -k "investment_skill_loader"
```

Expected: tests pass.

---

## Task 2: Load Uploaded Investment Skill Packages

**Files:**
- Modify: `business/investment/skill_registry.py`
- Modify: `business/investment/skill_versions.py`
- Test: `tests/test_investment_business.py`

- [ ] **Step 1: Write failing uploaded package test**

Add:

```python
def test_uploaded_investment_skill_package_appears_in_registry(investment_env, tmp_path):
    from business.investment.skill_versions import save_package_upload
    from business.investment.skill_registry import list_investment_skills, match_investment_skill
    from business.investment.constants import ServiceType
    from zipfile import ZipFile

    package = tmp_path / "macro.zip"
    skill_md = """---
name: macro-analysis
description: 宏观分析投研 Skill
investment:
  label: 宏观分析
  enabled: true
  routable: true
  service_type: macro_analysis
  match_type: exact
  triggers:
    - 宏观
  handler_type: script
  entry: scripts/macro_analysis.py
  output_mode: text
---
# Macro Analysis
"""
    script = "import json, sys\nprint(json.dumps({'success': True, 'reply_text': 'macro ok', 'output_files': []}, ensure_ascii=False))\n"
    with ZipFile(package, "w") as archive:
        archive.writestr("SKILL.md", skill_md)
        archive.writestr("scripts/macro_analysis.py", script)

    save_package_upload("macro.zip", package.read_bytes(), operator="pytest")

    keys = {item["skill_key"] for item in list_investment_skills()}
    assert "macro-analysis" in keys
    matched = match_investment_skill("宏观")
    assert matched is not None
    assert matched.skill_key == "macro-analysis"
    assert matched.service_type == ServiceType.UNMATCHED
```

`macro_analysis` is not yet in `ServiceType`; for first implementation unknown custom services may normalize to `ServiceType.UNMATCHED`. The runner still receives `skill_key` and can execute script Skills later.

- [ ] **Step 2: Run test and confirm failure**

Run:

```powershell
py -m pytest tests/test_investment_business.py -q -k "uploaded_investment_skill_package"
```

Expected: failure because upload and frontmatter loading are not implemented.

- [ ] **Step 3: Implement frontmatter package loading**

In `business/investment/skill_registry.py`, import and use existing parser:

```python
from agent.skills.frontmatter import parse_frontmatter
```

Add:

```python
def _read_uploaded_definition(skill_dir: Path) -> InvestmentSkillDefinition | None:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return None
    content = skill_md.read_text(encoding="utf-8")
    frontmatter = parse_frontmatter(content)
    investment = frontmatter.get("investment") or {}
    if not isinstance(investment, dict):
        return None
    skill_key = str(frontmatter.get("name") or skill_dir.name).strip()
    if not skill_key:
        return None
    triggers = investment.get("triggers") or []
    if isinstance(triggers, str):
        triggers = [triggers]
    service_type = normalize_service(str(investment.get("service_type") or "unmatched"))
    entry = str(investment.get("entry") or "").strip()
    return InvestmentSkillDefinition(
        skill_key=skill_key,
        label=str(investment.get("label") or skill_key),
        description=str(frontmatter.get("description") or ""),
        service_type=service_type,
        match_type=str(investment.get("match_type") or "exact"),
        default_triggers=tuple(str(item).strip() for item in triggers if str(item).strip()),
        handler_type=str(investment.get("handler_type") or "script"),
        entry=entry,
        output_mode=str(investment.get("output_mode") or "mixed"),
        routable=bool(investment.get("routable", True)),
        base_dir=str(skill_dir),
        config_key=str(investment.get("config_key") or ""),
        default_script_path=str((skill_dir / entry).resolve()) if entry else "",
        script_name=Path(entry).name if entry else "",
        storage_name=skill_key,
    )
```

Update `list_definitions()` to append uploaded packages and let uploaded packages override same-key built-ins:

```python
def list_definitions() -> list[InvestmentSkillDefinition]:
    definitions = {item.skill_key: item for item in BUILTIN_DEFINITIONS}
    root = _uploaded_skill_root()
    if root.is_dir():
        for skill_dir in sorted(item for item in root.iterdir() if item.is_dir()):
            definition = _read_uploaded_definition(skill_dir)
            if definition is not None:
                definitions[definition.skill_key] = definition
    return list(definitions.values())
```

- [ ] **Step 4: Implement package upload helper**

In `business/investment/skill_versions.py`, add a simple package upload function for new investment Skills:

```python
def save_package_upload(filename: str, content: bytes, *, operator: str = "web-console") -> dict:
    from zipfile import ZipFile
    import shutil
    import uuid
    from .skill_registry import _uploaded_skill_root

    safe_name = Path(filename or "").name
    if Path(safe_name).suffix.lower() != ".zip":
        raise ValueError("investment skill package upload only accepts .zip files")
    if not content:
        raise ValueError("uploaded skill package is empty")

    root = _uploaded_skill_root()
    tmp_dir = root / f".upload-{uuid.uuid4().hex}"
    tmp_dir.mkdir(parents=True, exist_ok=False)
    try:
        archive_path = tmp_dir / safe_name
        archive_path.write_bytes(content)
        with ZipFile(archive_path) as archive:
            for member in archive.infolist():
                if member.is_dir():
                    continue
                target = tmp_dir / _safe_member_path(member.filename)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(member))
        if not (tmp_dir / "SKILL.md").is_file():
            raise ValueError("investment skill package must contain SKILL.md at package root")
        from .skill_registry import _read_uploaded_definition

        definition = _read_uploaded_definition(tmp_dir)
        if definition is None:
            raise ValueError("SKILL.md must contain investment frontmatter")
        target_dir = root / definition.skill_key
        if target_dir.exists():
            shutil.rmtree(target_dir)
        tmp_dir.rename(target_dir)
        return {"skill_key": definition.skill_key, "storage_path": str(target_dir), "operator": operator}
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
```

- [ ] **Step 5: Run uploaded package tests**

Run:

```powershell
py -m pytest tests/test_investment_business.py -q -k "uploaded_investment_skill_package or investment_skill_loader"
```

Expected: tests pass.

---

## Task 3: Route and Run Investment Skills

**Files:**
- Create: `business/investment/skill_runner.py`
- Modify: `business/investment/router.py`
- Test: `tests/test_investment_business.py`

- [ ] **Step 1: Write failing route tests**

Add:

```python
def test_parse_route_uses_configured_investment_skill_triggers(investment_env):
    from business.investment.config_service import save_config
    from business.investment.constants import ServiceType
    from business.investment.router import parse_route

    save_config("skill.rate.triggers", ["今日利率"], operator_role="admin", operator="pytest")
    save_config("skill.technical-analysis.triggers", ["走势分析"], operator_role="admin", operator="pytest")

    assert parse_route("利率").matched is False
    assert parse_route("今日利率").service_type == ServiceType.RATE

    route = parse_route("300502.SZ 走势分析")
    assert route.matched is True
    assert route.service_type == ServiceType.TECHNICAL_ANALYSIS
    assert route.target_text == "300502.SZ"


def test_parse_route_ignores_disabled_investment_skill(investment_env):
    from business.investment.config_service import save_config
    from business.investment.router import parse_route

    save_config("skill.rate.enabled", False, operator_role="admin", operator="pytest")

    assert parse_route("利率").matched is False
```

- [ ] **Step 2: Replace hard-coded route matching**

In `business/investment/router.py`, change `parse_route()`:

```python
def parse_route(raw_input: str) -> RouteResult:
    from .skill_registry import match_investment_skill

    matched = match_investment_skill(raw_input)
    if matched is not None:
        return RouteResult(True, matched.service_type, raw_input, matched.target_text)
    return RouteResult(False, ServiceType.UNMATCHED, raw_input, error_code=ErrorCode.INPUT_ERROR)
```

- [ ] **Step 3: Create minimal script runner**

Create `business/investment/skill_runner.py`:

```python
# encoding:utf-8
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .constants import ErrorCode, ServiceType, user_message
from .daily_content import get_latest_effective_content
from .skill_registry import InvestmentSkillDefinition
from .technical_analysis import run_technical_analysis


@dataclass
class InvestmentSkillRunResult:
    success: bool
    reply_text: str = ""
    output_files: list[str] = field(default_factory=list)
    error_code: ErrorCode | None = None
    user_prompt: str = ""
    detail: str = ""


def _image_reply(paths: list[str]) -> str:
    return "\n".join(f"[图片: {path}]" for path in paths)


def _run_daily_content(definition: InvestmentSkillDefinition) -> InvestmentSkillRunResult:
    content = get_latest_effective_content(definition.service_type)
    if not content.success:
        code = content.error_code or ErrorCode.NO_CONTENT
        return InvestmentSkillRunResult(False, error_code=code, user_prompt=content.user_prompt, detail=content.detail)
    return InvestmentSkillRunResult(True, _image_reply([content.output_image]), [content.output_image])


def _run_script(definition: InvestmentSkillDefinition, openid: str, raw_input: str, target_text: str) -> InvestmentSkillRunResult:
    script = Path(definition.default_script_path or definition.entry)
    if not script.is_absolute():
        script = Path.cwd() / script
    payload = {
        "openid": openid,
        "raw_input": raw_input,
        "target_text": target_text,
        "skill_key": definition.skill_key,
    }
    completed = subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(completed.stdout or "{}")
    output_files = [str(item) for item in data.get("output_files", [])]
    return InvestmentSkillRunResult(
        bool(data.get("success")),
        str(data.get("reply_text") or _image_reply(output_files)),
        output_files,
        detail=str(data.get("detail") or ""),
    )


def run_investment_skill(definition: InvestmentSkillDefinition, openid: str, raw_input: str, target_text: str = "") -> InvestmentSkillRunResult:
    if definition.handler_type == "daily_content":
        return _run_daily_content(definition)
    if definition.handler_type == "builtin_technical_analysis":
        result = run_technical_analysis(openid, raw_input, target_text)
        if not result.success:
            code = result.error_code or ErrorCode.TECHNICAL_ANALYSIS_FAILED
            return InvestmentSkillRunResult(False, error_code=code, user_prompt=user_message(code), detail=result.detail)
        output_files = [result.signal_card_path, result.main_chart_path]
        return InvestmentSkillRunResult(True, _image_reply(output_files), output_files)
    if definition.handler_type == "script":
        return _run_script(definition, openid, raw_input, target_text)
    return InvestmentSkillRunResult(False, error_code=ErrorCode.INPUT_ERROR, user_prompt=user_message(ErrorCode.INPUT_ERROR), detail=f"unsupported handler_type: {definition.handler_type}")
```

- [ ] **Step 4: Keep existing detailed `handle_text_message()` logic for first pass**

Do not fully replace `handle_text_message()` in this task. Keep its existing special handling for rate, convertible bond, and technical analysis records. Only `parse_route()` changes now. Add a follow-up note in code comments if desired:

```python
# InvestmentSkillRunner is available for uploaded script Skills; built-in flows keep
# their existing record/cache behavior until they are migrated deliberately.
```

- [ ] **Step 5: Run routing tests**

Run:

```powershell
py -m pytest tests/test_investment_business.py -q -k "parse_route or investment_skill_loader"
```

Expected: tests pass.

---

## Task 4: Reuse Registry in Version and Package Management

**Files:**
- Modify: `business/investment/skill_versions.py`
- Test: `tests/test_investment_business.py`

- [ ] **Step 1: Update version listing test**

Add:

```python
def test_investment_skill_versions_include_loaded_skills(investment_env):
    from business.investment.skill_versions import list_all_skills

    payload = list_all_skills()
    by_key = {item["skill"]["skill_key"]: item for item in payload}

    assert "technical-analysis" in by_key
    assert "signal-card-renderer" in by_key
    assert "rate" in by_key
    assert "convertible-bond" in by_key
    assert by_key["technical-analysis"]["versions"]
    assert by_key["signal-card-renderer"]["versions"]
    assert by_key["rate"]["versions"] == []
    assert by_key["convertible-bond"]["versions"] == []
```

- [ ] **Step 2: Replace local registry usage**

In `business/investment/skill_versions.py`:

```python
from .skill_registry import InvestmentSkillDefinition, get_skill_definition, list_definitions
```

Set:

```python
def _definition(skill_key: str) -> InvestmentSkillDefinition:
    return get_skill_definition(skill_key)


def list_skill_definitions() -> list[dict]:
    return [definition.as_dict() for definition in list_definitions()]


def list_all_skills() -> list[dict]:
    items = []
    for definition in list_definitions():
        versions = []
        if definition.script_name and definition.config_key:
            versions = list_versions(definition.skill_key)
        items.append({"skill": definition.as_dict(), "versions": versions})
    return items
```

- [ ] **Step 3: Guard non-versioned Skills**

At the start of `save_upload()`, `list_versions()`, `activate_version()`, and `delete_version()`:

```python
if not definition.script_name or not definition.config_key:
    raise ValueError(f"{definition.label} does not support script version management")
```

- [ ] **Step 4: Run version tests**

Run:

```powershell
py -m pytest tests/test_investment_business.py -q -k "skill_versions or skill_upload or uploaded_investment_skill_package"
```

Expected: tests pass.

---

## Task 5: Add Investment Skill Settings and Package Upload APIs

**Files:**
- Modify: `channel/web/web_channel.py`
- Test: `tests/test_investment_business.py`

- [ ] **Step 1: Write failing settings API test**

Add:

```python
def test_investment_skill_settings_post_updates_triggers_and_enabled(investment_env, monkeypatch):
    import json
    import channel.web.web_channel as web_channel
    from business.investment.config_service import get_config
    from channel.web.web_channel import InvestmentSkillSettingsHandler

    monkeypatch.setattr(web_channel, "_require_investment_permission", lambda _permission: None)
    monkeypatch.setattr(web_channel, "_investment_json_body", lambda: {
        "enabled": False,
        "triggers": ["今日利率", "利率观察"],
        "operator": "pytest",
    })

    payload = json.loads(InvestmentSkillSettingsHandler().POST("rate"))

    assert payload["status"] == "success"
    assert get_config("skill.rate.enabled") is False
    assert get_config("skill.rate.triggers") == ["今日利率", "利率观察"]
```

- [ ] **Step 2: Register routes**

Add near investment Skill routes in `channel/web/web_channel.py`:

```python
'/api/investment/skills/(.*)/settings', 'InvestmentSkillSettingsHandler',
'/api/investment/skills/packages/upload', 'InvestmentSkillPackageUploadHandler',
```

- [ ] **Step 3: Implement settings handler**

Add:

```python
class InvestmentSkillSettingsHandler:
    def POST(self, skill_key):
        _require_investment_permission("skills.write")
        try:
            from business.investment.config_service import save_config
            from business.investment.skill_registry import get_skill_definition
            from business.investment.skill_versions import list_all_skills

            definition = get_skill_definition(skill_key)
            body = _investment_json_body()
            operator = body.get("operator", "web-console")

            if "enabled" in body:
                save_config(definition.enabled_config_key, bool(body.get("enabled")), operator_role="admin", operator=operator)

            if "triggers" in body:
                triggers = body.get("triggers") or []
                if isinstance(triggers, str):
                    triggers = [item.strip() for item in triggers.replace("，", ",").split(",")]
                triggers = [str(item).strip() for item in triggers if str(item).strip()]
                if definition.routable and not triggers:
                    return _investment_json_response({"status": "error", "message": "triggers cannot be empty"})
                save_config(definition.triggers_config_key, triggers, operator_role="admin", operator=operator)

            return _investment_json_response({"status": "success", "skills": list_all_skills()})
        except Exception as e:
            logger.error(f"[Investment] skill settings error: {e}")
            return _investment_json_response({"status": "error", "message": str(e)})
```

- [ ] **Step 4: Implement package upload handler**

Add:

```python
class InvestmentSkillPackageUploadHandler:
    def POST(self):
        _require_investment_permission("skills.write")
        try:
            from business.investment.skill_versions import list_all_skills, save_package_upload

            params = _raw_web_input()
            file_obj = params.get("file")
            if file_obj is None:
                return _investment_json_response({"status": "error", "message": "file required"})
            filename = getattr(file_obj, "filename", "") or getattr(file_obj, "name", "") or "investment-skill.zip"
            uploaded = save_package_upload(
                os.path.basename(filename),
                _read_uploaded_file_bytes(file_obj),
                operator=params.get("operator", "web-console"),
            )
            return _investment_json_response({"status": "success", "uploaded": uploaded, "skills": list_all_skills()})
        except Exception as e:
            logger.error(f"[Investment] skill package upload error: {e}")
            return _investment_json_response({"status": "error", "message": str(e)})
```

- [ ] **Step 5: Run API tests**

Run:

```powershell
py -m pytest tests/test_investment_business.py -q -k "skill_settings_post or uploaded_investment_skill_package or skill_versions"
```

Expected: tests pass.

---

## Task 6: Move Skill Config to a New Web Page

**Files:**
- Modify: `channel/web/static/js/console.js`
- Test: `tests/test_investment_web_ui.py`

- [ ] **Step 1: Write failing Web UI tests**

Add or update:

```python
def test_investment_skill_has_own_navigation_page():
    js = Path("channel/web/static/js/console.js").read_text(encoding="utf-8")

    assert "menu_invest_skills" in js
    assert "'invest-skills':" in js
    assert "renderInvestmentSkills()" in js
    assert "invest-skills-content" in js


def test_investment_config_no_longer_embeds_skill_manager():
    js = Path("channel/web/static/js/console.js").read_text(encoding="utf-8")

    config_start = js.index("async function renderInvestmentConfig()")
    config_end = js.index("function renderInvestmentSkillManager()")
    config_body = js[config_start:config_end]

    assert "renderInvestmentSkillManager()" not in config_body
    assert "loadInvestmentSkillVersions()" not in config_body
```

- [ ] **Step 2: Add navigation and page dispatch**

In `channel/web/static/js/console.js`, add:

```javascript
menu_invest_skills: '投资Skill'
```

```javascript
menu_invest_skills: 'Investment Skills'
```

Add mappings:

```javascript
'invest-skills': { group: 'nav_investment', page: 'menu_invest_skills' },
'invest-skills': 'skills.read',
```

Add dispatch:

```javascript
if (viewId === 'invest-skills') return renderInvestmentSkills();
```

- [ ] **Step 3: Remove Skill manager from config page**

In `renderInvestmentConfig()`, remove:

```javascript
const canReadSkills = investmentCan('skills.read');
${canReadSkills ? renderInvestmentSkillManager() : ''}
if (canReadSkills) loadInvestmentSkillVersions();
```

- [ ] **Step 4: Add standalone page renderer and package upload control**

Add:

```javascript
async function renderInvestmentSkills() {
    const element = investmentContentEl('invest-skills-content');
    investmentLoading(element);
    try {
        element.innerHTML = `
            <div class="investment-layout">
                <section class="investment-panel investment-workbench-full">
                    <div class="investment-panel-heading">
                        <div>
                            <div class="investment-panel-title"><i class="fas fa-upload"></i><span>新增投资Skill</span></div>
                            <div class="investment-subtitle">上传包含 SKILL.md 的 .zip 投资 Skill 包。</div>
                        </div>
                    </div>
                    <div class="investment-inline-form">
                        <label class="investment-btn investment-skill-upload-btn">
                            <i class="fas fa-upload"></i><span>上传 Skill 包</span>
                            <input id="invest-skill-package-file" type="file" accept=".zip" onchange="uploadInvestmentSkillPackage()">
                        </label>
                        <div id="invest-skill-package-result" class="investment-muted"></div>
                    </div>
                </section>
                ${renderInvestmentSkillManager()}
            </div>`;
        await loadInvestmentSkillVersions();
    } catch (error) {
        investmentError(element, error);
    }
}
```

- [ ] **Step 5: Add settings editor and package upload functions**

Add trigger editing in `renderInvestmentSkillConfigRow()` and add:

```javascript
async function saveInvestmentSkillSettings(skillKey) {
    const enabledInput = document.getElementById(`invest-skill-enabled-${skillKey}`);
    const triggersInput = document.getElementById(`invest-skill-triggers-${skillKey}`);
    const body = {operator: 'web-console', enabled: enabledInput ? enabledInput.checked : true};
    if (triggersInput) {
        body.triggers = triggersInput.value.split(/[,，]/).map(item => item.trim()).filter(Boolean);
    }
    try {
        await investmentFetchJson(`/api/investment/skills/${encodeURIComponent(skillKey)}/settings`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body),
        });
        showInvestmentToast('Skill 设置已保存');
        await loadInvestmentSkillVersions();
    } catch (error) {
        showInvestmentToast(`保存失败：${String(error.message || error)}`, 'error');
    }
}


async function uploadInvestmentSkillPackage() {
    const input = document.getElementById('invest-skill-package-file');
    const result = document.getElementById('invest-skill-package-result');
    if (!input || !input.files.length) return;
    const form = new FormData();
    form.append('file', input.files[0]);
    form.append('operator', 'web-console');
    if (result) result.textContent = '上传中...';
    try {
        await investmentFetchJson('/api/investment/skills/packages/upload', {method: 'POST', body: form});
        input.value = '';
        if (result) result.textContent = 'Skill 包已上传';
        showInvestmentToast('Skill 包已上传');
        await loadInvestmentSkillVersions();
    } catch (error) {
        if (result) result.textContent = String(error.message || error);
        showInvestmentToast('Skill 包上传失败', 'error');
    }
}
```

Expose:

```javascript
window.saveInvestmentSkillSettings = saveInvestmentSkillSettings;
window.uploadInvestmentSkillPackage = uploadInvestmentSkillPackage;
```

- [ ] **Step 6: Run Web UI tests**

Run:

```powershell
py -m pytest tests/test_investment_web_ui.py -q
```

Expected: tests pass.

---

## Task 7: Verify Existing Business Flows

**Files:**
- Test only unless failures reveal a bug.

- [ ] **Step 1: Run focused tests**

Run:

```powershell
py -m pytest tests/test_investment_business.py tests/test_wechatmp_investment_reply.py tests/test_investment_web_ui.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Smoke expected keywords**

Use existing tests first. If manual smoke is needed after starting the app:

```text
利率
转债
300502.SZ 技术分析
```

Expected:

- `利率` returns the current effective rate image.
- `转债` returns the current effective convertible bond image.
- `300502.SZ 技术分析` runs or starts the technical-analysis flow.

---

## Acceptance Criteria

- `投资Skill` is a standalone page.
- The system config page no longer embeds investment Skill configuration.
- Investment Skill keyword triggers can be edited in Web UI.
- Investment Skill package upload accepts `.zip` packages with root `SKILL.md`.
- Uploaded investment Skill packages appear in the investment Skill list.
- Original CowAgent general Skills are not used for investment routing or investment Skill configuration.
- Existing update/version behavior still works for script-backed built-ins such as `technical-analysis` and `signal-card-renderer`.
- `signal-card-renderer` remains an internal component by default.

## Execution Notes

- Keep this implementation intentionally small.
- Do not add regex triggers in this pass.
- Do not move investment settings into `skills_config.json`.
- Use `SKILL.md` frontmatter as package metadata only; do not invoke `agent.skills.SkillManager`.
- Store Web overrides in `investment_configs` using:
  - `skill.<skill_key>.enabled`
  - `skill.<skill_key>.triggers`
- Uploaded packages live under the investment storage root, for example `investment/investment-skills/<skill_key>/`.

