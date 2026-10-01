"""Regenerate fixed 20 °C presets: python -m pip install CoolProp==7.2.0.

CoolProp is needed only to regenerate this checked-in catalog, not to run the app.
"""
import json
from pathlib import Path
import CoolProp
from CoolProp.CoolProp import PropsSI

if CoolProp.__version__ != '7.2.0':
    raise RuntimeError('Use CoolProp==7.2.0 for reproducible catalog values.')

mapping = {'density_kg_m3':'D', 'dynamic_viscosity_pa_s':'V',
           'specific_heat_j_kg_k':'C', 'thermal_conductivity_w_m_k':'L'}
fluids = {}
for key, label, fluid, concentration in [
    ('water','Water','Water',None), ('air','Dry air','Air',None),
    ('water_eg30','Water + ethylene glycol · 30%','INCOMP::MEG-30%',.30),
    ('water_eg50','Water + ethylene glycol · 50%','INCOMP::MEG-50%',.50),
    ('water_pg30','Water + propylene glycol · 30%','INCOMP::MPG-30%',.30),
    ('water_pg50','Water + propylene glycol · 50%','INCOMP::MPG-50%',.50),
]:
    mixture = concentration is not None
    short_label = f'{concentration:.0%} {"ethylene" if "eg" in key else "propylene"} glycol' if mixture else label
    fluids[key] = {'label':label, 'short_label':short_label, 'temperature_c':20, 'pressure_pa':101325,
        'glycol_mass_fraction':concentration, 'coolprop_fluid':fluid,
        'values':{name:float(f'{PropsSI(prop,"T",293.15,"P",101325,fluid):.10g}') for name,prop in mapping.items()},
        'source':{'label':'CoolProp 7.2.0 · Melinder aqueous-mixture correlation' if mixture else f'CoolProp 7.2.0 · {fluid}',
                  'url':'https://coolprop.org/fluid_properties/Incompressibles.html' if mixture else f'https://coolprop.org/fluid_properties/fluids/{fluid}.html'},
        'note':'Glycol concentration is by mass, not by volume. Generic aqueous solution; inhibitor/additive effects are not represented.' if mixture else 'Dry air at 1 atm; humidity and pressure variation are not modeled.' if key=='air' else 'Liquid water at 1 atm.'}

materials = {
    'aluminium':{'label':'Aluminium · EN AW-6060', 'short_label':'Aluminium', 'temperature_c':20,
        'values':{'solid_conductivity_w_m_k':200, 'solid_density_kg_m3':2700, 'solid_specific_heat_j_kg_k':898},
        'source':{'label':'thyssenkrupp · EN AW-6060', 'url':'https://www.thyssenkrupp-materials.co.uk/aluminium-6060.html'},
        'note':'Conductivity uses the lower end of the published 200–220 W/(m·K) range. Density is 2700 kg/m³; the web table has a density-unit typo.'},
    'copper':{'label':'Copper · C11000', 'short_label':'Copper', 'temperature_c':20,
        'values':{'solid_conductivity_w_m_k':391.1, 'solid_density_kg_m3':8910, 'solid_specific_heat_j_kg_k':393.5},
        'source':{'label':'Aviva Metals · C11000', 'url':'https://www.avivametals.com/collections/copper-alloys/beryllium-copper/c11000-cda-110-cu-etp-electrolytic-tough-pitch-etp-copper'},
        'note':'Representative constant properties retained from the verified v0.4 material definition.'},
}
def units(label, default, rows):
    return {'label':label, 'default_unit':default,
            'units':[{'id':key,'label':name,'factor_to_si':factor} for key,name,factor in rows]}

catalog = {'schema_version':1, 'property_engine':'CoolProp 7.2.0', 'fluids':fluids, 'materials':materials,
    'inlet_units':{
        'velocity':units('Velocity','m/s', [('m/s','m/s',1),('cm/s','cm/s',.01),('mm/s','mm/s',.001),('km/h','km/h',1/3.6),('ft/s','ft/s',.3048)]),
        'volumetric_flow':units('Volumetric flow','L/min', [('L/min','L/min',.001/60),('L/h','L/h',.001/3600),('L/s','L/s',.001),('mL/min','mL/min',1e-6/60),('m3/h','m³/h',1/3600),('m3/s','m³/s',1),('CFM','CFM (ft³/min)',.3048**3/60),('US_gpm','US gal/min',.003785411784/60)]),
        'mass_flow':units('Mass flow','kg/h', [('kg/h','kg/h',1/3600),('kg/min','kg/min',1/60),('kg/s','kg/s',1),('g/s','g/s',.001)]),
    },
    'unit_source':'https://www.nist.gov/pml/us-surveyfoot/revised-unit-conversion-factors',
    'unit_note':'International foot = 0.3048 m exactly. CFM denotes actual volume, not standard/normal volume.'}
path = Path(__file__).resolve().parents[1]/'backend/app/material-catalog.json'
path.write_text(json.dumps(catalog,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
print(path)
