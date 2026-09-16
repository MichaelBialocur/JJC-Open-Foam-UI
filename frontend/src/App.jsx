import { useState } from 'react'
import './App.css'

function App() {
  const [form, setForm] = useState({
    length_mm: 500,
    inner_diameter_mm: 10,
    wall_thickness_mm: 2,
    material: 'aluminium',
    inlet_velocity_m_s: 1,
    inlet_temperature_c: 20,
    applied_heat_w: 500,
  })

  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  function updateField(event) {
    const { name, value } = event.target

    setForm((previous) => ({
      ...previous,
      [name]:
        name === 'material'
          ? value
          : Number(value),
    }))
  }

  async function previewPipe() {
    setError(null)
    setResult(null)

    try {
      const response = await fetch(
        '/api/pipe/preview',
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(form),
        }
      )

      if (!response.ok) {
        throw new Error(
          `Server returned ${response.status}`
        )
      }

      const data = await response.json()
      setResult(data)
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div className="app">
      <header>
        <div>
          <h1>Pipe CFD</h1>
          <p>OpenFOAM thermal-flow simulation</p>
        </div>

        <button onClick={previewPipe}>
          Create Pipe
        </button>
      </header>

      <main>
        <aside className="controls">

          <section>
            <h2>Geometry</h2>

            <label>
              Length
              <div>
                <input
                  name="length_mm"
                  type="number"
                  value={form.length_mm}
                  onChange={updateField}
                />
                <span>mm</span>
              </div>
            </label>

            <label>
              Inner diameter
              <div>
                <input
                  name="inner_diameter_mm"
                  type="number"
                  value={form.inner_diameter_mm}
                  onChange={updateField}
                />
                <span>mm</span>
              </div>
            </label>

            <label>
              Wall thickness
              <div>
                <input
                  name="wall_thickness_mm"
                  type="number"
                  value={form.wall_thickness_mm}
                  onChange={updateField}
                />
                <span>mm</span>
              </div>
            </label>
          </section>

          <section>
            <h2>Material</h2>

            <select
              name="material"
              value={form.material}
              onChange={updateField}
            >
              <option value="aluminium">
                Aluminium
              </option>

              <option value="copper">
                Copper
              </option>
            </select>
          </section>

          <section>
            <h2>Flow</h2>

            <label>
              Inlet velocity
              <div>
                <input
                  name="inlet_velocity_m_s"
                  type="number"
                  step="0.1"
                  value={form.inlet_velocity_m_s}
                  onChange={updateField}
                />
                <span>m/s</span>
              </div>
            </label>

            <label>
              Inlet temperature
              <div>
                <input
                  name="inlet_temperature_c"
                  type="number"
                  value={form.inlet_temperature_c}
                  onChange={updateField}
                />
                <span>°C</span>
              </div>
            </label>
          </section>

          <section>
            <h2>Thermal</h2>

            <label>
              Applied heat
              <div>
                <input
                  name="applied_heat_w"
                  type="number"
                  value={form.applied_heat_w}
                  onChange={updateField}
                />
                <span>W</span>
              </div>
            </label>
          </section>

        </aside>

        <section className="viewer">
          <div className="pipe">
            <div className="inlet">
              INLET →
            </div>

            <div className="pipeBody">
              PIPE
            </div>

            <div className="outlet">
              → OUTLET
            </div>
          </div>

          <div className="heat">
            ↑ HEAT
          </div>

          {result && (
            <div className="results">
              <h2>Pipe Preview</h2>

              <p>
                Flow rate:
                {' '}
                <strong>
                  {result.flow.flow_rate_l_min.toFixed(2)}
                  {' '}
                  L/min
                </strong>
              </p>

              <p>
                Reynolds number:
                {' '}
                <strong>
                  {result.flow.reynolds_number.toFixed(0)}
                </strong>
              </p>

              <p>
                Outer diameter:
                {' '}
                <strong>
                  {result.geometry.outer_diameter_mm.toFixed(2)}
                  {' '}
                  mm
                </strong>
              </p>

              <p>
                Solver:
                {' '}
                <strong>
                  {result.openfoam}
                </strong>
              </p>
            </div>
          )}

          {error && (
            <div className="error">
              {error}
            </div>
          )}
        </section>
      </main>
    </div>
  )
}

export default App