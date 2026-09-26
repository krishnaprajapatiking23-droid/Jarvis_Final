from brains_v2.reference_resolver import ReferenceResolver


def test_resolve_it_to_previous_entity():
    resolver = ReferenceResolver()

    resolver.remember_entity("calculator")

    result = resolver.resolve("open it")

    assert result["resolved"] is True
    assert result["reference"] == "it"
    assert result["entity"] == "calculator"


def test_resolve_this_and_that():
    resolver = ReferenceResolver()

    resolver.remember_entity("Python project")

    assert resolver.resolve("fix this")["entity"] == "Python project"
    assert resolver.resolve("analyze that")["entity"] == "Python project"


def test_resolve_there_to_previous_location():
    resolver = ReferenceResolver()

    resolver.remember_location("school")

    result = resolver.resolve("go there")

    assert result["resolved"] is True
    assert result["reference"] == "there"
    assert result["entity"] == "school"


def test_unresolved_reference_without_context():
    resolver = ReferenceResolver()

    result = resolver.resolve("open it")

    assert result["resolved"] is False
    assert result["entity"] is None