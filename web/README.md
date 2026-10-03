# Step 4: North Carolina map

From `web/`, run `npm install` and `npm run dev`. Open the local URL printed
by Vite. `npm run build` creates a static production site in `dist/`;
`npm run preview` serves the build.

The map loads the real `tracts.geojson` and `sites.geojson` files. Tracts
remain gray and unscored. Small red dots show sites; click one for its name
and type. Click a tract for its name and ID, or use the tract selector.
The initial view fits North Carolina; the sidebar also offers a Triangle view.
The 2–8 PM slider only updates its label. It does not filter or score data.

`npm run dev` and `npm run build` first copy the canonical files from
`../data/` into `public/`. Run `npm run sync:data` after receiving updated data
while the dev server is running, then refresh. Generated copies are ignored
by Git; the original files remain unchanged and are already tracked in `data/`.
Missing or invalid source data fails the sync explicitly.

No API keys or backend are needed. The browser reads local GeoJSON files;
OpenStreetMap background tiles are the only external data requests. Leaflet
and its CSS are bundled locally. Canvas rendering handles statewide tract
geometry, and a separate pane keeps the site dots above selected polygons.

Verification: confirm the counts match `data/`, the state draws in gray,
site dots appear over real cities, and both kinds of popup work. Refresh
and move the hour slider; map colors and site visibility should not change.
The current input contains 2,660 tracts and 962 sites (392 libraries,
407 community centers, and 163 hospitals).
