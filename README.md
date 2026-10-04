# House or Lot

Buyers see one price. Wake County already prices two things: the dirt and the structure. House or Lot splits them so you can tell whether you are buying a house to live in, or a lot that happens to have a house on it.

Land share is the county land value divided by land plus building.

- Under 40 percent: **house**. Improvements and condition matter more than the lot.
- 40 percent or more: **lot**. A remodel will not change what the market is pricing. Insurance rebuilds the building, not the land.
- 40 percent or more and built in 1975 or earlier: **teardown watch**. You may be bidding against someone who will take the house down.

## Data

Every number traces to a public source. Nothing is modelled or imputed.

| Source | Used for |
| --- | --- |
| Wake County `Property/Parcels` ArcGIS service | land value, building value, year built, heated area, last sale, parcel centroid |
| Census TIGER/Line | tract boundaries |
| ACS tables B25003, B25077, B25070 | owner occupancy, when shown |

## Run

```bash
.venv/bin/python pipeline/fetch_parcels.py
.venv/bin/python pipeline/fetch_housing.py
.venv/bin/python pipeline/build_land.py
.venv/bin/python pipeline/check_land.py
.venv/bin/python api/server.py
```

In another terminal, from `web/`:

```bash
npm install
npm test
npm run dev
```

The map is at http://127.0.0.1:5173/.
