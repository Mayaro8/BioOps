import logging
import sys

class ColoredFormatter(logging.Formatter):
    COLORS = {
        'INFO': '\033[32m',     # Зелёный
        'ERROR': '\033[31m',    # Красный
        'RESET': '\033[0m'      # Сброс цвета
    }

    def format(self, record):
        color = self.COLORS.get(record.levelname, '')
        message = super().format(record)
        if color:
            return f"{color}{message}{self.COLORS['RESET']}"
        return message

def setup_logging(debug_mode: bool = False) -> None:
    level = logging.DEBUG if debug_mode else logging.INFO
    
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Форматтер
    formatter = ColoredFormatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Обработчик для вывода в консоль
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
