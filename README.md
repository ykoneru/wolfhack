# FlowMap

FlowMap estimates when Wake County is likely to be more or less active on a typical weekday, then recommends a time to visit a place. It is not a live crowd count and it is not a traffic app.

The score adds population density, Census commute-departure timing, OpenStreetMap destinations, and road-and-bus connectivity. Parks get a small weather and air-quality adjustment from 2pm to 8pm. The best time is the lowest score in the user’s window that still leaves a 45-minute visit before the place closes.

## Run

```bash
.venv/bin/python pipeline/build_flowmap.py
.venv/bin/python api/server.py
```

The map is in `web/`:

```bash
cd web
npm install
npm run dev
```

The method page explains the weights, the opening-hour defaults, and the limits. Do not commit `.env`.
