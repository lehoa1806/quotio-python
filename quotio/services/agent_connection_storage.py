"""Storage service for managing multiple named agent connections."""

import json
from pathlib import Path
from typing import List, Optional, Dict
from datetime import datetime
import uuid

from ..models.agent_connections import NamedAgentConnection
from ..models.agents import CLIAgent


class AgentConnectionStorage:
    """Manages storage of multiple named agent connections."""

    STORAGE_FILE = "~/.quotio/agent_connections.json"

    def __init__(self):
        """Initialize the storage service."""
        self.home = Path.home()
        storage_path = Path(self.STORAGE_FILE.replace("~", str(self.home)))
        self.storage_path = storage_path
        storage_path.parent.mkdir(parents=True, exist_ok=True)

    def load_connections(self) -> Dict[str, List[NamedAgentConnection]]:
        """Load all connections, grouped by agent type.

        Returns:
            Dict mapping agent type (str) to list of connections
        """
        if not self.storage_path.exists():
            return {}

        try:
            with open(self.storage_path, "r") as f:
                data = json.load(f)

            # Convert JSON data back to NamedAgentConnection objects
            connections_by_agent: Dict[str, List[NamedAgentConnection]] = {}

            for agent_str, connections_list in data.items():
                try:
                    agent = CLIAgent(agent_str)
                    connections = []

                    for conn_data in connections_list:
                        # Parse datetime strings
                        created_at = None
                        if conn_data.get("created_at"):
                            created_at = datetime.fromisoformat(conn_data["created_at"])

                        last_used = None
                        if conn_data.get("last_used"):
                            last_used = datetime.fromisoformat(conn_data["last_used"])

                        connection = NamedAgentConnection(
                            id=conn_data["id"],
                            name=conn_data["name"],
                            agent=agent,
                            api_key=conn_data["api_key"],
                            proxy_url=conn_data.get("proxy_url"),
                            model_slots=conn_data.get("model_slots", {}),
                            created_at=created_at,
                            last_used=last_used
                        )
                        connections.append(connection)

                    connections_by_agent[agent_str] = connections
                except (ValueError, KeyError) as e:
                    print(f"[AgentConnectionStorage] Error loading connections for {agent_str}: {e}")
                    continue

            return connections_by_agent
        except Exception as e:
            print(f"[AgentConnectionStorage] Error loading connections: {e}")
            return {}

    def save_connections(self, connections_by_agent: Dict[str, List[NamedAgentConnection]]) -> None:
        """Save all connections to storage.

        Args:
            connections_by_agent: Dict mapping agent type to list of connections
        """
        try:
            # Convert to JSON-serializable format
            data = {}

            for agent_str, connections in connections_by_agent.items():
                connections_list = []
                for conn in connections:
                    conn_data = {
                        "id": conn.id,
                        "name": conn.name,
                        "api_key": conn.api_key,
                        "proxy_url": conn.proxy_url,
                        "model_slots": conn.model_slots or {},
                        "created_at": conn.created_at.isoformat() if conn.created_at else None,
                        "last_used": conn.last_used.isoformat() if conn.last_used else None,
                    }
                    connections_list.append(conn_data)

                data[agent_str] = connections_list

            # Write to file
            with open(self.storage_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[AgentConnectionStorage] Error saving connections: {e}")
            raise

    def add_connection(self, connection: NamedAgentConnection) -> None:
        """Add a new connection."""
        connections_by_agent = self.load_connections()
        agent_str = connection.agent.value

        if agent_str not in connections_by_agent:
            connections_by_agent[agent_str] = []

        # Check if connection with same ID already exists
        existing = [c for c in connections_by_agent[agent_str] if c.id == connection.id]
        if existing:
            # Update existing
            connections_by_agent[agent_str] = [
                c if c.id != connection.id else connection
                for c in connections_by_agent[agent_str]
            ]
        else:
            # Add new
            connections_by_agent[agent_str].append(connection)

        self.save_connections(connections_by_agent)

    def remove_connection(self, connection_id: str, agent: CLIAgent) -> bool:
        """Remove a connection by ID.

        Returns:
            True if connection was found and removed, False otherwise
        """
        connections_by_agent = self.load_connections()
        agent_str = agent.value

        if agent_str not in connections_by_agent:
            return False

        original_count = len(connections_by_agent[agent_str])
        connections_by_agent[agent_str] = [
            c for c in connections_by_agent[agent_str] if c.id != connection_id
        ]

        removed = len(connections_by_agent[agent_str]) < original_count
        if removed:
            self.save_connections(connections_by_agent)

        return removed

    def get_connections_for_agent(self, agent: CLIAgent) -> List[NamedAgentConnection]:
        """Get all connections for a specific agent type."""
        connections_by_agent = self.load_connections()
        agent_str = agent.value
        return connections_by_agent.get(agent_str, [])

    def get_connection_by_id(self, connection_id: str, agent: CLIAgent) -> Optional[NamedAgentConnection]:
        """Get a specific connection by ID."""
        connections = self.get_connections_for_agent(agent)
        for conn in connections:
            if conn.id == connection_id:
                return conn
        return None

    def update_connection(self, connection: NamedAgentConnection) -> bool:
        """Update an existing connection.

        Returns:
            True if connection was found and updated, False otherwise
        """
        connections_by_agent = self.load_connections()
        agent_str = connection.agent.value

        if agent_str not in connections_by_agent:
            return False

        found = False
        for i, conn in enumerate(connections_by_agent[agent_str]):
            if conn.id == connection.id:
                connections_by_agent[agent_str][i] = connection
                found = True
                break

        if found:
            self.save_connections(connections_by_agent)

        return found

    @staticmethod
    def generate_connection_id() -> str:
        """Generate a unique connection ID."""
        return str(uuid.uuid4())
