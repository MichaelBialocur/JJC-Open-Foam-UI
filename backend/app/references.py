"""Traceable reference values. None of these are CFD results."""

SUPERPIPE = {
    "id": "superpipe_41727",
    "title": "Princeton Superpipe, original Re 41,727 dataset",
    "kind": "experiment",
    "url": "https://www.princeton.edu/~gasdyn/Superpipe_data/4.1727E%2B04.txt",
    "publication": "Zagarola & Smits (1998), Mean-flow scaling of turbulent pipe flow, JFM 373, 33–79",
    "doi": "https://doi.org/10.1017/S0022112098002419",
    "retrieved": "2026-09-29",
    "reynolds": 41727.0,
    "darcy_friction_factor": 0.021858,
    "pressure_gradient_pa_m": 2.5855,
    "bulk_velocity_m_s": 5.1320,
    "friction_velocity_m_s": 0.26825,
    "diameter_m": 0.12936,
    "density_kg_m3": 1.1620,
    "dynamic_viscosity_pa_s": 1.8487e-5,
    "caveat": "Original uncorrected data: Princeton states that Pitot displacement and other corrections have NOT been applied and flags later pressure-correction work. This is an exploratory benchmark, not universal validation. Measurement uncertainty is not specified in this file.",
    # r/R and u+ pairs transcribed from the positive-radius half of the source.
    # Data are facts; retain original precision and provenance.
    "profile_r_uplus": [
        [0.99303,8.2379],[0.99234,8.7647],[0.99149,9.4217],[0.99051,9.7302],
        [0.98935,10.326],[0.98800,10.836],[0.98640,11.325],[0.98455,11.913],
        [0.98241,12.427],[0.97990,12.903],[0.97697,13.228],[0.97358,13.640],
        [0.96959,14.067],[0.96494,14.394],[0.95954,14.745],[0.95326,14.912],
        [0.94594,15.237],[0.93739,15.717],[0.92746,15.945],[0.91591,16.234],
        [0.90242,16.665],[0.88675,16.987],[0.86850,17.370],[0.84723,17.743],
        [0.82247,18.138],[0.79363,18.697],[0.76005,19.045],[0.72097,19.564],
        [0.67545,19.959],[0.62246,20.585],[0.56063,21.066],[0.49880,21.436],
        [0.43698,21.954],[0.37515,22.347],[0.31332,22.703],[0.25150,23.029],
        [0.18967,23.297],[0.14329,23.425],[0.096925,23.571],[0.066020,23.642],
        [0.035099,23.644],[0.0041936,23.654],
    ],
}


def reference_for(spec):
    if spec.selected_model == "laminar":
        return {"id": "hagen_poiseuille", "title": "Hagen–Poiseuille fully developed pipe flow",
                "kind": "analytical", "darcy_friction_factor": 64 / spec.reynolds,
                "pressure_gradient_pa_m": 32 * spec.dynamic_viscosity_pa_s * spec.inlet_velocity_m_s / spec.diameter_m**2,
                "url": "https://archive.nptel.ac.in/content/storage2/courses/112104118/lecture-26/26-3_hag_poiseuille.htm",
                "applicable": True, "note": "Compare the developed section, not the entrance-inclusive pressure loss."}
    matched = abs(spec.reynolds / SUPERPIPE["reynolds"] - 1) <= .01
    return {**{k: v for k, v in SUPERPIPE.items() if k != "profile_r_uplus"},
            "applicable": matched,
            "note": "Dimensionless comparison at matched Reynolds number (within 1%). Smooth wall, fully developed, incompressible flow required.",
            "profile": [{"r_over_R": r, "u_over_bulk": u * SUPERPIPE["friction_velocity_m_s"] / SUPERPIPE["bulk_velocity_m_s"]}
                        for r, u in sorted(SUPERPIPE["profile_r_uplus"])] if matched else []}
