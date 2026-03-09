from rolemesh import adapters, core, routing


def test_routing_all_exports_expected_public_api():
    assert routing.__all__ == [
        "RoleMeshOrchestrator",
        "SymphonyMACRS",
        "WorkItem",
        "WorkResult",
        "RoleMapper",
        "IntegrationManager",
        "DuplicateIntegrationError",
        "IntegrationNotFoundError",
    ]
    assert routing.RoleMeshOrchestrator is routing.SymphonyMACRS


def test_core_and_adapters_all_exports_expected_public_api():
    assert core.__all__ == [
        "RegistryClient",
        "AgentMatch",
        "Message",
        "build_contract",
        "init_db",
        "QualityTracker",
    ]
    assert adapters.__all__ == [
        "ProviderCircuitBreaker",
        "CBState",
        "TokenBucketThrottle",
        "ProviderRouter",
        "SmartRouter",
        "ask_amp",
        "ask_amp_async",
    ]
