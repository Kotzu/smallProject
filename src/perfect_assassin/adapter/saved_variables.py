from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


class SavedVariablesParseError(ValueError):
    """The file is outside the deliberately small SavedVariables grammar."""


@dataclass(frozen=True, slots=True)
class _Token:
    kind: str
    value: Any
    offset: int


class _Lexer:
    def __init__(self, source: str, *, max_tokens: int) -> None:
        self.source = source
        self.index = 0
        self.max_tokens = max_tokens
        self.tokens = 0

    def next(self) -> _Token:
        self._skip_space_and_comments()
        if self.index >= len(self.source):
            return self._emit("eof", None, self.index)
        start = self.index
        char = self.source[self.index]
        if char in "{}[]=,;":
            self.index += 1
            return self._emit(char, char, start)
        if char in "'\"":
            return self._string()
        if char.isdigit() or (char == "-" and self._peek_digit()):
            return self._number()
        if char.isalpha() or char == "_":
            self.index += 1
            while self.index < len(self.source):
                current = self.source[self.index]
                if not (current.isalnum() or current == "_"):
                    break
                self.index += 1
            return self._emit("identifier", self.source[start : self.index], start)
        raise SavedVariablesParseError(f"Unexpected character at offset {start}: {char!r}")

    def _emit(self, kind: str, value: Any, offset: int) -> _Token:
        self.tokens += 1
        if self.tokens > self.max_tokens:
            raise SavedVariablesParseError("SavedVariables token limit exceeded")
        return _Token(kind, value, offset)

    def _skip_space_and_comments(self) -> None:
        while self.index < len(self.source):
            if self.source[self.index].isspace():
                self.index += 1
                continue
            if self.source.startswith("--[[", self.index):
                raise SavedVariablesParseError("Block comments are not accepted")
            if self.source.startswith("--", self.index):
                newline = self.source.find("\n", self.index + 2)
                self.index = len(self.source) if newline < 0 else newline + 1
                continue
            return

    def _peek_digit(self) -> bool:
        return self.index + 1 < len(self.source) and self.source[self.index + 1].isdigit()

    def _number(self) -> _Token:
        start = self.index
        if self.source[self.index] == "-":
            self.index += 1
        while self.index < len(self.source) and self.source[self.index].isdigit():
            self.index += 1
        if self.index < len(self.source) and self.source[self.index] == ".":
            self.index += 1
            if self.index >= len(self.source) or not self.source[self.index].isdigit():
                raise SavedVariablesParseError(f"Malformed number at offset {start}")
            while self.index < len(self.source) and self.source[self.index].isdigit():
                self.index += 1
        text = self.source[start : self.index]
        value: int | float = float(text) if "." in text else int(text)
        return self._emit("number", value, start)

    def _string(self) -> _Token:
        start = self.index
        quote = self.source[self.index]
        self.index += 1
        output: list[str] = []
        escapes = {"a": "\a", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v", "\\": "\\", '"': '"', "'": "'"}
        while self.index < len(self.source):
            char = self.source[self.index]
            self.index += 1
            if char == quote:
                return self._emit("string", "".join(output), start)
            if char in "\r\n":
                raise SavedVariablesParseError(f"Unescaped newline in string at offset {start}")
            if char != "\\":
                output.append(char)
                continue
            if self.index >= len(self.source):
                break
            escaped = self.source[self.index]
            self.index += 1
            if escaped.isdigit():
                digits = escaped
                for _ in range(2):
                    if self.index < len(self.source) and self.source[self.index].isdigit():
                        digits += self.source[self.index]
                        self.index += 1
                codepoint = int(digits)
                if codepoint > 255:
                    raise SavedVariablesParseError("Lua decimal escape exceeds one byte")
                output.append(chr(codepoint))
            elif escaped in escapes:
                output.append(escapes[escaped])
            else:
                raise SavedVariablesParseError(f"Unsupported escape at offset {self.index - 1}")
        raise SavedVariablesParseError(f"Unterminated string at offset {start}")


class _Parser:
    def __init__(self, source: str, *, expected_root: str, max_depth: int, max_tokens: int) -> None:
        self.lexer = _Lexer(source, max_tokens=max_tokens)
        self.expected_root = expected_root
        self.max_depth = max_depth
        self.current = self.lexer.next()

    def parse(self) -> dict[str, Any]:
        root = self._expect("identifier").value
        if root != self.expected_root:
            raise SavedVariablesParseError(
                f"Unexpected SavedVariables root {root!r}; expected {self.expected_root!r}"
            )
        self._expect("=")
        value = self._value(0)
        if not isinstance(value, dict):
            raise SavedVariablesParseError("SavedVariables root must be a keyed table")
        if self.current.kind == ";":
            self._advance()
        self._expect("eof")
        return value

    def _value(self, depth: int) -> Any:
        if depth > self.max_depth:
            raise SavedVariablesParseError("SavedVariables nesting limit exceeded")
        token = self.current
        if token.kind in {"string", "number"}:
            self._advance()
            return token.value
        if token.kind == "identifier":
            self._advance()
            if token.value == "true":
                return True
            if token.value == "false":
                return False
            if token.value == "nil":
                return None
            raise SavedVariablesParseError(
                f"Executable or symbolic value is forbidden at offset {token.offset}"
            )
        if token.kind == "{":
            return self._table(depth + 1)
        raise SavedVariablesParseError(f"Expected value at offset {token.offset}")

    def _table(self, depth: int) -> Any:
        self._expect("{")
        values: dict[Any, Any] = {}
        next_array_index = 1
        while self.current.kind != "}":
            if self.current.kind == "[":
                self._advance()
                key_token = self.current
                if key_token.kind not in {"string", "number"}:
                    raise SavedVariablesParseError("Only string or numeric table keys are accepted")
                key = key_token.value
                self._advance()
                self._expect("]")
                self._expect("=")
                value = self._value(depth)
            elif (
                self.current.kind == "identifier"
                and self.current.value not in {"true", "false", "nil"}
            ):
                key = self.current.value
                self._advance()
                self._expect("=")
                value = self._value(depth)
            else:
                key = next_array_index
                next_array_index += 1
                value = self._value(depth)
            if key in values:
                raise SavedVariablesParseError(f"Duplicate table key: {key!r}")
            values[key] = value
            if self.current.kind in {",", ";"}:
                self._advance()
                if self.current.kind == "}":
                    break
            elif self.current.kind != "}":
                raise SavedVariablesParseError(
                    f"Expected table separator at offset {self.current.offset}"
                )
        self._expect("}")
        if values and all(isinstance(key, int) and not isinstance(key, bool) for key in values):
            keys = sorted(values)
            if keys == list(range(1, len(keys) + 1)):
                return [values[index] for index in keys]
        return values

    def _expect(self, kind: str) -> _Token:
        if self.current.kind != kind:
            raise SavedVariablesParseError(
                f"Expected {kind!r} at offset {self.current.offset}, got {self.current.kind!r}"
            )
        token = self.current
        if kind != "eof":
            self._advance()
        return token

    def _advance(self) -> None:
        self.current = self.lexer.next()


def parse_saved_variables(
    path: Path,
    *,
    expected_root: str = "PerfectAssassinObserverDB",
    max_bytes: int = 8 * 1024 * 1024,
    max_depth: int = 32,
    max_tokens: int = 250_000,
) -> dict[str, Any]:
    size = path.stat().st_size
    if size > max_bytes:
        raise SavedVariablesParseError(f"SavedVariables file exceeds {max_bytes} bytes")
    source = path.read_text(encoding="utf-8-sig")
    return _Parser(
        source,
        expected_root=expected_root,
        max_depth=max_depth,
        max_tokens=max_tokens,
    ).parse()
