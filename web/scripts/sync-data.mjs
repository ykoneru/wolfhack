import { readFile } from 'node:fs/promises'

const fairness = JSON.parse(await readFile(new URL('../public/fairness.json', import.meta.url), 'utf8'))
const tracts = JSON.parse(await readFile(new URL('../public/wake-tracts.geojson', import.meta.url), 'utf8'))

const county = fairness.county_stats
if (!county?.median_ratio) throw new Error('fairness.json is missing the county median ratio')
if (county.bands?.length !== 10) throw new Error('fairness.json is missing the ten price bands')
if (tracts.type !== 'FeatureCollection' || !tracts.features?.length) throw new Error('wake-tracts.geojson is empty')

const graded = tracts.features.filter((feature) => feature.properties.enough_sales)
if (!graded.length) throw new Error('no tract has enough sales to grade')
if (typeof graded[0].properties.median_ratio !== 'number') throw new Error('a graded tract has no median ratio')

console.log(
  `Fair Share ready: ${tracts.features.length} Wake County tracts, ${graded.length} graded, ` +
    `${county.sales.toLocaleString('en-US')} sales from ${county.basis_year}, median ratio ${county.median_ratio}`,
)
