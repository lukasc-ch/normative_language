# Counting

## Counting contract {#CNT-001}
<!-- ndf: kind=req level=must layer=L1 refines=CHR-000 status=stable since=0.2 model=models/chrono.py -->

While running, the count MUST increment by one exactly once per
elapsed second, with long-term rate accuracy limited only by the
clock source ([[CON-CLK-001]]). The count MUST hold at its value
while stopped. On incrementing past 99 the count MUST wrap to 00 and
continue ([[D-0001]]).

## Second-tick generation {#CNT-TCK-010}
<!-- ndf: kind=req level=must layer=L2 refines=CNT-001 status=stable since=0.2 -->

A modulo-32768 divider on `clk` MUST generate a one-cycle `tick`
pulse each second. RESET ([[CTL-RST-001]]) MUST also clear the
divider, so the first second after reset is full-length.

## BCD counter {#CNT-BCD-010}
<!-- ndf: kind=req level=must layer=L2 refines=CNT-001 status=stable since=0.2 -->

The count MUST be maintained as two cascaded decade counters (units,
tens), never holding a non-BCD value; on `tick` while running:
units 9→0 carries into tens, tens 9→0 wraps the whole count to 00.
