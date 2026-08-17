# Normative Language (NDF)

NDF — the Normative Description Format — organizes the normative description
of highly complicated systems as a clause tree: heading-anchored clauses with
machine-readable metadata, explicit refinement layers (L0 intent → L1
contract → L2 mechanism → L3 executable), tracked holes, decision records,
and open questions.

## Contents

| Path | Purpose |
| --- | --- |
| [`normative_language.md`](normative_language.md) | The specification (English, authoritative) |
| [`normative_language_cn.md`](normative_language_cn.md) | Chinese translation |
| [`src/ndf.py`](src/ndf.py) | Reference toolchain (`ndf` CLI) implementing the §8 minimum-viable tool set |
| [`examples/chrono/`](examples/chrono/) | The Appendix C worked example as a real, checkable NDF tree |
| [`tests/`](tests/) | Toolchain test suite |

## The `ndf` CLI

Zero-dependency single module; three ways to run it:

```bash
# 1. Directly, no installation
python3 src/ndf.py --root examples/chrono check

# 2. Installed (adds the `ndf` command)
pip install .
ndf --root examples/chrono coverage

# 3. From a checkout pinned inside another repository (e.g. a submodule)
python3 path/to/normative_language/src/ndf.py --root path/to/your/ndf check
```

The tree root is `--root`, or `$NDF_ROOT`, or the nearest ancestor of the
current directory containing `ndf.yaml`.

Implemented subcommands (spec §8): `new-id`, `check` (`--json`, `--strict`),
`trace`, `coverage` (`--json`), `status`, `options`. Not yet implemented:
`log`, `diff`, `deps`, `export`, `publish`, `ingest`, and the `models/`
runner.

```console
$ python3 src/ndf.py --root examples/chrono trace CHR-000
CHR-000 (L0)
├── CTL-SS-001 (L1) ── verified by VER-CTL-001
├── CTL-RST-001 (L1) ── verified by VER-CTL-001
├── CTL-DEB-001 (L1, draft, 1 TBD, blocked by Q-001)   ⚠ unverified
├── CNT-001 (L1) ── verified by VER-CNT-002, VER-CTL-001
│   ├── CNT-TCK-010 (L2)
│   └── CNT-BCD-010 (L2) ── verified by VER-CNT-002
└── DSP-001 (L1) ── verified by VER-DSP-003
```

## Tests

```bash
pip install -e .[dev]
pytest
```
