from abc import ABC, abstractmethod
from typing import Any, Dict, List


class EvidenceExtractor(ABC):
    name = "base"

    @abstractmethod
    def detect(self, file_info: Dict[str, Any], lines: List[str]) -> bool:
        raise NotImplementedError

    @abstractmethod
    def extract(self, file_info: Dict[str, Any], lines: List[str]) -> List[Dict[str, Any]]:
        raise NotImplementedError
