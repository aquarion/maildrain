import os
import tomllib
from dataclasses import dataclass, field

from dotenv import load_dotenv


@dataclass
class AppConfig:
    """Application-level settings: Gmail auth and the path to the servers file."""
    google_credentials_file: str
    google_token_file: str
    servers_file: str


@dataclass
class ServerConfig:
    """
    Settings for a single source mail account.

    IMAP credentials are always required (used for archiving, and for download
    when no POP3 credentials are provided).

    POP3 credentials are optional. When absent, IMAP is used for both download
    and archive, avoiding the need for two protocols on the same server.
    """
    name: str
    imap_host: str
    imap_port: int
    imap_username: str
    imap_password: str
    archive_folder: str = "Archive"
    labels: list[str] = field(default_factory=list)
    pop_host: str | None = None
    pop_port: int | None = None
    pop_username: str | None = None
    pop_password: str | None = None

    @property
    def use_pop(self) -> bool:
        """True if POP3 credentials are configured for this server."""
        return self.pop_host is not None


def load_config() -> AppConfig:
    """
    Load application config from environment variables.
    Reads .env if present; actual environment always takes precedence.
    """
    load_dotenv()
    return AppConfig(
        google_credentials_file=os.environ.get("GOOGLE_CREDENTIALS_FILE", "etc/credentials.json"),
        google_token_file=os.environ.get("GOOGLE_TOKEN_FILE", "etc/token.json"),
        servers_file=os.environ.get("SERVERS_FILE", "etc/servers.toml"),
    )


def load_servers(servers_file: str) -> list[ServerConfig]:
    """
    Load the list of source mail accounts from a TOML file.

    IMAP fields are always required. POP3 fields are optional; when absent,
    IMAP is used for both download and archive.

    Raises FileNotFoundError if the file is missing.
    Raises ValueError if any server entry is missing required fields.
    """
    try:
        with open(servers_file, "rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Servers config file not found: {servers_file!r}\n"
            f"Copy etc/servers.toml.example to {servers_file} and fill in your accounts."
        )

    raw_servers = data.get("servers", [])
    if not raw_servers:
        raise ValueError(f"No [[servers]] entries found in {servers_file!r}.")

    imap_required = ["name", "imap_host", "imap_port", "imap_username", "imap_password"]
    pop_fields = ["pop_host", "pop_port", "pop_username", "pop_password"]

    servers: list[ServerConfig] = []
    for i, entry in enumerate(raw_servers, start=1):
        label = entry.get("name", f"server #{i}")

        missing = [f for f in imap_required if f not in entry]
        if missing:
            raise ValueError(
                f"Server {label!r} is missing required fields: {', '.join(missing)}"
            )

        # If any POP3 field is present, all POP3 fields must be present.
        present_pop = [f for f in pop_fields if f in entry]
        if present_pop and len(present_pop) < len(pop_fields):
            missing_pop = [f for f in pop_fields if f not in entry]
            raise ValueError(
                f"Server {label!r} has some POP3 fields but is missing: {', '.join(missing_pop)}"
            )

        raw_labels = entry.get("labels", [])
        if isinstance(raw_labels, str):
            raw_labels = [raw_labels]

        servers.append(ServerConfig(
            name=label,
            imap_host=entry["imap_host"],
            imap_port=int(entry["imap_port"]),
            imap_username=entry["imap_username"],
            imap_password=entry["imap_password"],
            archive_folder=entry.get("archive_folder", "Archive"),
            labels=raw_labels,
            pop_host=entry.get("pop_host"),
            pop_port=int(entry["pop_port"]) if "pop_port" in entry else None,
            pop_username=entry.get("pop_username"),
            pop_password=entry.get("pop_password"),
        ))

    return servers
