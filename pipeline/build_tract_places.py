"""Build map place labels from recorded 2024 sale cities, not neighborhood names."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main():
    sales = json.loads((ROOT / 'data/sales.json').read_text())['sales']
    year = json.loads((ROOT / 'data/fairness.json').read_text())['county_stats']['basis_year']
    places = {}
    for sale in sales:
        city = (sale.get('city') or '').strip()
        tract = sale.get('tract_id')
        if sale.get('sale_year') != year or not city or not tract:
            continue
        name = 'Unincorporated Wake County' if city == 'UNINCORPORATED WAKE' else city.title()
        places.setdefault(tract, set()).add(name)
    output = {tract: sorted(cities) for tract, cities in sorted(places.items())}
    (ROOT / 'web/public/tract-places.json').write_text(json.dumps(output, indent=2) + '\n')
    print(f'Built recorded sale place labels for {len(output)} census tracts')

if __name__ == '__main__':
    main()
