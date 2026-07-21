"""Multi-node virtual UART network for the 8051 emulator.

Connects multiple emulator sessions via unidirectional TX→RX links,
enabling virtual serial communication between independently running
8051 programs.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import asdict, dataclass, field
from threading import RLock
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .session import SessionStore


@dataclass
class UARTLink:
    """A unidirectional TX→RX link between two sessions."""
    link_id: str
    source_session_id: str      # TX side — bytes read from this session's tx_log
    target_session_id: str      # RX side — bytes injected into this session's rx_queue
    created_at: float
    bytes_transferred: int = 0
    _tx_cursor: int = 0         # Tracks how many bytes from source tx_log have been transferred

    def to_dict(self) -> dict[str, Any]:
        return {
            "link_id": self.link_id,
            "source_session_id": self.source_session_id,
            "target_session_id": self.target_session_id,
            "created_at": self.created_at,
            "bytes_transferred": self.bytes_transferred,
        }


class UARTNetwork:
    """Manages unidirectional UART links between emulator sessions.

    Links are TX→RX: bytes transmitted by the source session's CPU
    are injected into the target session's CPU receive queue.

    For bidirectional communication, create two links (A→B and B→A),
    which mirrors real-world UART wiring where TXD connects to RXD.
    """

    def __init__(self) -> None:
        self._links: dict[str, UARTLink] = {}
        self._lock = RLock()

    def link(self, source_session_id: str, target_session_id: str) -> UARTLink:
        """Create a unidirectional TX→RX link between two sessions.

        Args:
            source_session_id: The session whose TX output will be forwarded.
            target_session_id: The session whose RX input will receive the data.

        Returns:
            The newly created UARTLink.

        Raises:
            ValueError: If source and target are the same session, or if
                a duplicate link already exists.
        """
        if source_session_id == target_session_id:
            raise ValueError("Cannot link a session to itself")

        with self._lock:
            # Check for duplicate links
            for existing in self._links.values():
                if (existing.source_session_id == source_session_id and
                        existing.target_session_id == target_session_id):
                    raise ValueError(
                        f"Link already exists from {source_session_id} to "
                        f"{target_session_id} (link_id={existing.link_id})"
                    )

            link_id = secrets.token_urlsafe(16)
            link = UARTLink(
                link_id=link_id,
                source_session_id=source_session_id,
                target_session_id=target_session_id,
                created_at=time.time(),
            )
            self._links[link_id] = link
            return link

    def unlink(self, link_id: str) -> bool:
        """Remove a specific link by ID.

        Returns True if the link existed and was removed.
        """
        with self._lock:
            return self._links.pop(link_id, None) is not None

    def unlink_session(self, session_id: str) -> int:
        """Remove all links involving a session (as source or target).

        Returns the number of links removed.
        """
        with self._lock:
            to_remove = [
                link_id for link_id, link in self._links.items()
                if link.source_session_id == session_id or link.target_session_id == session_id
            ]
            for link_id in to_remove:
                del self._links[link_id]
            return len(to_remove)

    def transfer(self, session_store: "SessionStore", *, session_id: str | None = None) -> int:
        """Transfer pending TX bytes across all active links.

        For each link, reads new bytes from the source session's
        ``cpu.serial.tx_log`` (starting from the cursor position) and
        injects them into the target session's CPU via ``inject_serial_rx``.

        Args:
            session_store: The session store to look up sessions.
            session_id: If provided, only transfer for links involving
                this session as the source. If None, transfer for all links.

        Returns:
            Total number of bytes transferred across all links.
        """
        total_transferred = 0

        with self._lock:
            links_snapshot = list(self._links.values())

        for link in links_snapshot:
            if session_id is not None and link.source_session_id != session_id:
                continue

            try:
                source = session_store.backend.get(link.source_session_id)
                if source is None:
                    continue

                target = session_store.backend.get(link.target_session_id)
                if target is None:
                    continue

                # Read new bytes from source TX log
                tx_log = source.cpu.serial.tx_log
                cursor = link._tx_cursor
                if cursor >= len(tx_log):
                    continue

                new_bytes = tx_log[cursor:]
                if not new_bytes:
                    continue

                # Inject into target RX
                if hasattr(target.cpu, "inject_serial_rx"):
                    target.cpu.inject_serial_rx(new_bytes)
                    session_store.save(target)

                # Update cursor and stats
                with self._lock:
                    if link.link_id in self._links:
                        self._links[link.link_id]._tx_cursor = len(tx_log)
                        self._links[link.link_id].bytes_transferred += len(new_bytes)

                total_transferred += len(new_bytes)

            except Exception:
                # Don't let a single broken link disrupt the entire network
                continue

        return total_transferred

    def get_links(self, session_id: str | None = None) -> list[UARTLink]:
        """Get all links, optionally filtered by session involvement.

        Args:
            session_id: If provided, only return links where this session
                is either the source or the target.

        Returns:
            List of matching UARTLink objects.
        """
        with self._lock:
            if session_id is None:
                return list(self._links.values())
            return [
                link for link in self._links.values()
                if link.source_session_id == session_id or link.target_session_id == session_id
            ]

    def status(self) -> dict[str, Any]:
        """Get network status summary."""
        with self._lock:
            links = list(self._links.values())
        return {
            "total_links": len(links),
            "total_bytes_transferred": sum(link.bytes_transferred for link in links),
            "links": [link.to_dict() for link in links],
        }

    def reset_cursor(self, link_id: str) -> None:
        """Reset the TX cursor for a link (e.g., after source session reset)."""
        with self._lock:
            if link_id in self._links:
                self._links[link_id]._tx_cursor = 0
                self._links[link_id].bytes_transferred = 0
