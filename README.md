# Last Door

Last Door ranks North Carolina census tracts by who loses their nearest cool public building when doors close around 5pm, then names the few buildings to keep open.

This repository is the step 0 contract. The files below are fixtures so the map and the data pipeline can be built separately. They are not the Census pull.

## Who edits what

- Data and API: `pipeline/`, `api/`, and `data/`
- Map and pages: `web/`
- Generated files the pipeline may write later: `web/public/tracts.geojson`, `web/public/sites.geojson`, and `web/public/hours.json`
- Do not commit `.env`. Copy `.env.example` when you start calling APIs.

## Scoring rules

Distance is haversine miles from a tract centroid to a site. A site is open when the selected hour is earlier than `close_hour`. A `close_hour` of `null` means the site stays open. Hospitals use that. A committed site stays open.

Vulnerability is the average of `share_age_65_plus`, `poverty_rate`, and `share_households_no_vehicle`.

- Heat risk is `(temperature_f - 75) / 35`, clamped to 0–1.
- Air risk is `aqi / 200`, clamped to 0–1.
- Burden is `0.5 * vulnerability + 0.35 * heat risk + 0.15 * air risk`.
- A tract is exposed when burden is at least `0.40`.
- A tract is covered when the nearest open site is within `3` miles.
- A tract is uncovered when it is exposed and not covered.

The 3-mile radius and the `0.40` burden cutoff are starting values. Tune them in the state run if the Triangle is already red at 2pm, or if almost nothing turns red at 6pm. The “I am here” walk speed is 3 miles per hour, which is separate from the coverage radius.

The same constants live in `pipeline/rules.py` and `web/src/rules.js`. Change them together, on `main`.

## Sample

`data/sample/` is the source. `web/public/sample/` is a copy the map can load. Five tracts, three sites, hours `14` through `20` (2pm through 8pm).

At 2pm every sample tract is covered. At 5pm the library and the community center close, four tracts become uncovered, and the hospital tract stays covered. Keeping the library open covers 8,400 people. Keeping the community center open covers 8,000. The first rescue pick is the library.

Rebuild and check the fixtures with:

```bash
python3 pipeline/build_sample.py
python3 pipeline/check_sample.py
```

## Tract fields

`tracts.geojson` properties: `id`, `name`, `population`, `share_age_65_plus`, `poverty_rate`, `share_households_no_vehicle`, `centroid` as `[lon, lat]`, `aqi`, `air_risk`, and `hourly`. Each hour has `temperature_f`, `heat_risk`, and `burden`.

## Site fields

`sites.geojson` properties: `id`, `name`, `type`, `close_hour`, `hours_source`. Geometry is a point. `hours_source` is `osm`, `default`, or `nconemap`.

## Hours file

`hours.json` has `radius_miles`, `exposed_burden_min`, `hours`, and `by_hour`. Each hour has `uncovered_population`, a `tracts` object, and `recommendations` for `"1"`, `"3"`, and `"5"` buildings. A recommendation entry has `site_id` and `people_added`.

## Branches

`main` only receives a step after its check passes. Data work stays on `data`. Map work stays on `web`.
