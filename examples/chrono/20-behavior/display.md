# Display

## Display encoding {#DSP-001}
<!-- ndf: kind=req level=must layer=L1 refines=CHR-000 status=stable since=0.1 -->

`sec_hi`/`sec_lo` MUST continuously present the current count as BCD
([[DEF-001]]) with no blanking, multiplexing, or intermediate
non-BCD codes observable at the outputs; the pair MUST update
atomically within one `clk` cycle.
