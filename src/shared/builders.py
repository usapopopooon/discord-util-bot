"""Pure helper functions for string/object building."""

DEFAULT_CHANNEL_TEMPLATE = "{name}'s Channel"


def build_channel_name(
    owner_name: str, template: str = DEFAULT_CHANNEL_TEMPLATE
) -> str:
    """Build a channel name from owner display name and template."""
    return template.replace("{name}", owner_name)


def build_user_limit_options() -> list[tuple[str, int]]:
    """Build pre-defined voice user-limit options."""
    return [
        ("No Limit", 0),
        ("2 Users", 2),
        ("5 Users", 5),
        ("10 Users", 10),
        ("15 Users", 15),
        ("25 Users", 25),
        ("50 Users", 50),
    ]


def truncate_name(name: str, max_length: int = 100) -> str:
    """Truncate a channel name to the Discord max length."""
    if len(name) <= max_length:
        return name
    return name[: max_length - 3] + "..."
