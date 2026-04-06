import json
from pathlib import Path


class BaseParser:
    """Base class for all ANAF parsers.

    Subclasses must set `name` and implement `run()`.
    """

    name = None

    def __init__(self, output_dir="output"):
        self.output_dir = Path(output_dir) / self.name
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def run(self):
        raise NotImplementedError

    def save_json(self, data, filename):
        path = self.output_dir / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"  Saved {path}")
