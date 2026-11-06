"""Allow running as ``python -m scripts.check.frontend_amount_guard``."""
from .cli import main
import sys

sys.exit(main())
