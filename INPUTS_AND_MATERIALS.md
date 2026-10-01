# Inlet units and editable materials · v0.5

## Input meaning

The circular pipe inlet area is `A = pi D²/4`. Velocity inputs convert directly to m/s; actual volumetric flow converts to m³/s and uses `U = Q/A`; mass flow converts to kg/s and uses `U = mass_flow/(rho A)`. All three feed the same uniform OpenFOAM velocity boundary. The original type/value/unit and the derived SI velocity are saved. A subsequent density or diameter edit recomputes velocity without changing the specified mass or volume flow. Changing the unit or boundary type converts the current value to preserve its physical meaning.

The backend validates unit/type combinations, positive finite values and the existing 100 m/s mean-velocity ceiling. The ceiling is an input guard, not a guarantee that incompressibility or any selected property values apply to the requested conditions.

Definitions: 1 L = 0.001 m³; 1 min = 60 s; 1 h = 3600 s; the international foot is exactly 0.3048 m. Therefore **1 CFM = 0.0004719474432 m³/s = 28.316846592 L/min**. A US gallon is 231 cubic inches = 0.003785411784 m³; the unit is labelled **US gal/min**. Sources: [NIST conversion factors](https://www.nist.gov/pml/us-surveyfoot/revised-unit-conversion-factors) and [NIST SP 811, Appendix B](https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication811e2008.pdf). CFM is actual volume at the selected conditions; standard/normal gas flow is not implemented.

## Fluid provenance

`backend/app/material-catalog.json` is the single backend/UI catalog. Its fluids were generated with **CoolProp 7.2.0**, using `PropsSI` at **293.15 K, 101325 Pa**, then rounded to ten significant figures. The rounded values are the actual application inputs. No CoolProp service or package is needed at runtime.

| Preset | Density kg/m³ | Dynamic viscosity Pa·s | Cp J/(kg·K) | Conductivity W/(m·K) |
|---|---:|---:|---:|---:|
| Water | 998.2071505 | 0.001001596143 | 4184.050925 | 0.5980123555 |
| Dry air | 1.204575182 | 0.00001820567518 | 1006.144032 | 0.02587382830 |
| Water + ethylene glycol, 30% | 1038.045507 | 0.002166449509 | 3718.251014 | 0.4648972237 |
| Water + ethylene glycol, 50% | 1064.928663 | 0.003693211431 | 3312.041904 | 0.3891483531 |
| Water + propylene glycol, 30% | 1023.784966 | 0.002964975516 | 3857.004010 | 0.4444288290 |
| Water + propylene glycol, 50% | 1039.060551 | 0.006393611173 | 3530.194859 | 0.3594636375 |

CoolProp sources: [Water](https://coolprop.org/fluid_properties/fluids/Water.html), [Air](https://coolprop.org/fluid_properties/fluids/Air.html), and [incompressible aqueous mixtures](https://coolprop.org/fluid_properties/Incompressibles.html). The mixture identifiers are `INCOMP::MEG-30%`, `MEG-50%`, `MPG-30%`, `MPG-50%`, from the documented Melinder mass-based correlations. Fractions are **glycol mass fractions**, not volume fractions. They represent generic aqueous mixtures, not a particular inhibited coolant product. The online documentation can describe a newer CoolProp release; the generation script pins the actual engine used here.

Properties stay constant throughout a solve and do not follow inlet temperature automatically. Air is dry and uses the stated pressure. Presets do not validate freezing, boiling, humidity, compressibility or large temperature excursions. Edit values for the intended state within the existing model's applicability. Reference-case buttons preserve the prior exact constants and show **Custom / benchmark properties**.

To regenerate the fluid catalog for development only:

```bash
.venv/bin/python -m pip install CoolProp==7.2.0
.venv/bin/python scripts/build_material_catalog.py
```

## Solid provenance

The v0.4 wall constants are retained, now with all three properties editable in the material window:

| Material | Conductivity W/(m·K) | Density kg/m³ | Heat capacity J/(kg·K) |
|---|---:|---:|---:|
| Aluminium EN AW-6060 | 200 | 2700 | 898 |
| Copper C11000 | 391.1 | 8910 | 393.5 |

Aluminium uses the lower end of [thyssenkrupp's 200–220 W/(m·K) range](https://www.thyssenkrupp-materials.co.uk/aluminium-6060.html). Its web table's density unit is a typo: 2.70 g/cm³ corresponds to 2700 kg/m³. Copper values follow the SI entries in [Aviva Metals' C11000 data](https://www.avivametals.com/collections/copper-alloys/beryllium-copper/c11000-cda-110-cu-etp-electrolytic-tough-pitch-etp-copper). These are representative room-temperature material definitions, not universal values for all grades. Conductivity determines the present steady wall equation; density and heat capacity are retained as native material inputs but do not introduce transient heat storage.

## Verification

Automated checks cover independent dimensional conversion examples; incompatible units, non-finite and invalid flows; density/diameter edits; saved-input round trips; legacy defaults; property overrides; matching preview/submission inputs; and edited solid properties reaching the native thermo dictionaries. For the existing laminar and Superpipe benchmarks, velocity/L/min/kg/h generate identical flow solver files on coarse, medium and fine meshes, excluding the manifest which retains input provenance.

Frontend checks cover all unit switches, fixed mass/volume semantics, blank entries and preset edits. The compiled React interface was also exercised against the live API: hidden property fields, material selection, Apply/Cancel/Reset, keyboard Escape/focus, invalid density rejection, kg/h and CFM preview values, legacy reference presets, and saved coupled-run field views. This DOM/SVG-fallback check does not claim a new WebGL browser qualification.

### Actual glycol mass-flow mesh study

Foundation OpenFOAM 14, 2026-10-01. Water with 30% ethylene glycol by mass, **6 kg/h**, D=10 mm, L=1000 mm, 20 °C, no heating. The preset values above determine Reynolds number; no coefficient is adjusted to fit the reference. Flow equations and the existing 5° wedge are unchanged. Compare the downstream gradient with **Hagen–Poiseuille, Darcy f = 64/Re**, and the developed profile with the parabola. The source, sampling and qualification criteria are in [VALIDATION.md](docs/VALIDATION.md). This is analytical verification, not experimental validation of glycol or its property correlation.

Measured results are recorded in [input-benchmarks.json](docs/input-benchmarks.json). All solver stopping reasons and qualification checks are retained. Axial/radial refinement does not remove the fixed wedge angular error; an unusually small coarse-grid error can reflect cancellation and must not be interpreted as superior accuracy.

Re = **97.951321**, analytical Darcy f = **0.653385779**:

| Mesh | Cells | Computed Darcy f | Signed friction error | Profile RMSE / bulk velocity |
|---|---:|---:|---:|---:|
| Coarse | 1,920 | 0.653359156 | −0.00407% | 0.34210% |
| Medium | 7,680 | 0.654312108 | +0.14177% | 0.18656% |
| Fine | 30,720 | 0.654551454 | +0.17841% | 0.17141% |

All three pass the existing project qualification checks and 2% analytical screening targets. Computed inlet mass flow is **6.00000000000 kg/h** to the displayed precision. The medium-to-fine friction-factor change is **0.03657%**. Each solver reaches the 2,500-iteration limit and passes the independent residual and saved-field stationarity gates; this is not an OpenFOAM convergence-stop message. These results do not establish accuracy for other fluids, geometries, turbulence, temperature ranges or thermal boundary conditions.

Reproduce through the existing validation runner:

```bash
.venv/bin/python - <<'PY'
import sys
from scripts import validate
validate.PRESETS['glycol_mass_flow'] = {'inputs': {
    'fluid': 'water_eg30', 'length_mm': 1000,
    'inlet': {'kind': 'mass_flow', 'value': 6, 'unit': 'kg/h'},
}}
sys.argv = ['validate', '--case', 'glycol_mass_flow', '--output', 'validation-output/v05-glycol']
raise SystemExit(validate.main())
PY
```
