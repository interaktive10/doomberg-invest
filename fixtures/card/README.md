# F-CARD (BRIEF §9, M6-02)

`make_card.py` writes one evidence pack (`pack.json`) for a fictional company, Nimbus Compute Corp., plus six thesis cards for it:

- `good.json` passes `pipeline/thesis/validate.py`.
- Five bad cards each differ from the good card in exactly one respect:
  - `bad_uncited.json`: a fact sentence with no citation;
  - `bad_number.json`: a number that matches no cited pack value;
  - `bad_inference.json`: an inference without the "Inference:" label;
  - `bad_kill.json`: a kill criterion whose check-after date falls before the next filing window;
  - `bad_hype.json`: a hype word ("multibagger").

`expected.json` lists, for each bad card, the error `validate.py` must report. `tests/thesis/test_validate.py` checks that each bad card fails with exactly that error, and that these files are the generator's output.

To regenerate: `python fixtures/card/make_card.py`
