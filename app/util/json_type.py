type JSON = str | int | float | bool | None | dict[str, "JSON"] | list["JSON"]


def get_bool(value: JSON) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        if value.lower() in ("true", "1", "yes", "on"):
            return True
        if value.lower() in ("false", "0", "no", "off"):
            return False
    return None
