"""Box flame sensor processing: burst of digital reads -> one yes / no per wake-up."""
from .config import MAX_SAMPLES, Config
from .sensor import FlameResult, process

__all__ = ["Config", "FlameResult", "process", "MAX_SAMPLES"]
