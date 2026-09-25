# GDELT DOC 2.0 samples (mock responses)

`api.gdeltproject.org` is blocked by the build container's egress policy (CONNECT 403, 2026-09-25), so these
responses are written in the documented `mode=timelinevolraw&format=json` shape rather than recorded:
`{"query_details": {...}, "timeline": [{"series": "Article Count", "data": [{"date": ..., "value": N, "norm": M}]}]}`.
GDELT reports errors as plain text with HTTP 200; `too_short.txt` and `rate_limit.txt` are two such answers.
