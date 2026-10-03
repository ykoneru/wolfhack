# Step 8: the afternoon flip

From `web/`, run `npm install` and `npm run dev`. Open the URL printed by
Vite. `npm run build` creates the static site in `dist/`; `npm run preview`
serves it. `npm test` checks coverage colors, input validation, and playback.

The map reads local `tracts.geojson`, `sites.geojson`, and `hours.json`.
The slider selects each computed hour from 2 PM through 8 PM, recolors all
tracts, and updates the large uncovered-population number. High-burden
uncovered tracts are red; high-burden covered tracts are teal; lower-burden
tracts are gray. These colors use the computed coverage flags in hours.json.
No scoring or live data API calls run in the browser.

Play starts at 4 PM and advances through 5, 6, and 7 PM, then stops. Pause
stops at the current hour. Moving the slider or hiding the browser tab pauses
playback. Pressing Play again restarts the 4–7 PM sequence. The initial map
view fits North Carolina; the Triangle view remains available.

Startup and build copy the canonical tract and site files from `../data/`.
The pipeline's `public/hours.json` is tracked directly and validated against
the copied tract IDs and population totals for all seven hours. Invalid hourly
data fails the build; a runtime failure keeps the base map available with
playback disabled and an unavailable-data message. Generated tract and site
copies are ignored by Git. Run `npm run sync:data` after receiving updated
pipeline files while the dev server is running, then refresh.

The current statewide hourly file was brought from origin/main's step 7
commit 2c26260. Its uncovered totals are 7,423 at 2 PM and 25,639 at 6 PM.
The displayed number is total high-burden population lacking coverage at the
selected hour, including people already uncovered at 2 PM. It is not the
number of unique people newly uncovered since 2 PM.

The supplied scores expose 15 tracts statewide and none inside the Triangle
view. Seven of those tracts are uncovered at 6 PM versus two at 2 PM. The UI
uses those results faithfully; a dramatic Triangle flip requires revised
pipeline inputs or calibration from the data owner.

Manual check: select 2 PM and 6 PM and compare colors and totals. Press Play
and observe 4–7 PM without intervention. Pause, drag the slider, and restart.
Check that a selected tract keeps its outline while its fill follows the hour.
Site dots remain visible and clickable; their visibility is not time-filtered
in this step. OpenStreetMap background tiles are the only external map data
requests.

## Step 10: rescue and walking access

Select None, 1, 3, or 5 under "Keep buildings open". The UI reads the
precomputed recommendations for that hour from hours.json, highlights those
sites in yellow, restores covered colors to their nearby tracts, and updates
the uncovered total. It uses the radius in hours.json and the pipeline's
haversine centroid rule, counting overlapping populations once. Changing the
hour or running Play recomputes the scenario for that hour. If fewer than the
requested number of buildings help, the actual count is shown.

The rescue works from files without starting the API server. Checks compare
its saved population with the pipeline recommendations for every hour and
staffing choice. The /recommend API uses the same forced-open semantics;
no calls to Census, weather, Overpass, or routing services run in the browser.

Click a site dot or recommendation to open /sites/{id}. The page displays
its name, normal closing time, hours source, selected-hour status, population
within the coverage radius, and additional uncovered population it could
cover. Counts for individual buildings can overlap; each recommendation's
"people added" is its marginal gain after previous picks. The site URL carries
the hour and staffing choice so refresh and sharing reproduce the scenario.
"Show on map" returns to the map and focuses on the building. Unknown site
IDs show a not-found state. A static host must serve index.html for /sites/*
paths (Vite dev and preview already do so).

Select "I am here" and click the map. The nearest site open at the selected
hour is named, with straight-line miles, an estimated walk at 3 mph, arrival
time, and whether it is within the coverage radius and reachable before
closing. Arriving exactly at closing is too late. Hospitals/24-hour sites
and buildings kept open in the scenario have no modeled closing deadline.
The selected point persists when changing hour or staffing, and the result
updates. This is a distance estimate, not a street route. No GPS permission
or routing API is used.

At 6 PM, keeping three buildings open restores 16,559 people and reduces
the current statewide uncovered population from 25,639 to 9,080. The five
option currently selects four useful buildings. Tests cover these counts,
overlap, closing equality, hospitals, and the 3-mile walking limit.
