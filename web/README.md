# Fair Share map

From `web/`, run `npm install` and `npm run dev`. The page loads Wake County tracts and the county ratio study from `public/`.

Start the API from the repo root so address search, the explanation, and the spoken reply work:

```bash
.venv/bin/python api/server.py
```

`npm test` checks the map colour scale, the dollar and ratio formatting, the pass-or-fail test against each published standard, and that the shortest price-band bar never collapses to nothing.

Map hover location labels use city names from recorded 2024 sale addresses, not verified neighborhood boundaries. After updating the sales dataset, regenerate them from the repository root with `python3 pipeline/build_tract_places.py`.
