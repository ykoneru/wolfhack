import { readFile, mkdir, copyFile } from 'node:fs/promises'

const publicDirectory = new URL('../public/', import.meta.url)
await mkdir(publicDirectory, { recursive: true })
for (const name of ['tracts', 'sites']) {
  const source = new URL(`../../data/${name}.geojson`, import.meta.url)
  const data = JSON.parse(await readFile(source, 'utf8'))
  const types = name === 'tracts' ? ['Polygon', 'MultiPolygon'] : ['Point']
  if (data.type !== 'FeatureCollection' || !data.features?.length ||
      data.features.some(feature => !types.includes(feature.geometry?.type) || !feature.properties?.id || !feature.properties?.name)) {
    throw new Error(`Invalid ${name}.geojson: expected named ${types.join('/')} features`)
  }
  await copyFile(source, new URL(`${name}.geojson`, publicDirectory))
  console.log(`Copied ${data.features.length.toLocaleString('en-US')} ${name} to web/public`)
}
