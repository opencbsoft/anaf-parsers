import json
import zipfile
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
        zip_path = self.output_dir / (filename + ".zip")
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        json_bytes = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(filename, json_bytes)
        size_mb = zip_path.stat().st_size / (1024 * 1024)
        print(f"  Saved {zip_path} ({size_mb:.1f} MB)")
