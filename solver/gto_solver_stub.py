from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class GTOSolverStub:
    """Phase 1 placeholder for the future GTO+ socket integration.

    Phase 2 target:
    - host: 127.0.0.1
    - port: 55143
    - protocol: local socket bridge to GTO+
    """

    host: str = "127.0.0.1"
    port: int = 55143
    enabled: bool = False

    def analyze(self, game_state: Dict[str, Any]) -> Dict[str, Any]:
        street = str(game_state.get("street", "")).lower()

        if street == "preflop":
            return {
                "status": "pass",
                "street": street,
                "message": "Pre-flop spot detected: skipping GTO+ in Phase 1.",
                "socket": None,
            }

        return {
            "status": "not_enabled",
            "street": street,
            "message": "GTO+ solving not yet enabled.",
            "socket": {
                "host": self.host,
                "port": self.port,
                "enabled": self.enabled,
            },
        }

    def analyze_with_gto_plus(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Phase 2 hook: send payload over socket and parse solver response."""
        raise NotImplementedError("GTO+ socket integration arrives in Phase 2.")
