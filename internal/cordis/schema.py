"""Minimal schema validation used to check plugin configs.

The API mirrors the subset of ``@deepseek-ai/schemastery`` that plugin authors
actually use::

    schema = Schema.object({
        'enabled': Schema.boolean().default(True),
        'port': Schema.natural().min(1).max(65535).default(8080),
        'mode': Schema.union(['local', 'remote']).default('local'),
    })

    config = schema(config_dict)   # raises ValidationError on mismatch
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from .errors import ConfigError, ValidationError

__all__ = ["Schema", "validate_config"]


class Schema:
    """A single value schema node."""

    def __init__(self, kind: str, *, nullable: bool = False) -> None:
        self.kind = kind
        self.nullable = nullable
        self._has_default = False
        self._default: Any = None
        self._required = False
        self._label = ""
        self._description = ""
        self._comment = ""

    # ------------------------------------------------------------------ dsl
    def default(self, value: Any) -> "Schema":
        self._has_default = True
        self._default = value
        return self

    def required(self, value: bool = True) -> "Schema":
        self._required = value
        return self

    def description(self, text: str) -> "Schema":
        self._description = text
        return self

    def comment(self, text: str) -> "Schema":
        self._comment = text
        return self

    def label(self, text: str) -> "Schema":
        self._label = text
        return self

    @property
    def has_default(self) -> bool:
        return self._has_default

    @property
    def default_value(self) -> Any:
        return self._default

    # -------------------------------------------------------------- dispatch
    def __call__(self, value: Any = None) -> Any:
        """Validate (and fill) a config value."""
        return self.validate(value, "")

    def validate(self, value: Any, path: str) -> Any:
        _ = value, path
        raise ConfigError(f"schema kind '{self.kind}' cannot validate anything")

    def _missing(self, path: str) -> Any:
        if self._has_default:
            return self._default
        if self._required:
            raise ValidationError(path, "required value is missing")
        return None

    def _accept_none(self, value: Any, path: str) -> tuple[bool, Any]:
        if value is None:
            if self.nullable:
                return True, None
            provided = self._missing(path)
            return True, provided
        return False, None

    # ----------------------------------------------------------- constructors
    @staticmethod
    def any() -> "Schema":
        return _AnySchema()

    @staticmethod
    def boolean() -> "Schema":
        return _BooleanSchema()

    @staticmethod
    def string() -> "StringSchema":
        return StringSchema()

    @staticmethod
    def number() -> "NumberSchema":
        return NumberSchema()

    @staticmethod
    def natural() -> "NumberSchema":
        return NumberSchema(integer=True, minimum=0)

    @staticmethod
    def integer() -> "NumberSchema":
        return NumberSchema(integer=True)

    @staticmethod
    def array(inner: "Schema | None" = None) -> "ArraySchema":
        return ArraySchema(inner)

    @staticmethod
    def dict(inner: "Schema | None" = None) -> "DictSchema":
        return DictSchema(inner)

    @staticmethod
    def object(shape: Mapping[str, "Schema"] | None = None) -> "ObjectSchema":
        return ObjectSchema(shape)

    @staticmethod
    def const(value: Any) -> "ConstSchema":
        return ConstSchema(value)

    @staticmethod
    def union(options: Iterable[Any]) -> "UnionSchema":
        return UnionSchema(list(options))


class _AnySchema(Schema):
    def __init__(self) -> None:
        super().__init__("any")

    def validate(self, value: Any, path: str) -> Any:
        if value is None:
            return self._missing(path)
        return value


class _BooleanSchema(Schema):
    def __init__(self) -> None:
        super().__init__("boolean")

    def validate(self, value: Any, path: str) -> Any:
        handled, resolved = self._accept_none(value, path)
        if handled:
            return resolved
        if not isinstance(value, bool):
            raise ValidationError(path, f"expected boolean, got {type(value).__name__}")
        return value


class StringSchema(Schema):
    def __init__(self) -> None:
        super().__init__("string")
        self._pattern: str | None = None
        self._min_length: int | None = None
        self._max_length: int | None = None

    def pattern(self, regex: str) -> "StringSchema":
        self._pattern = regex
        return self

    def min_length(self, value: int) -> "StringSchema":
        self._min_length = value
        return self

    def max_length(self, value: int) -> "StringSchema":
        self._max_length = value
        return self

    def validate(self, value: Any, path: str) -> Any:
        handled, resolved = self._accept_none(value, path)
        if handled:
            return resolved
        if not isinstance(value, str):
            raise ValidationError(path, f"expected string, got {type(value).__name__}")
        return value


class NumberSchema(Schema):
    def __init__(self, *, integer: bool = False, minimum: float | None = None) -> None:
        super().__init__("integer" if integer else "number")
        self._integer = integer
        self._minimum = minimum
        self._maximum: float | None = None

    def min(self, value: float) -> "NumberSchema":
        self._minimum = value
        return self

    def max(self, value: float) -> "NumberSchema":
        self._maximum = value
        return self

    def validate(self, value: Any, path: str) -> Any:
        handled, resolved = self._accept_none(value, path)
        if handled:
            return resolved
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValidationError(path, f"expected number, got {type(value).__name__}")
        if self._integer and not isinstance(value, int):
            raise ValidationError(path, "expected integer")
        if self._minimum is not None and value < self._minimum:
            raise ValidationError(path, f"value {value} is below minimum {self._minimum}")
        if self._maximum is not None and value > self._maximum:
            raise ValidationError(path, f"value {value} is above maximum {self._maximum}")
        return value


class ArraySchema(Schema):
    def __init__(self, inner: Schema | None = None) -> None:
        super().__init__("array")
        self._inner = inner

    def validate(self, value: Any, path: str) -> Any:
        handled, resolved = self._accept_none(value, path)
        if handled:
            return resolved
        if not isinstance(value, list):
            raise ValidationError(path, f"expected array, got {type(value).__name__}")
        if self._inner is None:
            return list(value)
        return [self._inner.validate(item, f"{path}[{index}]") for index, item in enumerate(value)]


class DictSchema(Schema):
    def __init__(self, inner: Schema | None = None) -> None:
        super().__init__("dict")
        self._inner = inner

    def validate(self, value: Any, path: str) -> Any:
        if not isinstance(value, Mapping):
            raise ValidationError(path, f"expected object, got {type(value).__name__}")
        if self._inner is None:
            return dict(value)
        return {str(key): self._inner.validate(item, _join(path, str(key))) for key, item in value.items()}


class ObjectSchema(Schema):
    def __init__(self, shape: Mapping[str, Schema] | None = None) -> None:
        super().__init__("object")
        self._shape: dict[str, Schema] = dict(shape or {})

    @property
    def shape(self) -> Mapping[str, Schema]:
        return self._shape

    def validate(self, value: Any, path: str) -> Any:
        handled, resolved = self._accept_none(value, path)
        if handled:
            return resolved
        if not isinstance(value, Mapping):
            raise ValidationError(path, f"expected object, got {type(value).__name__}")
        result: dict[str, Any] = {}
        for key, schema in self._shape.items():
            result[key] = schema.validate(value.get(key), _join(path, key))
        for key in value:
            if key not in self._shape:
                raise ValidationError(_join(path, str(key)), "unknown key")
        return result


class ConstSchema(Schema):
    def __init__(self, expected: Any) -> None:
        super().__init__("const")
        self._expected = expected

    def validate(self, value: Any, path: str) -> Any:
        handled, resolved = self._accept_none(value, path)
        if handled:
            return resolved
        if value != self._expected:
            raise ValidationError(path, f"expected const {self._expected!r}, got {value!r}")
        return value


class UnionSchema(Schema):
    def __init__(self, options: list[Any]) -> None:
        super().__init__("union")
        self._options = options

    def validate(self, value: Any, path: str) -> Any:
        handled, resolved = self._accept_none(value, path)
        if handled:
            return resolved
        if value not in self._options:
            raise ValidationError(path, f"expected one of {self._options!r}, got {value!r}")
        return value


def _join(path: str, key: str) -> str:
    return f"{path}.{key}" if path else key


def validate_config(schema: Schema | None, config: Any) -> Any:
    """Validate a plugin config, returning a normalised mapping."""
    if schema is None:
        return {} if config is None else config
    return schema(config if config is not None else {})


def schema_shape(schema: Schema | None) -> Mapping[str, Schema] | None:
    """Return the declared shape of an object schema (used for diagnostics)."""
    if isinstance(schema, ObjectSchema):
        return schema.shape
    return None
