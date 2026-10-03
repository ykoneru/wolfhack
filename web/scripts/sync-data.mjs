import { readFile } from 'node:fs/promises'

const activity = JSON.parse(await readFile(new URL('../public/activity.json', import.meta.url), 'utf8'))
const places = JSON.parse(await readFile(new URL('../public/places.json', import.meta.url), 'utf8'))
const tracts = JSON.parse(await readFile(new URL('../public/wake-tracts.geojson', import.meta.url), 'utf8'))
if (!activity.tracts || !activity.demo_place_id) throw new Error('activity.json is not a FlowMap file')
if (!places.places?.length) throw new Error('places.json is empty')
if (tracts.type !== 'FeatureCollection' || !tracts.features?.length) throw new Error('wake-tracts.geojson is empty')
const sample = activity.tracts[tracts.features[0].properties.id]
if (!sample?.['17']) throw new Error('activity.json is missing the 5pm score')
console.log(`FlowMap ready: ${tracts.features.length} Wake County tracts, ${places.places.length.toLocaleString('en-US')} places`)
