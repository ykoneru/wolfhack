# Fair Share

Zillow and Redfin tell you what your house is worth, because they are built for buyers and sellers. Nobody tells a homeowner whether the county assessed their house fairly, even though that number sets the tax bill every year.

Fair Share runs the check. It compares every Wake County single-family home that sold since the January 1, 2024 revaluation against the value the county assessed it at, then reports the result four ways, using the thresholds in the International Association of Assessing Officers *Standard on Ratio Studies*.

## What it found

Wake County meets all four standards. The median sales ratio is 0.951, the coefficient of dispersion is 7.6 against a ceiling of 15, the price-related differential is 1.016 inside a band of 0.98 to 1.03, and the price-related bias is -0.030 inside a band of -0.05 to 0.05.

The price bands still tilt. Sorted into ten equal groups by sale price, the cheapest tenth of homes sits at a median ratio of 0.982 and the priciest tenth at 0.907, declining almost monotonically in between. A $300,000 home is assessed at about 98 percent of what it sold for; a $1,000,000 home at about 91 percent. That gap is real, and it is also inside the tolerance the profession allows. The site reports both.

## Data

Every number traces to a public source. Nothing is modelled or imputed.

| Source | Used for |
| --- | --- |
| Wake County `Property/Parcels` ArcGIS service | assessed value, sale price, sale date, year built, heated area, parcel centroid |
| Census TIGER/Line | tract boundaries |
| ACS tables B25003, B25077, B25070 | owner occupancy, median owner value, renter cost burden |

Search and the official equity measures both use 2024 sales, so a home's own ratio and every benchmark it is compared against describe the same moment. 12,799 of those sales survive the arm's-length filters. 208 of Wake's 230 tracts have the fifteen sales needed before a tract median is worth reporting.

## Run

Build the data, which writes `data/fairness.json`, `data/sales.json`, and `web/public/wake-tracts.geojson`:

```bash
.venv/bin/python pipeline/fetch_parcels.py
.venv/bin/python pipeline/fetch_housing.py
.venv/bin/python pipeline/build_fairness.py
```

Check the ratio-study math against figures worked out by hand:

```bash
.venv/bin/python pipeline/check_fairness.py
```

Serve the lookups, the explanation, and the speech:

```bash
.venv/bin/python api/server.py
```

Then the map, from `web/`:

```bash
npm install
npm run dev
```

## Limits

A high ratio is evidence worth checking, not proof an appeal will succeed; the county's appraisal may account for condition or site features that a sale price and a square footage cannot see. The dollar figure shown on a home is a gap in assessed value, not in tax owed, because the rate depends on municipality and special districts. The method page states the filters, the thresholds, and what the measures cannot say.

Do not commit `.env`.
