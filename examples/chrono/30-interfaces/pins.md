# Interfaces

## External pins {#PIN-001}
<!-- ndf: kind=req level=must layer=L1 status=stable since=0.1 -->

The design MUST expose exactly the following interface:

```text ndf:normative
clk        in   1   system clock, 32.768 kHz (see CON-CLK-001)
rst_btn    in   1   RESET button, raw, active-high, asynchronous
ss_btn     in   1   START/STOP button, raw, active-high, asynchronous
sec_lo     out  4   BCD, seconds units digit (0-9)
sec_hi     out  4   BCD, seconds tens digit  (0-9)
running    out  1   1 while in running state (status indicator)
```

Button inputs are raw mechanical-switch signals; conditioning is the
design's responsibility ([[CTL-DEB-001]]).
