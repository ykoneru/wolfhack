import { readFile } from 'node:fs/promises'

const land = JSON.parse(await readFile(new URL('../public/land.json', import.meta.url), 'utf8'))
const tracts = JSON.parse(await readFile(new URL('../public/wake-tracts.geojson', import.meta.url), 'utf8'))

const county = land.county_stats
if (!county?.median_land_share) throw new Error('land.json is missing the county land share')
if (!county.cities?.length) throw new Error('land.json is missing city splits')
if (tracts.type !== 'FeatureCollection' || !tracts.features?.length) throw new Error('wake-tracts.geojson is empty')

const graded = tracts.features.filter((feature) => feature.properties.enough_homes)
if (!graded.length) throw new Error('no tract has enough homes to grade')
if (typeof graded[0].properties.median_land_share !== 'number') throw new Error('a graded tract has no land share')

console.log(
  `House or Lot ready: ${tracts.features.length} Wake County tracts, ${graded.length} graded, ` +
    `${county.homes.toLocaleString('en-US')} homes, typical land share ${county.median_land_share}`,
)
