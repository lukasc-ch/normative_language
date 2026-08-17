#!/usr/bin/env python3
"""Reference toolchain for NDF (Normative Description Format) clause trees.

Implements the minimum-viable toolchain functions specified in
``normative_language.md`` §8 that operate purely on the clause tree:

    ndf new-id PREFIX   allocate the next free clause number for a prefix
    ndf check           lint the tree (refs, IDs, keywords, layers, ...)
    ndf trace ID        print the refinement subtree rooted at ID
    ndf coverage        contract/verification coverage and hole counts
    ndf status          open Q-* items grouped by the clauses they block
    ndf options         kind=option clauses and their sweep metadata

Not (yet) implemented from the §8 table: ``log``, ``diff``, ``deps``,
``export``, ``publish``, ``ingest``, and the ``models/`` runner.

Everything operates on plain files; no server, no database, no third-party
dependencies. The clause grammar follows Appendix A of the spec:
``{#ID}`` heading anchors, one or more ``<!-- ndf: key=value ... -->``
metadata comments, ``[[ID]]`` cross-references, ``⟨TBD: ...⟩`` /
``⟨DSE: ...⟩`` markers, and an ``ndf.yaml`` manifest per tree.

The tree root is resolved from ``--root``, then ``$NDF_ROOT``, then by
walking upward from the current directory looking for ``ndf.yaml``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

__version__ = "0.1.0"

HEADING_RE = re.compile(r"^(#{1,6})\s+(?P<title>.*?)\s*\{#(?P<id>[A-Za-z0-9-]+)\}\s*$")
META_RE = re.compile(r"^<!--\s*ndf:\s*(?P<body>.*?)\s*-->\s*$")
REF_RE = re.compile(r"\[\[(?P<id>[A-Za-z0-9-]+)(?:\s*\|[^\]]*)?\]\]")
ID_NUM_RE = re.compile(r"^(?P<stem>[A-Za-z][A-Za-z0-9-]*)-(?P<num>\d+)$")
FENCE_RE = re.compile(r"^(```|~~~)")

# Edge-typed metadata keys whose values are comma-separated clause IDs
# (Appendix A plus the tree-observed blocks/blocks-by/affects/superseded-by).
EDGE_KEYS = (
    "refines",
    "verifies",
    "blocks",
    "blocks-by",
    "affects",
    "depends-on",
    "conflicts-with",
    "superseded-by",
)
# origin, derived-from, and model values are source-document paths or
# anchors, not clause IDs; they are not checked as edges.

RFC2119_RE = re.compile(r"\b(MUST NOT|MUST|SHOULD NOT|SHOULD|MAY)\b")
INFO_KEYWORD_RE = re.compile(r"\b(MUST|SHALL)\b")

DEFAULT_BAN_WORDS = ["appropriately", "as needed", "etc.", "handle", "support"]


@dataclass
class Clause:
    id: str
    title: str
    file: Path
    line: int
    meta: dict[str, str] = field(default_factory=dict)
    body: str = ""
    refs: list[str] = field(default_factory=list)
    has_meta: bool = False

    @property
    def kind(self) -> str:
        return self.meta.get("kind", "")

    @property
    def level(self) -> str:
        return self.meta.get("level", "")

    @property
    def layer(self) -> str:
        return self.meta.get("layer", "")

    @property
    def status(self) -> str:
        return self.meta.get("status", "")

    def edge(self, key: str) -> list[str]:
        raw = self.meta.get(key, "")
        return [item for item in (part.strip() for part in raw.split(",")) if item]

    def tbd_count(self) -> int:
        return len(re.findall(r"[⟨<]TBD:", self.body))


@dataclass
class Manifest:
    prefixes: list[str] = field(default_factory=list)
    ban_words: list[str] = field(default_factory=lambda: list(DEFAULT_BAN_WORDS))
    require_keyword_in_req: bool = True
    require_author: bool = False


@dataclass
class Finding:
    severity: str  # "error" | "warning"
    code: str
    clause: str
    file: str
    line: int
    message: str


@dataclass
class Tree:
    root: Path
    clauses: dict[str, Clause] = field(default_factory=dict)
    duplicates: list[tuple[Clause, Clause]] = field(default_factory=list)
    manifest: Manifest = field(default_factory=Manifest)

    def children_of(self, clause_id: str) -> list[Clause]:
        return sorted(
            (c for c in self.clauses.values() if clause_id in c.edge("refines")),
            key=lambda c: (str(c.file), c.line),
        )

    def verifiers_of(self, clause_id: str) -> list[Clause]:
        return sorted(
            (
                c
                for c in self.clauses.values()
                if c.kind == "verif" and clause_id in c.edge("verifies")
            ),
            key=lambda c: c.id,
        )

    def blockers_of(self, clause: Clause) -> list[str]:
        blockers = set(clause.edge("blocks-by"))
        for other in self.clauses.values():
            if other.kind == "question" and other.status == "open":
                if clause.id in other.edge("blocks"):
                    blockers.add(other.id)
        return sorted(blockers)


def _split_inline_list(raw: str) -> list[str]:
    return [item.strip() for item in raw.strip().strip("[]").split(",") if item.strip()]


def parse_manifest(path: Path) -> Manifest:
    """Extract id-prefixes and lint settings from ndf.yaml without PyYAML.

    Supports both the inline form (``id-prefixes: [A, B, C]``, as in the
    spec's Appendix C) and the block-list form (one ``- A`` per line).
    """
    manifest = Manifest()
    if not path.is_file():
        return manifest
    section = ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if not line.startswith(" "):
            key, _, rest = line.partition(":")
            section = key.strip()
            rest = rest.strip()
            if section == "id-prefixes" and rest:
                manifest.prefixes.extend(_split_inline_list(rest))
            continue
        stripped = line.strip()
        if section == "id-prefixes" and stripped.startswith("- "):
            manifest.prefixes.append(stripped[2:].strip())
        elif section == "lint":
            if stripped.startswith("ban-words:"):
                words = _split_inline_list(stripped.split(":", 1)[1])
                if words:
                    manifest.ban_words = words
            elif stripped.startswith("require-keyword-in-req:"):
                value = stripped.split(":", 1)[1].strip().lower()
                manifest.require_keyword_in_req = value != "false"
            elif stripped.startswith("require-author:"):
                value = stripped.split(":", 1)[1].strip().lower()
                manifest.require_author = value == "true"
    return manifest


def parse_meta(body: str) -> dict[str, str]:
    """Parse `key=value` tokens; values may themselves contain '='."""
    meta: dict[str, str] = {}
    for token in body.split():
        if "=" in token:
            key, value = token.split("=", 1)
            meta[key] = value
    return meta


def strip_code_fences(text: str) -> str:
    """Drop fenced code blocks so reference/lint checks see prose only."""
    out: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if FENCE_RE.match(line.strip()):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append(line)
    return "\n".join(out)


def load_tree(root: Path) -> Tree:
    tree = Tree(root=root, manifest=parse_manifest(root / "ndf.yaml"))
    for path in sorted(root.rglob("*.md")):
        lines = path.read_text(encoding="utf-8").splitlines()
        anchors: list[tuple[int, str, str]] = []  # (line index, id, title)
        for idx, line in enumerate(lines):
            match = HEADING_RE.match(line)
            if match:
                anchors.append((idx, match.group("id"), match.group("title")))
        for pos, (idx, clause_id, title) in enumerate(anchors):
            end = anchors[pos + 1][0] if pos + 1 < len(anchors) else len(lines)
            clause = Clause(id=clause_id, title=title, file=path, line=idx + 1)
            # Metadata: one or more consecutive ndf comments directly after
            # the heading (blank lines allowed before the first).
            for follow in lines[idx + 1 : end]:
                stripped = follow.strip()
                if not stripped and not clause.has_meta:
                    continue
                meta_match = META_RE.match(stripped)
                if meta_match:
                    clause.meta.update(parse_meta(meta_match.group("body")))
                    clause.has_meta = True
                    continue
                break
            clause.body = "\n".join(lines[idx + 1 : end])
            # Collect [[ID]] refs from prose only; fenced code blocks may
            # contain illustrative references.
            clause.refs = [
                m.group("id")
                for m in REF_RE.finditer(strip_code_fences(clause.body))
            ]
            if clause_id in tree.clauses:
                tree.duplicates.append((tree.clauses[clause_id], clause))
            else:
                tree.clauses[clause_id] = clause
    return tree


def relpath(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def resolve_root(cli_root: Path | None) -> Path | None:
    """--root, then $NDF_ROOT, then walk up from cwd looking for ndf.yaml."""
    if cli_root is not None:
        return cli_root.expanduser().resolve()
    env = os.environ.get("NDF_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    current = Path.cwd()
    for candidate in (current, *current.parents):
        if (candidate / "ndf.yaml").is_file():
            return candidate
    return None


# ---------------------------------------------------------------------------
# check


def reaches_layer(tree: Tree, clause: Clause, layer: str) -> bool:
    """True if following refines= edges upward reaches a clause of `layer`."""
    seen: set[str] = set()
    frontier = [clause]
    while frontier:
        current = frontier.pop()
        for parent_id in current.edge("refines"):
            if parent_id in seen or parent_id not in tree.clauses:
                continue
            seen.add(parent_id)
            parent = tree.clauses[parent_id]
            if parent.layer == layer:
                return True
            frontier.append(parent)
    return False


def run_check(tree: Tree) -> list[Finding]:
    findings: list[Finding] = []
    manifest = tree.manifest

    def add(severity: str, code: str, clause: Clause, message: str) -> None:
        findings.append(
            Finding(
                severity=severity,
                code=code,
                clause=clause.id,
                file=relpath(clause.file, tree.root),
                line=clause.line,
                message=message,
            )
        )

    for first, second in tree.duplicates:
        findings.append(
            Finding(
                severity="error",
                code="duplicate-id",
                clause=second.id,
                file=relpath(second.file, tree.root),
                line=second.line,
                message=(
                    f"duplicate ID also defined at "
                    f"{relpath(first.file, tree.root)}:{first.line}"
                ),
            )
        )

    known = set(tree.clauses)
    for clause in tree.clauses.values():
        prose = strip_code_fences(clause.body)

        # Dangling [[ID]] references.
        for ref in clause.refs:
            if ref not in known:
                add("error", "dangling-ref", clause, f"[[{ref}]] does not resolve")

        # Dangling edge targets.
        for key in EDGE_KEYS:
            for target in clause.edge(key):
                if target not in known:
                    add(
                        "error",
                        "dangling-edge",
                        clause,
                        f"{key}={target} does not resolve",
                    )

        # Metadata presence and shape.
        if not clause.has_meta:
            add("warning", "missing-meta", clause, "no <!-- ndf: ... --> metadata")
        elif not clause.kind:
            add("warning", "missing-kind", clause, "metadata has no kind=")

        # Keyword discipline.
        if clause.kind == "req" and manifest.require_keyword_in_req:
            if not RFC2119_RE.search(prose):
                add(
                    "error",
                    "req-no-keyword",
                    clause,
                    "kind=req clause has no MUST/SHOULD/MAY keyword",
                )
        if clause.kind == "info" and INFO_KEYWORD_RE.search(prose):
            add(
                "error",
                "info-keyword",
                clause,
                "kind=info clause contains MUST/SHALL",
            )

        # Layer parenting, following refines= chains transitively (trees
        # legitimately chain L2 -> L2 -> L1). Definitional and process
        # clauses (def/arch at L1, def at L2, question/decision anywhere)
        # are exempt, matching observed tree usage.
        exempt = clause.kind in ("question", "decision")
        if clause.layer == "L2" and clause.kind != "def" and not exempt:
            if not reaches_layer(tree, clause, "L1"):
                add(
                    "error",
                    "layer-l2-parent",
                    clause,
                    "layer=L2 clause does not reach an L1 clause via refines=",
                )
        elif (
            clause.layer == "L1"
            and clause.kind not in ("arch", "def", "constraint")
            and not exempt
        ):
            if not reaches_layer(tree, clause, "L0"):
                add(
                    "warning",
                    "layer-l1-parent",
                    clause,
                    "layer=L1 clause does not reach an L0 clause via refines=",
                )

        # Ban-words in must-level clauses. Judgment-dependent (e.g. "support"
        # without an object), so reported as warnings.
        if clause.level == "must":
            lowered = prose.lower()
            for word in manifest.ban_words:
                if re.search(rf"(?<![a-z]){re.escape(word.lower())}(?![a-z])", lowered):
                    add(
                        "warning",
                        "ban-word",
                        clause,
                        f'ban-word "{word}" in level=must clause',
                    )

        # Author requirement on decision/question clauses; opt-in via
        # `lint: require-author: true` (the base grammar does not require
        # author=, but project conventions may).
        if (
            manifest.require_author
            and clause.kind in ("decision", "question")
            and "author" not in clause.meta
        ):
            add(
                "warning",
                "missing-author",
                clause,
                f"kind={clause.kind} clause has no author=",
            )

        # Prefix registration.
        if manifest.prefixes:
            prefix = clause.id.split("-", 1)[0]
            if prefix not in manifest.prefixes:
                add(
                    "warning",
                    "unregistered-prefix",
                    clause,
                    f'ID prefix "{prefix}" is not registered in ndf.yaml',
                )

    findings.sort(key=lambda f: (f.severity != "error", f.file, f.line))
    return findings


def cmd_check(tree: Tree, args: argparse.Namespace) -> int:
    findings = run_check(tree)
    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]
    if args.json:
        print(
            json.dumps(
                {
                    "root": str(tree.root),
                    "clauses": len(tree.clauses),
                    "errors": len(errors),
                    "warnings": len(warnings),
                    "findings": [vars(f) for f in findings],
                },
                indent=2,
                default=str,
            )
        )
    else:
        for f in findings:
            print(
                f"{f.severity.upper():7s} {f.code:20s} {f.clause:24s} "
                f"{f.file}:{f.line}  {f.message}"
            )
        print(
            f"\nndf check: {len(tree.clauses)} clauses, "
            f"{len(errors)} errors, {len(warnings)} warnings"
        )
    if errors:
        return 1
    if warnings and args.strict:
        return 1
    return 0


# ---------------------------------------------------------------------------
# new-id


def cmd_new_id(tree: Tree, args: argparse.Namespace) -> int:
    prefix = args.prefix.rstrip("-")
    numbers: list[tuple[int, int]] = []  # (value, digits)
    for clause_id in tree.clauses:
        match = ID_NUM_RE.match(clause_id)
        if match and match.group("stem") == prefix:
            numbers.append((int(match.group("num")), len(match.group("num"))))
    if numbers:
        next_num = max(value for value, _ in numbers) + 1
        width = max(digits for _, digits in numbers)
    else:
        next_num = 1
        width = 3
    print(f"{prefix}-{next_num:0{width}d}")
    return 0


# ---------------------------------------------------------------------------
# trace


def clause_annotations(tree: Tree, clause: Clause) -> str:
    """Render the parenthesized state and verification suffix for trace."""
    parts = [clause.layer or "?"]
    if clause.status and clause.status not in ("stable",):
        parts.append(clause.status)
    tbd = clause.tbd_count()
    if tbd:
        parts.append(f"{tbd} TBD")
    blockers = tree.blockers_of(clause)
    if blockers:
        parts.append("blocked by " + ", ".join(blockers))
    label = f"({', '.join(parts)})"

    verifiers = tree.verifiers_of(clause.id)
    if verifiers:
        return f"{label} ── verified by " + ", ".join(v.id for v in verifiers)
    if clause.layer == "L1" and clause.level == "must" and clause.kind == "req":
        return f"{label}   ⚠ unverified"
    return label


def cmd_trace(tree: Tree, args: argparse.Namespace) -> int:
    clause_id = args.id
    if clause_id not in tree.clauses:
        print(f"error: unknown clause ID {clause_id}", file=sys.stderr)
        return 1

    seen: set[str] = set()

    def emit(cid: str, prefix: str, connector: str) -> None:
        clause = tree.clauses[cid]
        cycle = cid in seen
        line = f"{prefix}{connector}{cid} {clause_annotations(tree, clause)}"
        if cycle:
            line += " (cycle)"
        print(line)
        if cycle:
            return
        seen.add(cid)
        children = tree.children_of(cid)
        child_prefix = prefix + ("│   " if connector == "├── " else "    ")
        if connector == "":
            child_prefix = ""
        for i, child in enumerate(children):
            last = i == len(children) - 1
            emit(child.id, child_prefix, "└── " if last else "├── ")

    emit(clause_id, "", "")
    return 0


# ---------------------------------------------------------------------------
# coverage


def build_coverage(tree: Tree) -> dict:
    clauses = list(tree.clauses.values())
    l1_must = [c for c in clauses if c.layer == "L1" and c.level == "must"]
    verif = [c for c in clauses if c.kind == "verif"]
    verified_ids: set[str] = set()
    for clause in verif:
        verified_ids.update(clause.edge("verifies"))
    l1_verified = [c for c in l1_must if c.id in verified_ids]

    tbd_markers = sum(c.tbd_count() for c in clauses)
    dse_markers = sum(len(re.findall(r"[⟨<]DSE:", c.body)) for c in clauses)
    conflicts = sum(len(c.edge("conflicts-with")) for c in clauses)

    options = [c for c in clauses if c.kind == "option"]
    open_options = [c for c in options if c.status != "stable" or c.level == "tbd"]
    questions = [c for c in clauses if c.kind == "question"]
    open_questions = [c for c in questions if c.status == "open"]

    by_layer: dict[str, int] = {}
    for clause in clauses:
        key = clause.layer or "(none)"
        by_layer[key] = by_layer.get(key, 0) + 1

    return {
        "clauses": len(clauses),
        "by_layer": dict(sorted(by_layer.items())),
        "l1_must": len(l1_must),
        "l1_must_verified": len(l1_verified),
        "verif_clauses": len(verif),
        "verif_draft": len([c for c in verif if c.status == "draft"]),
        "tbd_level": len([c for c in clauses if c.level == "tbd"]),
        "tbd_markers": tbd_markers,
        "dse_markers": dse_markers,
        "conflicts": conflicts,
        "options": len(options),
        "options_open": len(open_options),
        "questions": len(questions),
        "questions_open": len(open_questions),
        "unverified_l1_must": sorted(
            c.id for c in l1_must if c.id not in verified_ids
        ),
    }


def cmd_coverage(tree: Tree, args: argparse.Namespace) -> int:
    cov = build_coverage(tree)
    if args.json:
        print(json.dumps(cov, indent=2))
        return 0
    print(f"clauses:              {cov['clauses']}")
    print(
        "by layer:             "
        + ", ".join(f"{k}={v}" for k, v in cov["by_layer"].items())
    )
    print(f"L1 must contracts:    {cov['l1_must']}")
    print(
        f"  verifies-linked:    {cov['l1_must_verified']} "
        f"({cov['l1_must'] - cov['l1_must_verified']} unverified)"
    )
    if cov["unverified_l1_must"]:
        print(
            "  unverified:         "
            + ", ".join(cov["unverified_l1_must"][:8])
            + (" ..." if len(cov["unverified_l1_must"]) > 8 else "")
        )
    print(
        f"verif clauses:        {cov['verif_clauses']} "
        f"({cov['verif_draft']} draft)"
    )
    print(f"level=tbd clauses:    {cov['tbd_level']}")
    print(f"TBD markers:          {cov['tbd_markers']}")
    print(f"DSE markers:          {cov['dse_markers']}")
    print(f"conflicts:            {cov['conflicts']}")
    print(f"option clauses:       {cov['options']} ({cov['options_open']} open)")
    print(f"open questions:       {cov['questions_open']} of {cov['questions']}")
    return 0


# ---------------------------------------------------------------------------
# status


def cmd_status(tree: Tree, args: argparse.Namespace) -> int:
    questions = [
        c
        for c in tree.clauses.values()
        if c.kind == "question" and c.status == "open"
    ]
    closed = [
        c
        for c in tree.clauses.values()
        if c.kind == "question" and c.status != "open"
    ]
    grouped: dict[str, list[Clause]] = {}
    for clause in questions:
        targets = clause.edge("blocks") or ["(no blocks= declared)"]
        for target in targets:
            grouped.setdefault(target, []).append(clause)
    for target in sorted(grouped):
        print(f"{target}:")
        for clause in sorted(grouped[target], key=lambda c: c.id):
            print(f"  {clause.id}  {clause.title}")
    print(f"\nopen questions: {len(questions)}  (resolved/closed: {len(closed)})")
    return 0


# ---------------------------------------------------------------------------
# options


def cmd_options(tree: Tree, args: argparse.Namespace) -> int:
    options = sorted(
        (c for c in tree.clauses.values() if c.kind == "option"),
        key=lambda c: c.id,
    )
    if not options:
        print("no kind=option clauses found")
        return 0
    for clause in options:
        state = (
            "closed"
            if clause.status == "stable" and clause.level == "must"
            else "open"
        )
        print(f"{clause.id}  [{state}]  {clause.title}")
        print(f"  file:         {relpath(clause.file, tree.root)}:{clause.line}")
        for key in ("default", "explore", "unit", "couples-with", "status", "level"):
            value = clause.meta.get(key, "")
            print(f"  {key + ':':13s} {value if value else '(not set)'}")
    return 0


# ---------------------------------------------------------------------------
# main


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ndf",
        description="Reference toolchain for NDF clause trees.",
    )
    parser.add_argument(
        "--version", action="version", version=f"ndf {__version__}"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help=(
            "NDF tree root (default: $NDF_ROOT, else the nearest ancestor "
            "of the current directory containing ndf.yaml)"
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_new_id = sub.add_parser("new-id", help="allocate the next free clause ID")
    p_new_id.add_argument("prefix", help="ID stem, e.g. ROB or ROB-ENTRY")
    p_new_id.set_defaults(func=cmd_new_id)

    p_check = sub.add_parser("check", help="lint the NDF tree")
    p_check.add_argument("--json", action="store_true", help="JSON report")
    p_check.add_argument(
        "--strict", action="store_true", help="warnings also fail the run"
    )
    p_check.set_defaults(func=cmd_check)

    p_trace = sub.add_parser("trace", help="print the refinement subtree of ID")
    p_trace.add_argument("id", help="clause ID to trace")
    p_trace.set_defaults(func=cmd_trace)

    p_coverage = sub.add_parser("coverage", help="coverage and hole counts")
    p_coverage.add_argument("--json", action="store_true", help="JSON report")
    p_coverage.set_defaults(func=cmd_coverage)

    p_status = sub.add_parser("status", help="open questions by blocked clause")
    p_status.set_defaults(func=cmd_status)

    p_options = sub.add_parser("options", help="list kind=option clauses")
    p_options.set_defaults(func=cmd_options)

    args = parser.parse_args(argv)
    root = resolve_root(args.root)
    if root is None:
        print(
            "error: no NDF root found — pass --root, set $NDF_ROOT, or run "
            "inside a tree containing ndf.yaml",
            file=sys.stderr,
        )
        return 2
    if not root.is_dir():
        print(f"error: NDF root not found: {root}", file=sys.stderr)
        return 2
    tree = load_tree(root)
    return args.func(tree, args)


if __name__ == "__main__":
    sys.exit(main())
