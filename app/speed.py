import math


DEFAULT_SPEED_SCALE = 1.0


def normalize_speed_scale(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("speed_scale must be a number.")

    normalized = float(value)
    if not math.isfinite(normalized) or normalized <= 0:
        raise ValueError("speed_scale must be a finite number greater than zero.")
    return normalized


def format_speed_scale(value: object) -> str:
    return repr(normalize_speed_scale(value))
