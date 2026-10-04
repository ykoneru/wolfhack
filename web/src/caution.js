import { CAUTION } from './config.js'

function yearNow() {
  return new Date().getFullYear()
}

export function cautionFlags(detail, options = {}) {
  const limits = { ...CAUTION, ...options }
  const flags = []
  const land = Number(detail.land)
  const building = Number(detail.building)
  const share = detail.land_share
  const built = detail.year_built
  const tractBuilding = detail.tract?.median_building

  if (!Number.isFinite(land) || land <= 0 || !Number.isFinite(building) || building <= 0) {
    flags.push({
      code: 'missing',
      reason: 'Land or building value is missing or zero, so the split is not reliable.',
    })
    return flags
  }

  if (share != null && share > limits.highLandShare) {
    flags.push({
      code: 'high-share',
      reason: 'Land is more than 80% of the split. That can be a real lot, or an appraisal quirk.',
    })
  } else if (share != null && share < limits.lowLandShare) {
    flags.push({
      code: 'low-share',
      reason: 'Land is under 10% of the split. That can understate the lot in a mass appraisal.',
    })
  }

  if (building < land * limits.buildingVsLand) {
    flags.push({
      code: 'teardown-signal',
      reason: 'Likely teardown candidate: the building is valued far below the land.',
    })
  } else if (
    built &&
    built <= limits.oldYear &&
    Number.isFinite(tractBuilding) &&
    tractBuilding > 0 &&
    building < tractBuilding * limits.neighborhoodBuildingRatio
  ) {
    flags.push({
      code: 'old-vs-neighborhood',
      reason: 'Likely teardown candidate: the building is valued far below nearby homes.',
    })
  }

  if (built && yearNow() - built <= limits.newConstructionYears) {
    flags.push({
      code: 'new-construction',
      reason: 'Built within the last two years, so the assessed building value may still be incomplete.',
    })
  }

  return flags
}
