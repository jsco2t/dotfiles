"""Conservative YAML reading and lossless top-level Markdown field editing.

Ordinary TaskNotes YAML is decoded without third-party code. Unsupported values are
opaque and preserved; ambiguous structure fails. No YAML constructors are executed.
"""
from dataclasses import dataclass
import json
import re


class FrontmatterError(ValueError):
    """The note cannot be changed without risking its contents."""


@dataclass(frozen=True)
class RawYaml:
    text: str


def uncomment(text):
    quote, escaped = None, False
    for i, char in enumerate(text):
        if quote:
            if escaped:
                escaped = False
            elif char == "\\" and quote == '"':
                escaped = True
            elif char == quote:
                quote = None
        elif char in "'\"":
            quote = char
        elif char == "#" and (i == 0 or text[i - 1].isspace()):
            return text[:i].rstrip(), text[i:]
    return text.rstrip(), ""


def key_value(text):
    quote, escaped = None, False
    for i, char in enumerate(text):
        if quote:
            if escaped:
                escaped = False
            elif char == "\\" and quote == '"':
                escaped = True
            elif char == quote:
                quote = None
        elif char in "'\"":
            quote = char
        elif char == ":" and (i + 1 == len(text) or text[i + 1].isspace()):
            key = scalar(text[:i].strip())
            if not isinstance(key, str) or not key:
                raise FrontmatterError("Frontmatter keys must be nonempty strings.")
            return key, text[i + 1:].strip()
    raise FrontmatterError("Expected a YAML mapping key followed by ': '.")


def scalar(text):
    text = text.strip()
    if not text:
        return None
    if text.startswith('"'):
        try:
            return json.loads(text)
        except (ValueError, TypeError) as exc:
            raise FrontmatterError("Unsupported quoted YAML value.") from exc
    if text.startswith("'"):
        if len(text) < 2 or not text.endswith("'"):
            raise FrontmatterError("Unterminated single-quoted YAML value.")
        return text[1:-1].replace("''", "'")
    if text.startswith(("*", "&", "!", "%", chr(96))) or text == "<<":
        raise FrontmatterError("YAML anchors, aliases, tags and merge keys are not interpreted.")
    if text in ("null", "Null", "NULL", "~"):
        return None
    if text.lower() in ("true", "false"):
        return text.lower() == "true"
    if re.fullmatch(r"-?(0|[1-9]\d*)", text):
        return int(text)
    if re.fullmatch(r"-?\d+\.\d+([eE][+-]?\d+)?", text):
        return float(text)
    if ": " in text:
        raise FrontmatterError("Ambiguous unquoted YAML scalar.")
    return text


class Flow:
    def __init__(self, text):
        self.text, self.at = text, 0

    def space(self):
        while self.at < len(self.text) and self.text[self.at].isspace():
            self.at += 1

    def value(self):
        self.space()
        if self.at == len(self.text):
            raise FrontmatterError("Missing flow value.")
        char = self.text[self.at]
        if char in "[{":
            self.at += 1
            closing, result = ("]", []) if char == "[" else ("}", {})
            self.space()
            while self.at < len(self.text) and self.text[self.at] != closing:
                if char == "{":
                    start, quote = self.at, None
                    while self.at < len(self.text):
                        c = self.text[self.at]
                        if quote:
                            if c == quote and (self.at == 0 or self.text[self.at - 1] != "\\"):
                                quote = None
                        elif c in "'\"":
                            quote = c
                        elif c == ":":
                            break
                        self.at += 1
                    if self.at == len(self.text):
                        raise FrontmatterError("Unclosed flow mapping.")
                    key = scalar(self.text[start:self.at].strip())
                    if not isinstance(key, str) or key in result:
                        raise FrontmatterError("Invalid or duplicate flow mapping key.")
                    self.at += 1
                    result[key] = self.value()
                else:
                    result.append(self.value())
                self.space()
                if self.at < len(self.text) and self.text[self.at] == ",":
                    self.at += 1
                    self.space()
                elif self.at < len(self.text) and self.text[self.at] != closing:
                    raise FrontmatterError("Expected flow comma or closing delimiter.")
            if self.at >= len(self.text):
                raise FrontmatterError("Unclosed flow value.")
            self.at += 1
            return result
        start = self.at
        if char in "'\"":
            self.at += 1
            while self.at < len(self.text):
                if self.text[self.at] == char:
                    if char == "'" and self.at + 1 < len(self.text) and self.text[self.at + 1] == "'":
                        self.at += 2
                        continue
                    self.at += 1
                    if char == "'" or self.text[self.at - 2] != "\\":
                        return scalar(self.text[start:self.at])
                else:
                    self.at += 1
            raise FrontmatterError("Unclosed quoted flow value.")
        while self.at < len(self.text) and self.text[self.at] not in ",]}":
            self.at += 1
        return scalar(self.text[start:self.at])


def atom(text):
    value, _ = uncomment(text)
    if value.startswith(("[", "{")):
        parser = Flow(value)
        result = parser.value()
        parser.space()
        if parser.at != len(value):
            raise FrontmatterError("Unexpected content after flow value.")
        return result
    return scalar(value)


def block_value(lines):
    if lines:
        first = lines[0].rstrip("\r\n")
        base = len(first) - len(first.lstrip(" "))
        try:
            name, marker = key_value(first.lstrip())
        except FrontmatterError:
            marker = ""
        marker = uncomment(marker)[0]
        if re.fullmatch(r"[|>][+-]?", marker) and all(
            not line.strip() or len(line) - len(line.lstrip(" ")) > base for line in lines[1:]
        ):
            content = lines[1:]
            indent = min((len(line) - len(line.lstrip(" ")) for line in content if line.strip()), default=base + 2)
            value = "\n".join(line.rstrip("\r\n")[indent:] if line.strip() else "" for line in content)
            if marker.startswith(">"):
                value = re.sub(r"(?<=\S)\n(?=\S)", " ", value)
            if marker.endswith("-"):
                value = value.rstrip("\n")
            elif marker.endswith("+"):
                value += "\n" if content else ""
            else:
                value = value.rstrip("\n") + ("\n" if content else "")
            return {name: value}
    useful = [line.rstrip("\r\n") for line in lines if line.strip() and not line.lstrip().startswith("#")]
    if not useful:
        return None
    indentation = min(len(line) - len(line.lstrip(" ")) for line in useful)
    if any("\t" in line[:len(line) - len(line.lstrip())] for line in useful):
        raise FrontmatterError("Tabs in YAML indentation are unsupported.")
    result = [] if useful[0].lstrip().startswith("-") else {}
    index = 0
    while index < len(useful):
        line = useful[index]
        indent = len(line) - len(line.lstrip(" "))
        if indent != indentation:
            raise FrontmatterError("Unexpected YAML indentation.")
        end = index + 1
        while end < len(useful) and len(useful[end]) - len(useful[end].lstrip(" ")) > indentation:
            end += 1
        content = line[indent:]
        children = useful[index + 1:end]
        if isinstance(result, list):
            if not (content == "-" or content.startswith("- ")):
                raise FrontmatterError("Mixed YAML sequence and mapping.")
            rest = content[1:].strip()
            if rest.startswith(("[", "{")):
                value = atom(rest)
            elif not rest:
                value = block_value(children)
            else:
                try:
                    key_value(rest)
                except FrontmatterError:
                    if children:
                        raise FrontmatterError("Unsupported multiline sequence scalar.")
                    value = atom(rest)
                else:
                    value = block_value([" " * (indentation + 2) + rest] + children)
            result.append(value)
        else:
            key, rest = key_value(content)
            if key in result:
                raise FrontmatterError("Duplicate YAML key: " + key)
            if not rest:
                while end < len(useful) and useful[end].startswith(" " * indentation + "-"):
                    end += 1
                    while end < len(useful) and len(useful[end]) - len(useful[end].lstrip(" ")) > indentation:
                        end += 1
                value = block_value(useful[index + 1:end])
            elif re.fullmatch(r"[|>][+-]?", rest):
                trimmed = [s[indentation + 2:] if s.startswith(" " * (indentation + 2)) else s.lstrip() for s in children]
                value = ("\n" if rest[0] == "|" else " ").join(trimmed)
                if not rest.endswith("-"):
                    value += "\n"
            elif children:
                raise FrontmatterError("Unsupported multiline scalar.")
            else:
                value = atom(rest)
            result[key] = value
        index = end
    return result


def encode(value):
    # JSON scalars and flow collections are valid YAML accepted by Obsidian.
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise FrontmatterError("Values must be JSON-compatible, finite YAML data.") from exc


def yaml_field(key, value, newline):
    name = key if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", key) else encode(key)
    if isinstance(value, list) and value:
        return name + ":" + newline + "".join("  - " + encode(item) + newline for item in value)
    return name + ": " + encode(value) + newline


class Document:
    @classmethod
    def parse(cls, text):
        doc = cls()
        doc.original = text
        doc.bom = "\ufeff" if text.startswith("\ufeff") else ""
        text = text[len(doc.bom):]
        doc.newline = "\r\n" if "\r\n" in text else "\n"
        lines = text.splitlines(keepends=True)
        doc.data, doc.fields = {}, {}
        doc.opening, doc.header, doc.closing, doc.body = "", [], "", text
        if not lines or not re.fullmatch(r"---[ \t]*(?:\r?\n)?", lines[0]):
            return doc
        end = next((i for i in range(1, len(lines)) if re.fullmatch(r"(?:---|\.\.\.)[ \t]*(?:\r?\n)?", lines[i])), None)
        if end is None:
            raise FrontmatterError("Unterminated YAML frontmatter; no file was changed.")
        doc.opening, doc.header, doc.closing = lines[0], lines[1:end], lines[end]
        doc.body = "".join(lines[end + 1:])
        starts = []
        depth, quote = [], None
        for i, line in enumerate(doc.header):
            if not depth and quote is None and line.strip() and not line.startswith((" ", "\t", "#", "-")):
                key, _ = key_value(line.rstrip("\r\n"))
                if key in (k for k, _ in starts):
                    raise FrontmatterError("Duplicate YAML key: " + key)
                starts.append((key, i))
            if depth or (line and not line[0].isspace() and ":" in line):
                content = uncomment(line)[0]
                escaped = False
                for char in content:
                    if quote:
                        if escaped:
                            escaped = False
                        elif char == "\\" and quote == '"':
                            escaped = True
                        elif char == quote:
                            quote = None
                    elif char in "'\"":
                        quote = char
                    elif char in "[{":
                        depth.append(char)
                    elif char in "]}":
                        if not depth or (depth.pop(), char) not in (("[", "]"), ("{", "}")):
                            raise FrontmatterError("Mismatched YAML flow delimiter.")
        if depth or quote:
            raise FrontmatterError("Unterminated quoted/flow frontmatter.")
        if not starts and any(line.strip() and not line.lstrip().startswith("#") for line in doc.header):
            raise FrontmatterError("Frontmatter must be a top-level mapping.")
        for position, (key, start) in enumerate(starts):
            stop = starts[position + 1][1] if position + 1 < len(starts) else len(doc.header)
            while stop > start + 1 and (not doc.header[stop - 1].strip() or doc.header[stop - 1].lstrip().startswith("#")):
                stop -= 1
            raw = doc.header[start:stop]
            try:
                parsed = block_value(raw)
                doc.data[key] = parsed[key]
            except (FrontmatterError, KeyError):
                doc.data[key] = RawYaml("".join(raw))
            doc.fields[key] = (start, stop)
        return doc

    def render(self, changes, body=None):
        if not changes and body is None:
            return self.original
        for key, value in changes.items():
            if not isinstance(key, str) or not key or "\n" in key or "\r" in key:
                raise FrontmatterError("Field names must be nonempty, single-line strings.")
            if isinstance(self.data.get(key), RawYaml):
                raise FrontmatterError("Cannot rewrite unsupported YAML field: " + key)
            if value is not None:
                encode(value)
        replacements, additions = {}, []
        for key, value in changes.items():
            if key in self.fields:
                start, stop = self.fields[key]
                replacement = "" if value is None else yaml_field(key, value, self.newline)
                _, comment = uncomment(self.header[start].rstrip("\r\n"))
                if comment and replacement:
                    first, *rest = replacement.splitlines(keepends=True)
                    replacement = first.rstrip("\r\n") + " " + comment + self.newline + "".join(rest)
                replacements[start] = (stop, replacement)
            elif value is not None:
                additions.append(yaml_field(key, value, self.newline))
        out, index = [], 0
        while index < len(self.header):
            if index in replacements:
                stop, replacement = replacements[index]
                out.append(replacement)
                index = stop
            else:
                out.append(self.header[index])
                index += 1
        header = "".join(out) + "".join(additions)
        opening = self.opening or "---" + self.newline
        closing = self.closing or "---" + self.newline
        return self.bom + opening + header + closing + (self.body if body is None else body)
