"""Generate a Foundation OpenFOAM 14 case; geometry is separate from execution."""
import json
from math import cos, sin, radians, sqrt
from pathlib import Path

from .models import PipeDefinition


def header(name, cls="dictionary"):
    return f'FoamFile\n{{\n    format ascii;\n    class {cls};\n    object {name};\n}}\n\n'


def field(name, dimensions, initial, inlet, outlet, wall, cls="volScalarField"):
    return header(name, cls) + f"""dimensions {dimensions};
internalField uniform {initial};
boundaryField
{{
    inlet {{ {inlet} }}
    outlet {{ {outlet} }}
    wall {{ {wall} }}
    front {{ type wedge; }}
    back {{ type wedge; }}
}}
"""


def generate_pipe(case: Path, spec: PipeDefinition):
    """A one-cell circumferential wedge, collapsed on the x axis, in SI units."""
    errors = spec.run_errors()
    if errors:
        raise ValueError(" ".join(errors))
    for folder in ("0", "constant", "system"):
        (case / folder).mkdir(parents=True, exist_ok=True)
    length, radius = spec.length_m, spec.diameter_m / 2
    y, z = radius * cos(radians(2.5)), radius * sin(radians(2.5))
    nx, nr = spec.mesh_shape
    grading = 1 if spec.selected_model == "laminar" else .02
    files = {
        "system/blockMeshDict": header("blockMeshDict") + f"""
vertices ((0 0 0) ({length:.14g} 0 0)
          ({length:.14g} {y:.14g} {-z:.14g}) (0 {y:.14g} {-z:.14g})
          ({length:.14g} {y:.14g} {z:.14g}) (0 {y:.14g} {z:.14g}));
blocks (hex (0 1 2 3 0 1 4 5) ({nx} {nr} 1) simpleGrading (1 {grading} 1));
edges ();
boundary
(
    inlet {{ type patch; faces ((0 0 5 3)); }}
    outlet {{ type patch; faces ((1 2 4 1)); }}
    wall {{ type wall; faces ((3 5 4 2)); }}
    front {{ type wedge; faces ((0 3 2 1)); }}
    back {{ type wedge; faces ((0 1 4 5)); }}
);
mergePatchPairs ();
""",
        "constant/physicalProperties": header("physicalProperties") + f"viscosityModel constant;\nnu {spec.nu:.14g};\n",
        "constant/momentumTransport": header("momentumTransport") + (
            "simulationType laminar;\nlaminar { model Stokes; viscosityModel Newtonian; }\n" if spec.selected_model == "laminar" else
            "simulationType RAS;\nRAS { model kOmegaSST; turbulence on; viscosityModel Newtonian; }\n"),
        "0/U": field("U", "[0 1 -1 0 0 0 0]", f"({spec.inlet_velocity_m_s:.14g} 0 0)",
                     f"type fixedValue; value uniform ({spec.inlet_velocity_m_s:.14g} 0 0);",
                     "type zeroGradient;", "type noSlip;", "volVectorField"),
        "0/p": field("p", "[0 2 -2 0 0 0 0]", "0", "type zeroGradient;",
                     "type fixedValue; value uniform 0;", "type zeroGradient;"),
        "system/controlDict": header("controlDict") + f"""
application foamRun;
solver incompressibleFluid;
startFrom startTime;
startTime 0;
stopAt endTime;
endTime {spec.max_iterations};
deltaT 1;
writeControl timeStep;
writeInterval 100;
purgeWrite 2;
writeFormat ascii;
writePrecision 12;
writeCompression off;
timeFormat general;
timePrecision 10;
runTimeModifiable false;
""",
        "system/fvSchemes": header("fvSchemes") + """
ddtSchemes { default steadyState; }
gradSchemes { default Gauss linear; }
divSchemes
{
    default none;
    div(phi,U) bounded Gauss linearUpwind grad(U);
    div(phi,k) bounded Gauss limitedLinear 1;
    div(phi,omega) bounded Gauss limitedLinear 1;
    div((nuEff*dev2(T(grad(U))))) Gauss linear;
    div(nonlinearStress) Gauss linear;
}
laplacianSchemes { default Gauss linear corrected; }
interpolationSchemes { default linear; }
snGradSchemes { default corrected; }
wallDist { method meshWave; }
""",
        "system/fvSolution": header("fvSolution") + f"""
solvers
{{
    p {{ solver GAMG; tolerance 1e-10; relTol 0.01; smoother GaussSeidel; }}
    pcorr {{ solver GAMG; tolerance 1e-10; relTol 0; smoother GaussSeidel; }}
    "(U|k|omega)" {{ solver smoothSolver; smoother symGaussSeidel; tolerance 1e-10; relTol 0.01; }}
}}
SIMPLE
{{
    nNonOrthogonalCorrectors 0;
    consistent no;
    residualControl {{ p {spec.residual_tolerance:.12g}; U {spec.residual_tolerance:.12g};
                      "(k|omega)" {spec.residual_tolerance:.12g}; }}
}}
relaxationFactors
{{
    fields {{ p 0.3; }}
    equations {{ U 0.7; k 0.7; omega 0.7; }}
}}
""",
    }
    if spec.selected_model == "kOmegaSST":
        k = 1.5 * (spec.inlet_velocity_m_s * spec.turbulence_intensity)**2
        omega = sqrt(k) / (.09**.25 * .07 * spec.diameter_m)
        files["0/k"] = field("k", "[0 2 -2 0 0 0 0]", f"{k:.14g}",
                             f"type fixedValue; value uniform {k:.14g};", "type zeroGradient;", "type fixedValue; value uniform 1e-12;")
        files["0/omega"] = field("omega", "[0 0 -1 0 0 0 0]", f"{omega:.14g}",
                                 f"type fixedValue; value uniform {omega:.14g};", "type zeroGradient;", f"type omegaWallFunction; value uniform {omega:.14g};")
        files["0/nut"] = field("nut", "[0 2 -1 0 0 0 0]", "0",
                               "type calculated; value uniform 0;", "type calculated; value uniform 0;",
                               "type nutLowReWallFunction; value uniform 0;")
    for path, content in files.items():
        (case / path).write_text(content)
    (case / "pipe.foam").touch()
    (case / "manifest.json").write_text(json.dumps({"schema_version": 1, "generator": "pipe-wedge-v1",
        "openfoam": "Foundation 14", "inputs": spec.model_dump(),
        "boundaries": {"inlet": "uniform velocity", "outlet": "0 Pa gauge", "wall": "smooth no-slip"}}, indent=2))
