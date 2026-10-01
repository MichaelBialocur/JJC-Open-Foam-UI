"""One versioned catalog shared with the UI; no runtime property-service dependency."""
import json
from pathlib import Path

CATALOG = json.loads(Path(__file__).with_name('material-catalog.json').read_text())
FLUIDS = CATALOG['fluids']
MATERIALS = CATALOG['materials']
INLET_UNITS = CATALOG['inlet_units']


def unit_factor(kind, unit):
    for item in INLET_UNITS[kind]['units']:
        if item['id'] == unit:
            return item['factor_to_si']
    raise ValueError(f'{unit} is not a valid {INLET_UNITS[kind]["label"].lower()} unit.')
