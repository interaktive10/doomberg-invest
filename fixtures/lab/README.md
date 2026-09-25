# F-LAB (BRIEF §9)

A synthetic panel for the Signal Lab tests, built in memory by `make_lab.py` (seed 7): 500 companies × 60
month-ends (2015-01 to 2019-12), quarterly filings from 2012, one planted signal and one noise signal.

- **Planted (S1, the live order-book signal):** 25% of the companies see their order book step up 40%. From the
  month after the filing that makes S1 fire, their price drifts +2.5% a month for 12 months.
- **Noise (S5, the live capital-discipline signal):** 25% buy back 4% of their shares, with no price effect.
- **Leak test:** `make(shift_filed_days=400)` files the planted companies' quarters 400 days later. S1 then fires
  after the drift, so a point-in-time Lab must not find the effect (M8-02).

Periods for the tests: in-sample 2015–2016 and out-of-sample 2017–2018 (by event month); horizon 12 months.
No file is committed: the generator is the fixture.
