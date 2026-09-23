def test_prefer_healthy_orders_unhealthy_last_without_breaking_priority():
    from selfhost.profiles import _prefer_healthy

    healthy = {"id": "a", "capabilities": {"runtime": {"status": "healthy"}}}
    unhealthy = {"id": "b", "capabilities": {"runtime": {"status": "unhealthy"}}}
    unknown = {"id": "c", "capabilities": {}}

    ordered = _prefer_healthy([unhealthy, healthy, unknown])

    # Healthy and unknown providers keep their priority order; the provider that
    # is currently marked unhealthy is only tried after them.
    assert [profile["id"] for profile in ordered] == ["a", "c", "b"]


def test_prefer_healthy_is_a_noop_when_every_provider_is_healthy():
    from selfhost.profiles import _prefer_healthy

    profiles = [{"id": str(index), "capabilities": {"runtime": {"status": "healthy"}}} for index in range(3)]

    assert _prefer_healthy(profiles) == profiles
