"""Edit file tool: replace text in files."""

import difflib
import re
from pathlib import Path
from typing import Any, Iterator

from weavbot.agent.tools.base import Tool
from weavbot.utils import resolve_path

# --- Line ending helpers ---


def _normalize_line_endings(text: str) -> str:
    return text.replace("\r\n", "\n")


def _detect_line_ending(content: str) -> str:
    return "\r\n" if "\r\n" in content else "\n"


def _convert_to_line_ending(text: str, ending: str) -> str:
    if ending == "\n":
        return text
    return text.replace("\n", "\r\n")


# --- Levenshtein distance ---


def _levenshtein(a: str, b: str) -> int:
    if not a or not b:
        return max(len(a), len(b))
    rows = len(a) + 1
    cols = len(b) + 1
    matrix = [[0] * cols for _ in range(rows)]
    for i in range(rows):
        matrix[i][0] = i
    for j in range(cols):
        matrix[0][j] = j
    for i in range(1, rows):
        for j in range(1, cols):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            matrix[i][j] = min(
                matrix[i - 1][j] + 1,
                matrix[i][j - 1] + 1,
                matrix[i - 1][j - 1] + cost,
            )
    return matrix[rows - 1][cols - 1]


# --- Replacer strategies ---

SINGLE_CANDIDATE_SIMILARITY_THRESHOLD = 0.0
MULTIPLE_CANDIDATES_SIMILARITY_THRESHOLD = 0.3

Replacer = Iterator[str]


def _simple_replacer(content: str, find: str) -> Replacer:
    yield find


def _line_trimmed_replacer(content: str, find: str) -> Replacer:
    original_lines = content.split("\n")
    search_lines = find.split("\n")
    if search_lines and search_lines[-1] == "":
        search_lines.pop()
    for i in range(len(original_lines) - len(search_lines) + 1):
        matches = all(
            original_lines[i + j].strip() == search_lines[j].strip()
            for j in range(len(search_lines))
        )
        if matches:
            match_start = sum(len(original_lines[k]) + 1 for k in range(i))
            match_end = match_start
            for k in range(len(search_lines)):
                match_end += len(original_lines[i + k])
                if k < len(search_lines) - 1:
                    match_end += 1
            yield content[match_start:match_end]


def _block_anchor_replacer(content: str, find: str) -> Replacer:
    original_lines = content.split("\n")
    search_lines = find.split("\n")
    if len(search_lines) < 3:
        return
    if search_lines and search_lines[-1] == "":
        search_lines.pop()
    first_search = search_lines[0].strip()
    last_search = search_lines[-1].strip()
    search_block_size = len(search_lines)

    candidates: list[tuple[int, int]] = []
    for i in range(len(original_lines)):
        if original_lines[i].strip() != first_search:
            continue
        for j in range(i + 2, len(original_lines)):
            if original_lines[j].strip() == last_search:
                candidates.append((i, j))
                break

    if not candidates:
        return

    def _build_match(start: int, end: int) -> str:
        match_start = sum(len(original_lines[k]) + 1 for k in range(start))
        match_end = match_start
        for k in range(start, end + 1):
            match_end += len(original_lines[k])
            if k < end:
                match_end += 1
        return content[match_start:match_end]

    if len(candidates) == 1:
        start_line, end_line = candidates[0]
        actual_block_size = end_line - start_line + 1
        lines_to_check = min(search_block_size - 2, actual_block_size - 2)
        similarity = 1.0
        if lines_to_check > 0:
            total = 0.0
            count = 0
            for j in range(1, min(search_block_size - 1, actual_block_size - 1) + 1):
                orig_line = original_lines[start_line + j].strip()
                search_line = search_lines[j].strip()
                max_len = max(len(orig_line), len(search_line))
                if max_len == 0:
                    continue
                dist = _levenshtein(orig_line, search_line)
                total += (1 - dist / max_len) / lines_to_check
                count += 1
            if count > 0:
                similarity = total
        if similarity >= SINGLE_CANDIDATE_SIMILARITY_THRESHOLD:
            yield _build_match(start_line, end_line)
        return

    best_match = None
    max_sim = -1.0
    for start_line, end_line in candidates:
        actual_block_size = end_line - start_line + 1
        lines_to_check = min(search_block_size - 2, actual_block_size - 2)
        similarity = 1.0
        if lines_to_check > 0:
            sims = []
            for j in range(1, min(search_block_size - 1, actual_block_size - 1) + 1):
                orig_line = original_lines[start_line + j].strip()
                search_line = search_lines[j].strip()
                max_len = max(len(orig_line), len(search_line))
                if max_len == 0:
                    continue
                dist = _levenshtein(orig_line, search_line)
                sims.append(1 - dist / max_len)
            if sims:
                similarity = sum(sims) / len(sims)
        if similarity > max_sim:
            max_sim = similarity
            best_match = (start_line, end_line)

    if max_sim >= MULTIPLE_CANDIDATES_SIMILARITY_THRESHOLD and best_match:
        yield _build_match(best_match[0], best_match[1])


def _whitespace_normalized_replacer(content: str, find: str) -> Replacer:
    def _norm(t: str) -> str:
        return re.sub(r"\s+", " ", t).strip()

    normalized_find = _norm(find)
    lines = content.split("\n")

    for i, line in enumerate(lines):
        if _norm(line) == normalized_find:
            yield line
        else:
            norm_line = _norm(line)
            if norm_line and normalized_find in norm_line:
                words = find.strip().split()
                if words:
                    pattern = re.escape(words[0])
                    for w in words[1:]:
                        pattern += r"\s+" + re.escape(w)
                    m = re.search(pattern, line)
                    if m:
                        yield m.group(0)

    find_lines = find.split("\n")
    if len(find_lines) > 1:
        for i in range(len(lines) - len(find_lines) + 1):
            block = "\n".join(lines[i : i + len(find_lines)])
            if _norm(block) == normalized_find:
                yield block


def _indentation_flexible_replacer(content: str, find: str) -> Replacer:
    def _remove_indent(text: str) -> str:
        lines = text.split("\n")
        non_empty = [l for l in lines if l.strip()]
        if not non_empty:
            return text
        min_indent = min(len(m.group(1)) if (m := re.match(r"^(\s*)", l)) else 0 for l in non_empty)
        return "\n".join(l[min_indent:] if l.strip() else l for l in lines)

    normalized_find = _remove_indent(find)
    content_lines = content.split("\n")
    find_lines = find.split("\n")

    for i in range(len(content_lines) - len(find_lines) + 1):
        block = "\n".join(content_lines[i : i + len(find_lines)])
        if _remove_indent(block) == normalized_find:
            yield block


def _trimmed_boundary_replacer(content: str, find: str) -> Replacer:
    trimmed = find.strip()
    if trimmed == find:
        return
    if trimmed in content:
        yield trimmed
    lines = content.split("\n")
    find_lines = find.split("\n")
    for i in range(len(lines) - len(find_lines) + 1):
        block = "\n".join(lines[i : i + len(find_lines)])
        if block.strip() == trimmed:
            yield block


_REPLACERS = [
    _simple_replacer,
    _line_trimmed_replacer,
    _block_anchor_replacer,
    _whitespace_normalized_replacer,
    _indentation_flexible_replacer,
    _trimmed_boundary_replacer,
]


def _replace(content: str, old_string: str, new_string: str, replace_all: bool) -> str:
    if old_string == new_string:
        raise ValueError("old_text and new_text are identical; no changes to apply.")

    not_found = True
    for replacer in _REPLACERS:
        candidates = list(replacer(content, old_string))
        for search in candidates:
            idx = content.find(search)
            if idx < 0:
                continue
            not_found = False
            if replace_all:
                return content.replace(search, new_string)
            last_idx = content.rfind(search)
            if idx != last_idx:
                continue
            return content[:idx] + new_string + content[idx + len(search) :]

    if not_found:
        raise ValueError(
            "Could not find old_text in the file. It must match exactly, including "
            "whitespace, indentation, and line endings."
        )
    raise ValueError(
        "Found multiple matches for old_text. Provide more surrounding context to "
        "make the match unique, or use replace_all to change every occurrence."
    )


# --- Tool ---


class EditFileTool(Tool):
    """Tool to edit a file by replacing text."""

    DESCRIPTION = """Performs string replacements in files.

Usage:
- Read the file before editing (recommended).
- When editing text from Read output, preserve the exact indentation as shown. Never include the line number prefix (e.g. "1: ") in old_text or new_text.
- Prefer editing existing files. Only create new files when explicitly required.
- The edit fails if old_text is not found.
- The edit fails if old_text matches multiple times: provide more surrounding context to make it unique, or use replace_all to change every occurrence.
- Use replace_all for renaming variables or replacing across the file."""

    def __init__(self, workspace: Path, allowed_dir: Path | None = None):
        self._workspace = workspace
        self._allowed_dir = allowed_dir

    @property
    def name(self) -> str:
        return "edit_file"

    @property
    def description(self) -> str:
        return self.DESCRIPTION

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to edit"},
                "old_text": {"type": "string", "description": "Text to find and replace"},
                "new_text": {"type": "string", "description": "Replacement text"},
                "replace_all": {
                    "type": "boolean",
                    "description": "Replace all occurrences (default: false)",
                    "default": False,
                },
            },
            "required": ["path", "old_text", "new_text"],
        }

    async def execute(
        self,
        path: str,
        old_text: str,
        new_text: str,
        replace_all: bool = False,
        **kwargs: Any,
    ) -> str:
        try:
            file_path = resolve_path(path, self._workspace, self._allowed_dir)
            if file_path.exists() and file_path.is_dir():
                return f"Error: Path is a directory, not a file: {path}"

            if old_text == new_text:
                return "Error: old_text and new_text are identical; no changes to apply."

            if old_text == "":
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(new_text, encoding="utf-8")
                return f"Successfully wrote to {file_path}"

            if not file_path.exists():
                return f"Error: File not found: {path}"

            content = file_path.read_text(encoding="utf-8")
            ending = _detect_line_ending(content)
            old_norm = _convert_to_line_ending(_normalize_line_endings(old_text), ending)
            new_norm = _convert_to_line_ending(_normalize_line_endings(new_text), ending)

            try:
                new_content = _replace(content, old_norm, new_norm, replace_all)
            except ValueError as e:
                if "Could not find" in str(e):
                    return self._not_found_message(old_text, content, path)
                if "multiple matches" in str(e).lower():
                    count = content.count(old_norm)
                    return (
                        f"Error: old_text appears {count} times. Provide more surrounding "
                        "context to make it unique, or use replace_all to change every occurrence."
                    )
                return f"Error: {e}"

            file_path.write_text(new_content, encoding="utf-8")
            return f"Successfully edited {file_path}"
        except PermissionError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error editing file: {str(e)}"

    @staticmethod
    def _not_found_message(old_text: str, content: str, path: str) -> str:
        """Build a helpful error when old_text is not found."""
        lines = content.splitlines(keepends=True)
        old_lines = old_text.splitlines(keepends=True)
        window = len(old_lines)

        best_ratio, best_start = 0.0, 0
        for i in range(max(1, len(lines) - window + 1)):
            ratio = difflib.SequenceMatcher(None, old_lines, lines[i : i + window]).ratio()
            if ratio > best_ratio:
                best_ratio, best_start = ratio, i

        if best_ratio > 0.5:
            diff = "\n".join(
                difflib.unified_diff(
                    old_lines,
                    lines[best_start : best_start + window],
                    fromfile="old_text (provided)",
                    tofile=f"{path} (actual, line {best_start + 1})",
                    lineterm="",
                )
            )
            return (
                f"Error: old_text not found in {path}.\n"
                f"Best match ({best_ratio:.0%} similar) at line {best_start + 1}:\n{diff}"
            )
        return (
            f"Error: old_text not found in {path}. No similar text found. Verify the file content."
        )
