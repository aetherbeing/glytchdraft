"""Allow `python -m glytchos` to run the CLI."""
import sys
from glytchos.cli import main

sys.exit(main())
