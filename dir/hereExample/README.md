# hereExample

A tiny deterministic response-closure example for the LeafOS persistent loop.

`classify(expected, observed)` must return:

- `confirmed` when both known values agree;
- `contradicted` when both known values disagree;
- `inconclusive` when either value is missing.

Run the acceptance check with:

```bash
python3 -m unittest discover -s tests -v
```
