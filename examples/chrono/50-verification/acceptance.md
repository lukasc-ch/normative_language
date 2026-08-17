# Acceptance

## Control sequence equivalence {#VER-CTL-001}
<!-- ndf: kind=verif level=must layer=L3 verifies=CTL-SS-001,CTL-RST-001,CNT-001 -->

The DUT MUST match `models/chrono.py` on 1,000 randomized sequences
of {press_reset, press_startstop, tick} (10,000 events each),
comparing `(count, running)` after every event.

## Wrap behavior {#VER-CNT-002}
<!-- ndf: kind=verif level=must layer=L3 verifies=CNT-001,CNT-BCD-010 -->

Directed test: from reset, run 100 ticks; outputs MUST read 99 at
tick 99 and 00 at tick 100 with `running` still asserted.

## Output BCD invariant {#VER-DSP-003}
<!-- ndf: kind=verif level=must layer=L3 verifies=DSP-001 -->

Assertion, all tests: `sec_hi <= 9 && sec_lo <= 9` at every clock
edge, including during carry propagation.
