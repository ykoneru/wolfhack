# Step 2: sample map

From `web/`:

```sh
npm install
npm run dev
```

Open the local URL printed by Vite. `npm run build` creates `dist/`;
`npm run preview` serves that production build.

The Leaflet map starts over the Research Triangle and reads only
`public/sample/tracts.geojson`. All five polygons stay gray. Click a polygon
to show its full name, or choose a tract from the keyboard-accessible list.
The 2–8 PM slider updates its time label without changing the map.

No keys or backend are needed. Project data comes from the local fixture;
OpenStreetMap background tiles are the only external map requests. Leaflet
and its styles are bundled locally. If tiles fail, the polygons still render.

Manual check: refresh, confirm five gray polygons, click each polygon, and
move the slider. The tract names should match the fixture and no polygon
should change color or disappear. Repeat at a narrow/mobile viewport.

References: [Leaflet quick start](https://leafletjs.com/examples/quick-start/)
and [Vite guide](https://vite.dev/guide/).
