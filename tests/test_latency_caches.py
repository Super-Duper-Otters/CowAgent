# encoding:utf-8


def test_get_config_reuses_short_lived_cache_and_save_invalidates(business_env, monkeypatch):
    from business.config import config_service

    config_service.save_config("prompt.rate", "v1", operator_role="admin")
    config_service.clear_config_cache()

    original_connect = config_service.connect
    calls = {"count": 0}

    def counted_connect(*args, **kwargs):
        calls["count"] += 1
        return original_connect(*args, **kwargs)

    monkeypatch.setattr(config_service, "connect", counted_connect)

    assert config_service.get_config("prompt.rate") == "v1"
    assert config_service.get_config("prompt.rate") == "v1"
    assert calls["count"] == 1

    config_service.save_config("prompt.rate", "v2", operator_role="admin")

    assert config_service.get_config("prompt.rate") == "v2"
    assert calls["count"] == 3


def test_business_definitions_cache_reuses_directory_scan_and_config_save_keeps_route_fresh(business_env, monkeypatch):
    from business.components import registry
    from business.config.config_service import save_config
    from business.config.constants import ServiceType

    registry.clear_business_definition_cache()
    original_merge = registry._merge_component_definitions
    calls = {"count": 0}

    def counted_merge(definitions, root):
        calls["count"] += 1
        return original_merge(definitions, root)

    monkeypatch.setattr(registry, "_merge_component_definitions", counted_merge)

    first = registry.list_business_definitions()
    second = registry.list_business_definitions()

    assert first == second
    assert calls["count"] == 2

    save_config("skill.technical-analysis.triggers", ["走势分析"], operator_role="admin", operator="pytest")

    route = registry.match_business("300502.SZ 走势分析")

    assert route is not None
    assert route.service_type == ServiceType.TECHNICAL_ANALYSIS
    assert route.target_text == "300502.SZ"
