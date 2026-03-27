"""Base class for agent tools."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from weavbot.utils.helpers import normalize_session_key


@dataclass
class DeliveryTarget:
    """Normalized message delivery target."""

    channel: str
    chat_id: str
    session_key: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_optional(
        cls,
        *,
        channel: str | None,
        chat_id: str | None,
        session_key: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "DeliveryTarget | None":
        """Build target when channel/chat_id are both available."""
        ch = (channel or "").strip()
        cid = (chat_id or "").strip()
        if not ch or not cid:
            return None
        skey = normalize_session_key((session_key or "").strip() or f"{ch}:{cid}")
        return cls(channel=ch, chat_id=cid, session_key=skey, metadata=dict(metadata or {}))

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "DeliveryTarget | None":
        """Build target from persisted dict representation."""
        payload = raw if isinstance(raw, dict) else {}
        return cls.from_optional(
            channel=payload.get("channel"),
            chat_id=payload.get("chat_id"),
            session_key=payload.get("session_key"),
            metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert target to dict for persistence/transport."""
        return {
            "channel": self.channel,
            "chat_id": self.chat_id,
            "session_key": self.session_key,
            "metadata": dict(self.metadata or {}),
        }

    def matches(self, *, channel: str, chat_id: str) -> bool:
        """Check whether the given route points to this target."""
        return channel == self.channel and chat_id == self.chat_id


@dataclass
class ToolExecutionContext(DeliveryTarget):
    """Per-tool-call runtime routing context."""

    message_id: str | None = None
    interactive: DeliveryTarget | None = None


@dataclass
class ToolResult:
    """Result from a tool that includes media file references."""

    content: str
    media: list[str] = field(default_factory=list)


class Tool(ABC):
    """
    Abstract base class for agent tools.

    Tools are capabilities that the agent can use to interact with
    the environment, such as reading files, executing commands, etc.
    """

    _TYPE_MAP = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "array": list,
        "object": dict,
    }

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name used in function calls."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Description of what the tool does."""
        pass

    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        """JSON Schema for tool parameters."""
        pass

    @abstractmethod
    async def execute(self, *, context: ToolExecutionContext, **kwargs: Any) -> str | ToolResult:
        """
        Execute the tool with given parameters.

        Args:
            context: Runtime execution context for routing/session information.
            **kwargs: Tool-specific parameters.

        Returns:
            String result, or a ToolResult with content and media file paths.
        """
        pass

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        """Validate tool parameters against JSON schema. Returns error list (empty if valid)."""
        schema = self.parameters or {}
        if schema.get("type", "object") != "object":
            raise ValueError(f"Schema must be object type, got {schema.get('type')!r}")
        return self._validate(params, {**schema, "type": "object"}, "")

    def _validate(self, val: Any, schema: dict[str, Any], path: str) -> list[str]:
        t, label = schema.get("type"), path or "parameter"
        if t in self._TYPE_MAP and not isinstance(val, self._TYPE_MAP[t]):
            return [f"{label} should be {t}"]

        errors = []
        if "enum" in schema and val not in schema["enum"]:
            errors.append(f"{label} must be one of {schema['enum']}")
        if t in ("integer", "number"):
            if "minimum" in schema and val < schema["minimum"]:
                errors.append(f"{label} must be >= {schema['minimum']}")
            if "maximum" in schema and val > schema["maximum"]:
                errors.append(f"{label} must be <= {schema['maximum']}")
        if t == "string":
            if "minLength" in schema and len(val) < schema["minLength"]:
                errors.append(f"{label} must be at least {schema['minLength']} chars")
            if "maxLength" in schema and len(val) > schema["maxLength"]:
                errors.append(f"{label} must be at most {schema['maxLength']} chars")
        if t == "object":
            props = schema.get("properties", {})
            for k in schema.get("required", []):
                if k not in val:
                    errors.append(f"missing required {path + '.' + k if path else k}")
            for k, v in val.items():
                if k in props:
                    errors.extend(self._validate(v, props[k], path + "." + k if path else k))
        if t == "array" and "items" in schema:
            for i, item in enumerate(val):
                errors.extend(
                    self._validate(item, schema["items"], f"{path}[{i}]" if path else f"[{i}]")
                )
        return errors

    def to_schema(self) -> dict[str, Any]:
        """Convert tool to OpenAI function schema format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
