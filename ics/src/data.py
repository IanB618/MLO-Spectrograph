import json
import time
from pathlib import Path

from src.models import ExposureRequest, ExposureResult, SystemSnapshot


class DataManager:
    def __init__(self, data_root: Path):
        self.data_root = data_root
        self.log_path = self.data_root / "observing_log.jsonl"
        self.data_root.mkdir(parents=True, exist_ok=True)

    def record_exposure(self, request: ExposureRequest, result: ExposureResult, snapshot: SystemSnapshot):
        entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "request": request.model_dump(mode="json"),
            "result": result.model_dump(mode="json"),
            "snapshot": snapshot.model_dump(mode="json"),
        }
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")

    def recent_log_entries(self, limit: int = 20):
        if not self.log_path.exists():
            return []
        lines = self.log_path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines[-limit:]]
