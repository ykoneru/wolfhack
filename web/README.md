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
