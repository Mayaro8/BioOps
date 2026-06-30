from dataclasses import dataclass

@dataclass
class DelayConfig:
    """
    - delay: int
    - step: int
    - chunk_size: int 
    """
    delay: int = 0
    step: int = 10
    chunk_size: int = 1

