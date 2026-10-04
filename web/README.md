# Parcel map

From `web/`, run `npm install` and `npm run dev`. The page loads Wake County tracts and the land-share study from `public/`.

Start the API from the repo root so address search and Ask work:

```bash
.venv/bin/python api/server.py
```

`npm test` checks the map colour scale, dollar and land-share formatting, and the house / lot / teardown copy.
