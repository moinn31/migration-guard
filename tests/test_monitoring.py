from backend import observability
from backend.config import settings

def test_monitoring_initializes_with_declared_sdk_without_network(monkeypatch):
    import sentry_sdk
    original = sentry_sdk.init
    monkeypatch.setattr(settings, 'sentry_dsn', 'https://public@example.invalid/1')
    def initialize(**options):
        return original(**options, transport=lambda event: None, default_integrations=False)
    monkeypatch.setattr(sentry_sdk, 'init', initialize)
    observability.initialize_monitoring()
    sentry_sdk.get_client().close()
