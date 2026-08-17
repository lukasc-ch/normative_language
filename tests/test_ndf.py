import io
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

import ndf as NDF  # noqa: E402

CHRONO = REPO / "examples" / "chrono"

MANIFEST = """\
id-prefixes:
  - CHR      # charter
  - ROB      # reorder buffer
  - VER      # verification
  - D        # decisions
  - Q        # open questions

lint:
  ban-words: [appropriately, as needed, etc., handle, support]
  require-keyword-in-req: true
  require-author: true
"""


def write_tree(tmp_path: Path, files: dict[str, str], manifest: str = MANIFEST) -> Path:
    root = tmp_path / "ndf"
    root.mkdir(parents=True)
    (root / "ndf.yaml").write_text(manifest, encoding="utf-8")
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


def clean_tree(tmp_path: Path) -> Path:
    return write_tree(
        tmp_path,
        {
            "00-charter/charter.md": (
                "# Charter\n\n"
                "## Intent {#CHR-001}\n"
                "<!-- ndf: kind=arch level=must layer=L0 status=stable -->\n\n"
                "The core exists. See [[ROB-001]].\n"
            ),
            "20-behavior/rob.md": (
                "# ROB\n\n"
                "## Unified ROB {#ROB-001}\n"
                "<!-- ndf: kind=req level=must layer=L1 status=stable"
                " refines=CHR-001 -->\n\n"
                "The core MUST provide one unified ROB.\n\n"
                "## ROB entry {#ROB-ENTRY-001}\n"
                "<!-- ndf: kind=req level=must layer=L2 status=stable"
                " refines=ROB-001 -->\n\n"
                "Each entry MUST record the old physical register.\n"
            ),
            "50-verification/acceptance.md": (
                "# Acceptance\n\n"
                "## ROB conformance {#VER-ROB-001}\n"
                "<!-- ndf: kind=verif level=must layer=L3 status=draft"
                " verifies=ROB-001 -->\n\n"
                "A trace replay MUST confirm in-order commit.\n"
            ),
            "decisions/D-0001.md": (
                "# D-0001: Unified ROB {#D-0001}\n"
                "<!-- ndf: kind=decision date=2026-01-01 author=alice"
                " affects=ROB-001 -->\n\n"
                "One ROB, not two.\n"
            ),
            "open/Q-001.md": (
                "# Q-001: ROB size {#Q-001}\n"
                "<!-- ndf: kind=question status=open author=bob"
                " blocks=ROB-001 -->\n\n"
                "Is the size right? ⟨TBD: model it⟩\n"
            ),
        },
    )


def check_codes(root: Path) -> dict[str, str]:
    tree = NDF.load_tree(root)
    return {f.code: f.severity for f in NDF.run_check(tree)}


# ---------------------------------------------------------------------------
# synthetic-tree checks


def test_clean_tree_has_no_findings(tmp_path: Path) -> None:
    tree = NDF.load_tree(clean_tree(tmp_path))
    assert len(tree.clauses) == 6
    assert NDF.run_check(tree) == []


def test_manifest_block_list_and_lint(tmp_path: Path) -> None:
    root = clean_tree(tmp_path)
    manifest = NDF.parse_manifest(root / "ndf.yaml")
    assert manifest.prefixes == ["CHR", "ROB", "VER", "D", "Q"]
    assert manifest.ban_words == [
        "appropriately",
        "as needed",
        "etc.",
        "handle",
        "support",
    ]
    assert manifest.require_keyword_in_req is True
    assert manifest.require_author is True


def test_manifest_inline_list(tmp_path: Path) -> None:
    path = tmp_path / "ndf.yaml"
    path.write_text(
        "project: chrono\n"
        "id-prefixes: [CHR, DEF, CNT, CTL, DSP, PIN, CON, VER, D, Q]\n"
        "layers: {L0: intent, L1: contract, L2: mechanism, L3: executable}\n",
        encoding="utf-8",
    )
    manifest = NDF.parse_manifest(path)
    assert manifest.prefixes == [
        "CHR", "DEF", "CNT", "CTL", "DSP", "PIN", "CON", "VER", "D", "Q",
    ]
    assert manifest.require_author is False  # opt-in


def test_dangling_ref_is_error(tmp_path: Path) -> None:
    root = write_tree(
        tmp_path,
        {
            "a.md": (
                "## A {#ROB-001}\n"
                "<!-- ndf: kind=info status=stable -->\n\n"
                "See [[ROB-MISSING-001]].\n"
            )
        },
    )
    assert check_codes(root).get("dangling-ref") == "error"


def test_ref_inside_code_fence_is_ignored(tmp_path: Path) -> None:
    root = write_tree(
        tmp_path,
        {
            "a.md": (
                "## A {#ROB-001}\n"
                "<!-- ndf: kind=info status=stable -->\n\n"
                "```text\nillustrative [[ROB-MISSING-001]]\n```\n"
            )
        },
    )
    assert "dangling-ref" not in check_codes(root)


def test_dangling_edge_and_blocks_by(tmp_path: Path) -> None:
    root = write_tree(
        tmp_path,
        {
            "a.md": (
                "## A {#ROB-001}\n"
                "<!-- ndf: kind=info status=stable refines=CHR-MISSING-001"
                " blocks-by=Q-MISSING-001 -->\n\n"
                "Body.\n"
            )
        },
    )
    tree = NDF.load_tree(root)
    targets = {
        f.message for f in NDF.run_check(tree) if f.code == "dangling-edge"
    }
    assert targets == {
        "refines=CHR-MISSING-001 does not resolve",
        "blocks-by=Q-MISSING-001 does not resolve",
    }


def test_duplicate_id_is_error(tmp_path: Path) -> None:
    root = write_tree(
        tmp_path,
        {
            "a.md": (
                "## A {#ROB-001}\n<!-- ndf: kind=info status=stable -->\n\nX.\n"
                "## B {#ROB-001}\n<!-- ndf: kind=info status=stable -->\n\nY.\n"
            )
        },
    )
    assert check_codes(root).get("duplicate-id") == "error"


def test_req_without_keyword_is_error(tmp_path: Path) -> None:
    root = write_tree(
        tmp_path,
        {
            "a.md": (
                "## A {#ROB-001}\n"
                "<!-- ndf: kind=req level=should layer=L1 status=stable -->\n\n"
                "The ROB tracks instructions.\n"
            )
        },
    )
    assert check_codes(root).get("req-no-keyword") == "error"


def test_info_with_keyword_is_error(tmp_path: Path) -> None:
    root = write_tree(
        tmp_path,
        {
            "a.md": (
                "## A {#ROB-001}\n"
                "<!-- ndf: kind=info status=stable -->\n\n"
                "The ROB MUST do things.\n"
            )
        },
    )
    assert check_codes(root).get("info-keyword") == "error"


def test_l2_without_l1_ancestor_is_error(tmp_path: Path) -> None:
    root = write_tree(
        tmp_path,
        {
            "a.md": (
                "## A {#ROB-001}\n"
                "<!-- ndf: kind=req level=must layer=L2 status=stable -->\n\n"
                "It MUST work.\n"
            )
        },
    )
    assert check_codes(root).get("layer-l2-parent") == "error"


def test_l2_reaching_l1_transitively_is_clean(tmp_path: Path) -> None:
    root = write_tree(
        tmp_path,
        {
            "a.md": (
                "## Contract {#ROB-001}\n"
                "<!-- ndf: kind=req level=must layer=L1 status=stable -->\n\n"
                "It MUST exist.\n\n"
                "## Mechanism {#ROB-ENTRY-001}\n"
                "<!-- ndf: kind=req level=must layer=L2 status=stable"
                " refines=ROB-001 -->\n\n"
                "It MUST have entries.\n\n"
                "## Sub-mechanism {#ROB-FIELD-001}\n"
                "<!-- ndf: kind=req level=must layer=L2 status=stable"
                " refines=ROB-ENTRY-001 -->\n\n"
                "Entries MUST have fields.\n"
            )
        },
    )
    assert "layer-l2-parent" not in check_codes(root)


def test_ban_word_in_must_clause_is_warning(tmp_path: Path) -> None:
    root = write_tree(
        tmp_path,
        {
            "a.md": (
                "## A {#ROB-001}\n"
                "<!-- ndf: kind=req level=must layer=L1 status=stable -->\n\n"
                "The ROB MUST respond appropriately.\n"
            )
        },
    )
    assert check_codes(root).get("ban-word") == "warning"


def test_missing_author_is_opt_in(tmp_path: Path) -> None:
    files = {
        "decisions/D-0001.md": (
            "# D-0001: X {#D-0001}\n"
            "<!-- ndf: kind=decision date=2026-01-01 -->\n\n"
            "Because.\n"
        )
    }
    with_lint = write_tree(tmp_path / "a", files)
    assert check_codes(with_lint).get("missing-author") == "warning"
    without_lint = write_tree(
        tmp_path / "b", files, manifest="id-prefixes: [D]\n"
    )
    assert "missing-author" not in check_codes(without_lint)


def test_unregistered_prefix_is_warning(tmp_path: Path) -> None:
    root = write_tree(
        tmp_path,
        {
            "a.md": (
                "## A {#ZZZ-001}\n"
                "<!-- ndf: kind=info status=stable -->\n\n"
                "Body.\n"
            )
        },
    )
    assert check_codes(root).get("unregistered-prefix") == "warning"


def test_metadata_value_containing_equals_is_parsed() -> None:
    meta = NDF.parse_meta("kind=req status=superseded-by=MEM-TLSU-002")
    assert meta["status"] == "superseded-by=MEM-TLSU-002"


def test_multiple_meta_comments_are_an_error(tmp_path: Path) -> None:
    root = write_tree(
        tmp_path,
        {
            "a.md": (
                "## A {#ROB-001}\n"
                "<!-- ndf: kind=req level=must layer=L1 status=draft -->\n"
                "<!-- ndf: blocks-by=Q-001 -->\n\n"
                "It MUST work.\n"
            ),
            "open/Q-001.md": (
                "# Q-001: open item {#Q-001}\n"
                "<!-- ndf: kind=question status=open author=bob"
                " blocks=ROB-001 -->\n\n"
                "Undecided.\n"
            ),
        },
    )
    tree = NDF.load_tree(root)
    # A clause has exactly one metadata comment; extra comments are an
    # error, but their values are still merged for reporting.
    assert check_codes(root).get("multiple-meta") == "error"
    clause = tree.clauses["ROB-001"]
    assert clause.kind == "req"
    assert clause.edge("blocks-by") == ["Q-001"]


def test_l1_root_without_l0_is_a_note(tmp_path: Path) -> None:
    root = write_tree(
        tmp_path,
        {
            "a.md": (
                "## A {#ROB-001}\n"
                "<!-- ndf: kind=req level=must layer=L1 status=stable -->\n\n"
                "It MUST exist.\n"
            )
        },
    )
    assert check_codes(root).get("clutter") == "note"


# ---------------------------------------------------------------------------
# subcommand behavior


def run_cmd(tree, func, **kwargs) -> tuple[int, str]:
    buffer = io.StringIO()
    args = type("Args", (), kwargs)()
    with redirect_stdout(buffer):
        code = func(tree, args)
    return code, buffer.getvalue()


def test_new_id_allocates_next_number(tmp_path: Path) -> None:
    tree = NDF.load_tree(clean_tree(tmp_path))
    assert run_cmd(tree, NDF.cmd_new_id, prefix="ROB")[1].strip() == "ROB-002"
    assert (
        run_cmd(tree, NDF.cmd_new_id, prefix="ROB-ENTRY")[1].strip()
        == "ROB-ENTRY-002"
    )
    # keeps the observed zero-pad width; unused prefixes start at 001
    assert run_cmd(tree, NDF.cmd_new_id, prefix="D")[1].strip() == "D-0002"
    assert run_cmd(tree, NDF.cmd_new_id, prefix="PIPE")[1].strip() == "PIPE-001"


def test_trace_prints_refinement_subtree(tmp_path: Path) -> None:
    tree = NDF.load_tree(clean_tree(tmp_path))
    code, out = run_cmd(tree, NDF.cmd_trace, id="CHR-001")
    assert code == 0
    assert "CHR-001" in out and "ROB-001" in out and "ROB-ENTRY-001" in out
    assert "verified by VER-ROB-001" in out
    code, _ = run_cmd(tree, NDF.cmd_trace, id="NOPE-001")
    assert code == 1


def test_coverage_counts(tmp_path: Path) -> None:
    cov = NDF.build_coverage(NDF.load_tree(clean_tree(tmp_path)))
    assert cov["clauses"] == 6
    assert cov["l1_must"] == 1
    assert cov["l1_must_verified"] == 1
    assert cov["verif_clauses"] == 1
    assert cov["questions_open"] == 1
    assert cov["tbd_markers"] == 1


# ---------------------------------------------------------------------------
# the chrono example (normative_language.md, Appendix C)


def test_chrono_check_is_clean_except_one_note() -> None:
    tree = NDF.load_tree(CHRONO)
    assert len(tree.clauses) == 16
    findings = NDF.run_check(tree)
    assert [f for f in findings if f.severity in ("error", "warning")] == []
    # Known state: PIN-001 does not refine up to CHR-000 (Appendix C keeps
    # interface clauses as roots) — structural clutter, reported as a note.
    assert [(f.clause, f.severity, f.code) for f in findings] == [
        ("PIN-001", "note", "clutter")
    ]


def test_chrono_coverage_matches_appendix_c9() -> None:
    cov = NDF.build_coverage(NDF.load_tree(CHRONO))
    # C.9: "TBD holes: 1 ... open questions: 1 (Q-001) conflicts: 0"
    assert cov["tbd_markers"] == 1
    assert cov["questions_open"] == 1
    assert cov["conflicts"] == 0
    # CTL-DEB-001 is the deliberate verification gap (§C.7 note).
    assert "CTL-DEB-001" in cov["unverified_l1_must"]


def test_chrono_trace_shape() -> None:
    tree = NDF.load_tree(CHRONO)
    code, out = run_cmd(tree, NDF.cmd_trace, id="CHR-000")
    assert code == 0
    lines = out.splitlines()
    assert lines[0] == "CHR-000 (L0)"
    # Document order, per C.9: SS, RST, DEB, CNT (with its L2 children), DSP.
    import re

    ids = [re.search(r"[A-Z][A-Z0-9-]+", line).group(0) for line in lines]
    assert ids == [
        "CHR-000",
        "CTL-SS-001",
        "CTL-RST-001",
        "CTL-DEB-001",
        "CNT-001",
        "CNT-TCK-010",
        "CNT-BCD-010",
        "DSP-001",
    ]
    assert "blocked by Q-001" in out
    assert "⚠ unverified" in out


def test_chrono_status_groups_by_blocked_clause() -> None:
    tree = NDF.load_tree(CHRONO)
    _, out = run_cmd(tree, NDF.cmd_status)
    assert "CTL-DEB-001:" in out
    assert "Q-001" in out


def test_chrono_model_matches_spec() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(CHRONO / "models")],
        capture_output=True,
        text=True,
        cwd=CHRONO / "models",
    )
    assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# CLI surface


def test_cli_root_resolution_and_version(tmp_path: Path) -> None:
    script = REPO / "src" / "ndf.py"
    result = subprocess.run(
        [sys.executable, str(script), "--version"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0 and "ndf" in result.stdout

    # Walk-up discovery: run from inside the chrono tree without --root.
    result = subprocess.run(
        [sys.executable, str(script), "coverage"],
        capture_output=True,
        text=True,
        cwd=CHRONO / "20-behavior",
    )
    assert result.returncode == 0
    assert "open questions:       1 of 1" in result.stdout

    # No root anywhere: exit 2 with guidance.
    result = subprocess.run(
        [sys.executable, str(script), "check"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={"PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 2
    assert "no NDF root found" in result.stderr
