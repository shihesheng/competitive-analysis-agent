import logging, os
logging.basicConfig(level=getattr(logging, os.getenv("LOG_LEVEL","INFO")),
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
def get_logger(name: str): return logging.getLogger(name)
