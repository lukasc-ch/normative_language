# Controls

## Start/stop toggling {#CTL-SS-001}
<!-- ndf: kind=req level=must layer=L1 refines=CHR-000 status=stable since=0.1 -->

Each press of START/STOP MUST toggle the state: stopped → running,
running → stopped. Stopping MUST preserve the current count; a
subsequent start MUST resume from the preserved count.

## Reset {#CTL-RST-001}
<!-- ndf: kind=req level=must layer=L1 refines=CHR-000 status=stable since=0.1 -->

A press of RESET MUST set the count to 00 and MUST force the state to
stopped, regardless of the current state. See [[D-0001 | D-0001]] for
the rejected "reset keeps running" alternative.

## Button conditioning {#CTL-DEB-001}
<!-- ndf: kind=req level=must layer=L1 refines=CHR-000 status=draft since=0.1 -->
<!-- ndf: blocks-by=Q-001 -->

Each raw button input MUST be synchronized to `clk` (min. 2 flops) and
debounced such that one physical press yields exactly one press event.
A press event MUST be recognized no later than
⟨TBD: debounce interval, see Q-001⟩ after the physical press.
Simultaneous RESET and START/STOP press events MUST resolve as RESET
alone ([[CTL-RST-001]] wins).
